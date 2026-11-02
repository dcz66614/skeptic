"""The sb_docs tools (S9.2): three read-only document tools.

``search_docs`` searches the current version of the 30 fictional Northwind
Robotics documents KB-001 to KB-030, ``read_doc`` returns the current version
and ``read_doc_archive`` the requested older version. The archive is the
alternate source: the current and archived text differ, so an agent can
recover when the primary tool is corrupted.

S9.2 fixes the fields verbatim. A search result is ``doc_id, title, snippet,
updated_at``; a document is ``doc_id, title, body, updated_at, version``. The
document field order is the S9.2 order, which puts the numeric ``version``
last for the S6 S04 rule.

The state is the ``documents`` list of every version. The sandbox is all-read,
so the state file is written once at startup and never changes (S9.1 item 4).
"""

import copy
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from skeptic_agent.sandboxes.sb_common.data import load_json
from skeptic_agent.sandboxes.sb_common.server import (
    SandboxTool,
    ToolFailure,
    ToolSpec,
    make_server,
    run_sandbox,
)
from skeptic_agent.sandboxes.sb_common.state import SandboxState

NAME = "sb_docs"
"""The server name (S9.1 item 2)."""

DOCS_FILE = Path(__file__).resolve().parent / "data" / "docs.json"
"""The committed document table the server reads (S9.1 item 3)."""

SNIPPET_LENGTH = 160
"""How many characters of the body a search result carries."""

SNIPPET_LEAD = 60
"""How many characters of context precede a match in a snippet."""


class SearchArguments(BaseModel):
    """The arguments of ``search_docs``."""

    query: str = Field(description="Text to find in a document title or body.")
    top_k: int = Field(default=5, description="The maximum number of results, at least 1.")


class DocArguments(BaseModel):
    """The arguments of ``read_doc``."""

    doc_id: str = Field(description="The document id, for example 'KB-001'.")


class ArchiveArguments(DocArguments):
    """The arguments of ``read_doc_archive``."""

    version: int = Field(description="The archived version number, for example 1.")


class SearchHit(BaseModel):
    """One search result (S9.2 search fields)."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    snippet: str
    updated_at: str


class SearchResults(BaseModel):
    """The documents a search matched."""

    results: list[SearchHit]


class Document(BaseModel):
    """One document version (S9.2 document fields)."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    title: str
    body: str
    updated_at: str
    version: int


def load_documents() -> list[dict[str, Any]]:
    """Read the committed document versions as a fresh copy.

    Returns:
        One dict per version, in file order.
    """
    records: list[dict[str, Any]] = load_json(DOCS_FILE)
    return copy.deepcopy(records)


def _records(tool: SandboxTool) -> list[dict[str, Any]]:
    """Return the state's document versions, typed for the tools.

    Args:
        tool: The bound tool.

    Returns:
        The mutable list of version records.
    """
    records: list[dict[str, Any]] = tool.data["documents"]
    return records


def _current(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index the newest version of every document.

    Args:
        records: Every committed version.

    Returns:
        ``{doc_id: record}`` with the highest version of each document.
    """
    current: dict[str, dict[str, Any]] = {}
    for record in records:
        doc_id = str(record["doc_id"])
        previous = current.get(doc_id)
        if previous is None or int(record["version"]) > int(previous["version"]):
            current[doc_id] = record
    return current


def _doc(tool: SandboxTool, doc_id: str) -> dict[str, Any]:
    """Look up the current version of one document.

    Args:
        tool: The bound tool.
        doc_id: The client's document id.

    Returns:
        The current record.

    Raises:
        ToolFailure: When the id is not one of the 30 documents.
    """
    code = doc_id.strip().upper()
    current = _current(_records(tool))
    if code not in current:
        raise ToolFailure(f"unknown document {doc_id!r}")
    return current[code]


def _archive(tool: SandboxTool, doc_id: str, version: int) -> dict[str, Any]:
    """Look up one version of a document.

    Args:
        tool: The bound tool.
        doc_id: The client's document id.
        version: The requested version number.

    Returns:
        The matching record.

    Raises:
        ToolFailure: When the document or that version does not exist.
    """
    if version <= 0:
        raise ToolFailure("version must be greater than zero")
    code = doc_id.strip().upper()
    for record in _records(tool):
        if str(record["doc_id"]) == code and int(record["version"]) == version:
            return record
    if code not in _current(_records(tool)):
        raise ToolFailure(f"unknown document {doc_id!r}")
    raise ToolFailure(f"document {code} has no version {version}")


def _terms(query: str) -> list[str]:
    """Split a query into the terms every match must contain.

    Args:
        query: The client's query.

    Returns:
        The lower-cased terms.

    Raises:
        ToolFailure: When the query is empty or only whitespace.
    """
    terms = query.lower().split()
    if not terms:
        raise ToolFailure("query must not be empty")
    return terms


def _score(record: dict[str, Any], terms: list[str]) -> int:
    """Rank one document against a query.

    Args:
        record: The document version.
        terms: The lower-cased query terms.

    Returns:
        The weighted number of term occurrences; a title match counts twice.
    """
    title = str(record["title"]).lower()
    body = str(record["body"]).lower()
    return sum(title.count(term) * 2 + body.count(term) for term in terms)


def _matches(record: dict[str, Any], terms: list[str]) -> bool:
    """Tell whether every query term occurs in a document.

    Args:
        record: The document version.
        terms: The lower-cased query terms.

    Returns:
        ``True`` when all terms occur in the title or body.
    """
    text = f"{record['title']}\n{record['body']}".lower()
    return all(term in text for term in terms)


def _snippet(body: str, terms: list[str]) -> str:
    """Return a short excerpt around the first query term.

    Args:
        body: The document body.
        terms: The lower-cased query terms.

    Returns:
        At most ``SNIPPET_LENGTH`` characters, starting before the first
        match when one exists in the body.
    """
    lowered = body.lower()
    positions = [lowered.find(term) for term in terms]
    found = [position for position in positions if position >= 0]
    start = max(0, min(found) - SNIPPET_LEAD) if found else 0
    return body[start : start + SNIPPET_LENGTH].strip()


async def search_docs(arguments: SearchArguments, tool: SandboxTool) -> SearchResults:
    """Search the current version of every document.

    Args:
        arguments: The query and the maximum number of results.
        tool: The bound tool.

    Returns:
        The matching documents, best score first then by id. No match is an
        empty ``results`` list.

    Raises:
        ToolFailure: On an empty query or a ``top_k`` below one.
    """
    if arguments.top_k < 1:
        raise ToolFailure("top_k must be greater than zero")
    terms = _terms(arguments.query)
    ranked = [
        (record, _score(record, terms))
        for record in _current(_records(tool)).values()
        if _matches(record, terms)
    ]
    ranked.sort(key=lambda item: (-item[1], str(item[0]["doc_id"])))
    return SearchResults(
        results=[
            SearchHit(
                doc_id=str(record["doc_id"]),
                title=str(record["title"]),
                snippet=_snippet(str(record["body"]), terms),
                updated_at=str(record["updated_at"]),
            )
            for record, _ in ranked[: arguments.top_k]
        ]
    )


async def read_doc(arguments: DocArguments, tool: SandboxTool) -> Document:
    """Return the current version of one document.

    Args:
        arguments: The document id.
        tool: The bound tool.

    Returns:
        The current document version.

    Raises:
        ToolFailure: On an unknown document id.
    """
    return Document.model_validate(_doc(tool, arguments.doc_id))


async def read_doc_archive(arguments: ArchiveArguments, tool: SandboxTool) -> Document:
    """Return one archived version of a document.

    Args:
        arguments: The document id and version.
        tool: The bound tool.

    Returns:
        The requested version.

    Raises:
        ToolFailure: On an unknown document, a non-positive version, or a
            version the document does not have.
    """
    return Document.model_validate(_archive(tool, arguments.doc_id, arguments.version))


TOOLS = (
    ToolSpec(
        "search_docs",
        "Search the current version of the Northwind Robotics documents.",
        SearchArguments,
        SearchResults,
        search_docs,
    ),
    ToolSpec(
        "read_doc",
        "Return one document's current version with its full body.",
        DocArguments,
        Document,
        read_doc,
    ),
    ToolSpec(
        "read_doc_archive",
        "Return an older version of one document (the alternate source).",
        ArchiveArguments,
        Document,
        read_doc_archive,
    ),
)
"""The three S9.2 tools, all read-only."""


def build_state() -> SandboxState:
    """Build the sandbox state from the committed documents.

    Returns:
        A state whose ``documents`` key holds every version; the file comes
        from ``SKEPTIC_STATE_FILE`` (S9.1 item 4).
    """
    return SandboxState.from_env({"documents": load_documents()})


def server(state: SandboxState | None = None) -> Any:
    """Build the sb_docs server.

    Args:
        state: The state to serve; defaults to :func:`build_state`.

    Returns:
        The SDK server.
    """
    return make_server(NAME, TOOLS, state if state is not None else build_state())


def main() -> None:
    """Serve sb_docs (stdio, or ``--http HOST:PORT``)."""
    run_sandbox(NAME, TOOLS, build_state())


if __name__ == "__main__":
    main()
