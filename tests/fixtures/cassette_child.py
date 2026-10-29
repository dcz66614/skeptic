"""Open a cassette recorder, write one message and exit without finishing (P15).

The parent ``test_atexit_writes_the_missing_footer`` runs this as a child
process so the footer can only come from the recorder's ``atexit`` hook.
"""

import sys
from pathlib import Path

from skeptic_agent.jsonrpc import Message, parse_line
from skeptic_agent.protocol import Era
from skeptic_agent.record.cassette import Recorder

EPISODE_ID = "20261105-142233-a1b2c3:weather.forecast.max-temp.001:S04:1"
CALL = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"f","arguments":{}}}'


def main(directory: str) -> None:
    """Write one cassette line and return, leaving the footer to ``atexit``.

    Args:
        directory: The record directory.
    """
    recorder = Recorder.open(
        Path(directory),
        episode_id=EPISODE_ID,
        transport="stdio",
        upstream=["python"],
        era=Era(kind="MODERN", version="2026-07-28"),
        seed=1,
        profile="none",
        scenario_id="weather.forecast.max-temp.001",
    )
    message = parse_line(CALL)
    assert isinstance(message, Message)
    recorder.record(direction="c2s", msg=message)


if __name__ == "__main__":
    main(sys.argv[1])
