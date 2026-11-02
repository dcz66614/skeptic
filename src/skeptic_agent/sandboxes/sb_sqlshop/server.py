"""The sb_sqlshop tools (S9.2): three read-only SQL tools.

``get_schema`` describes the four tables, ``run_query`` runs a SELECT on the
committed database and ``run_query_replica`` is the alternate source that runs
the same SELECT on a fresh copy of the same database. The database is built in
memory from the committed ``data/shop.sql`` on every call, so it always
matches the S9.2 row counts: 40 products, 40 customers, 120 orders and 300
order items.

Only a single SELECT statement is accepted (S9.2). Anything else, and any
SQLite syntax or name error, is a business error (``isError``) rather than a
JSON-RPC error (S9.1 item 7).

A query result is the S9.2 shape ``columns, rows, row_count``. ``get_schema``
is not given return fields by S9.2, so it returns ``tables`` with each table's
``name`` and its ``columns`` of ``name, type, not_null, primary_key``.

The sandbox is all-read, so its state file is written once at startup and
never changes (S9.1 item 4).
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_sqlshop"
"""The server name (S9.1 item 2)."""

SHOP_SQL = Path(__file__).resolve().parent / "data" / "shop.sql"
"""The committed database script the server reads (S9.1 item 3)."""

TABLES = ("products", "customers", "orders", "order_items")
"""The four S9.2 tables, in schema order."""

_SELECT = re.compile(r"(?is)^select\b")
"""Matches a statement that starts with the SELECT keyword."""


class SchemaArguments(BaseModel):
    """The arguments of ``get_schema``; the tool takes none."""


class QueryArguments(BaseModel):
    """The arguments of ``run_query`` and ``run_query_replica``."""

    sql: str = Field(description="One SELECT statement over the shop tables.")


class ColumnInfo(BaseModel):
    """One column of a table."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    not_null: bool
    primary_key: bool


class TableInfo(BaseModel):
    """One table of the shop database."""

    model_config = ConfigDict(extra="forbid")

    name: str
    columns: list[ColumnInfo]


class Schema(BaseModel):
    """The four tables of the shop database."""

    tables: list[TableInfo]


class QueryResult(BaseModel):
    """The result of a query (S9.2 ``columns, rows, row_count``)."""

    columns: list[str]
    rows: list[list[Any]]
    row_count: int


def load_script() -> str:
    """Read the committed database script.

    Returns:
        The SQL text of ``data/shop.sql``.
    """
    return SHOP_SQL.read_text(encoding="utf-8")


def _connection() -> sqlite3.Connection:
    """Build the in-memory database from the committed script.

    Returns:
        A new connection holding the S9.2 tables.
    """
    connection = sqlite3.connect(":memory:")
    connection.executescript(load_script())
    return connection


def _select_statement(sql: str) -> str:
    """Validate a query as one SELECT statement.

    Args:
        sql: The client's SQL.

    Returns:
        The statement without a trailing semicolon.

    Raises:
        ToolFailure: When the SQL is empty, holds more than one statement, or
            does not start with SELECT.
    """
    text = sql.strip()
    if not text:
        raise ToolFailure("SQL must not be empty")
    statement = text[:-1].rstrip() if text.endswith(";") else text
    if ";" in statement:
        raise ToolFailure("only one SQL statement is allowed")
    if not _SELECT.match(statement):
        raise ToolFailure("only SELECT statements are allowed")
    return statement


def _schema(connection: sqlite3.Connection) -> Schema:
    """Read the table and column metadata.

    Args:
        connection: The open in-memory database.

    Returns:
        The four tables in :data:`TABLES` order.
    """
    tables: list[TableInfo] = []
    for table in TABLES:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        tables.append(
            TableInfo(
                name=table,
                columns=[
                    ColumnInfo(
                        name=str(row[1]),
                        type=str(row[2]),
                        not_null=bool(row[3]),
                        primary_key=bool(row[5]),
                    )
                    for row in rows
                ],
            )
        )
    return Schema(tables=tables)


def _run(sql: str) -> QueryResult:
    """Run one validated SELECT on a fresh in-memory database.

    Args:
        sql: The client's SQL.

    Returns:
        The columns, rows and row count.

    Raises:
        ToolFailure: When the statement is not a single SELECT or SQLite
            rejects it.
    """
    statement = _select_statement(sql)
    connection = _connection()
    try:
        cursor = connection.execute(statement)
        columns = [str(description[0]) for description in cursor.description or []]
        rows = [list(row) for row in cursor.fetchall()]
    except sqlite3.Error as error:
        raise ToolFailure(f"SQL error: {error}") from None
    finally:
        connection.close()
    return QueryResult(columns=columns, rows=rows, row_count=len(rows))


async def get_schema(arguments: SchemaArguments, tool: SandboxTool) -> Schema:
    """Return the schema of the four shop tables.

    Args:
        arguments: No arguments.
        tool: The bound tool.

    Returns:
        The tables and their columns.
    """
    del arguments, tool
    connection = _connection()
    try:
        return _schema(connection)
    finally:
        connection.close()


async def run_query(arguments: QueryArguments, tool: SandboxTool) -> QueryResult:
    """Run one SELECT on the primary in-memory database.

    Args:
        arguments: The SQL statement.
        tool: The bound tool.

    Returns:
        The columns, rows and row count.

    Raises:
        ToolFailure: On a non-SELECT statement, more than one statement, or a
            SQLite error.
    """
    del tool
    return _run(arguments.sql)


async def run_query_replica(arguments: QueryArguments, tool: SandboxTool) -> QueryResult:
    """Run one SELECT on the replica in-memory database (the alternate).

    Args:
        arguments: The SQL statement.
        tool: The bound tool.

    Returns:
        The columns, rows and row count.

    Raises:
        ToolFailure: On a non-SELECT statement, more than one statement, or a
            SQLite error.
    """
    del tool
    return _run(arguments.sql)


TOOLS = (
    ToolSpec(
        "get_schema",
        "Return the four shop tables with their columns and key hints.",
        SchemaArguments,
        Schema,
        get_schema,
    ),
    ToolSpec(
        "run_query",
        "Run one SELECT statement on the primary shop database.",
        QueryArguments,
        QueryResult,
        run_query,
    ),
    ToolSpec(
        "run_query_replica",
        "Run one SELECT statement on the replica shop database (the alternate).",
        QueryArguments,
        QueryResult,
        run_query_replica,
    ),
)
"""The three S9.2 tools, all read-only."""


def build_state() -> SandboxState:
    """Build the sandbox state for the read-only shop.

    Returns:
        A state naming the committed script and its tables; the file comes
        from ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"database": SHOP_SQL.name, "tables": list(TABLES)})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_sqlshop server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_sqlshop (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
