"""An example sandbox with two tools, used by ``test_sb_common`` (S30).

Run as ``python -m`` would: it passes its arguments straight to
``run_sandbox``, so ``--http HOST:PORT`` and ``--state-file PATH`` behave as
in a real sandbox (S9.1 item 2).
"""

from pydantic import BaseModel

from skeptic_agent.sandboxes.sb_common.server import ToolFailure, ToolSpec, run_sandbox
from skeptic_agent.sandboxes.sb_common.state import SandboxState


class ReadArguments(BaseModel):
    """No arguments; the S9.1 read tools still publish an object schema."""


class Count(BaseModel):
    count: int


class AddArguments(BaseModel):
    by: int


class AddResult(BaseModel):
    status: str
    count: int


async def get_count(arguments: ReadArguments, tool: object) -> Count:
    """Return the current count.

    Args:
        arguments: The validated arguments, unused.
        tool: The bound ``SandboxTool``.

    Returns:
        The count.
    """
    del arguments
    return Count(count=int(tool.data["count"]))


async def add(arguments: AddArguments, tool: object) -> AddResult:
    """Add to the count and write the state file.

    Args:
        arguments: The validated arguments.
        tool: The bound ``SandboxTool``.

    Returns:
        The new status and count.

    Raises:
        ToolFailure: When ``by`` is negative.
    """
    if arguments.by < 0:
        raise ToolFailure("cannot add a negative amount")
    data = tool.data
    data["count"] = int(data["count"]) + arguments.by
    tool.finish()
    return AddResult(status="ok", count=int(data["count"]))


TOOLS = (
    ToolSpec("get_count", "Return the current count.", ReadArguments, Count, get_count),
    ToolSpec(
        "add",
        "Add to the count and write the state file.",
        AddArguments,
        AddResult,
        add,
        write=True,
        destructive=False,
        idempotent=False,
    ),
)
"""The two tools the acceptance line asks for: one read, one write."""


def main() -> None:
    """Serve the example sandbox."""
    run_sandbox("example", TOOLS, SandboxState.from_env({"count": 0}))


if __name__ == "__main__":
    main()
