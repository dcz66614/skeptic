"""Unit tests for the JSON-RPC message model and framing."""

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skeptic_agent.jsonrpc import (
    ErrorObject,
    ErrorResponse,
    Message,
    Notification,
    ParseError,
    Request,
    Response,
    dump,
    parse_line,
)

pytestmark = pytest.mark.unit

JSON_SCALARS = (
    st.none()
    | st.booleans()
    | st.integers()
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text()
)
JSON_VALUES = st.recursive(
    JSON_SCALARS,
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=10,
)
METHODS = st.text(min_size=1)
IDS = st.integers() | st.text()


def _semantic_key(msg: Message) -> dict[str, Any]:
    key = msg.model_dump(exclude={"raw_bytes"})
    if isinstance(msg, Request | Notification) and msg.params is None:
        key.pop("params")
    return key


def test_parse_request() -> None:
    line = b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo"}}\n'
    msg = parse_line(line)
    assert isinstance(msg, Request)
    assert msg.id == 1
    assert msg.method == "tools/call"
    assert msg.params == {"name": "echo"}
    assert msg.raw_bytes == line.removesuffix(b"\n")


def test_parse_request_string_id() -> None:
    msg = parse_line(b'{"jsonrpc":"2.0","id":"abc","method":"initialize"}\r\n')
    assert isinstance(msg, Request)
    assert msg.id == "abc"
    assert msg.params is None
    assert msg.raw_bytes == b'{"jsonrpc":"2.0","id":"abc","method":"initialize"}'


def test_numeric_string_id_stays_string() -> None:
    msg = parse_line(b'{"jsonrpc":"2.0","id":"7","method":"ping"}')
    assert isinstance(msg, Request)
    assert msg.id == "7"


def test_parse_notification() -> None:
    line = b'{"jsonrpc":"2.0","method":"notifications/initialized"}'
    msg = parse_line(line)
    assert isinstance(msg, Notification)
    assert msg.method == "notifications/initialized"
    assert msg.params is None
    assert msg.raw_bytes == line


def test_parse_request_with_positional_params() -> None:
    line = b'{"jsonrpc":"2.0","id":1,"method":"add","params":[1,"a"]}'
    msg = parse_line(line)
    assert isinstance(msg, Request)
    assert msg.params == [1, "a"]
    assert dump(msg) == line + b"\n"


def test_parse_notification_with_positional_params() -> None:
    line = b'{"jsonrpc":"2.0","method":"notify","params":[1,"a"]}'
    msg = parse_line(line)
    assert isinstance(msg, Notification)
    assert msg.params == [1, "a"]
    assert dump(msg) == line + b"\n"


def test_parse_response() -> None:
    line = b'{"jsonrpc":"2.0","id":5,"result":{"ok":true}}'
    msg = parse_line(line)
    assert isinstance(msg, Response)
    assert msg.id == 5
    assert msg.result == {"ok": True}
    assert msg.raw_bytes == line


def test_parse_response_null_id() -> None:
    msg = parse_line(b'{"jsonrpc":"2.0","id":null,"result":null}')
    assert isinstance(msg, Response)
    assert msg.id is None
    assert msg.result is None


def test_parse_error_response() -> None:
    line = (
        b'{"jsonrpc":"2.0","id":3,"error":{"code":-32601,"message":"Method not found",'
        b'"data":{"method":"nope"}}}'
    )
    msg = parse_line(line)
    assert isinstance(msg, ErrorResponse)
    assert msg.id == 3
    assert msg.error.code == -32601
    assert msg.error.message == "Method not found"
    assert msg.error.data == {"method": "nope"}
    assert msg.raw_bytes == line


def test_parse_array_is_parse_error() -> None:
    line = b'[{"jsonrpc":"2.0","id":1,"method":"a"},{"jsonrpc":"2.0","method":"b"}]\n'
    result = parse_line(line)
    assert isinstance(result, ParseError)
    assert result.raw_bytes == line.removesuffix(b"\n")
    assert result.reason == "message must be a JSON object"


def test_parse_empty_and_partial_lines_are_parse_errors() -> None:
    for line in (b"", b"\n", b"\r\n", b"   ", b'{"jsonrpc":"2.0"}'):
        result = parse_line(line)
        assert isinstance(result, ParseError)
        assert result.raw_bytes == line.removesuffix(b"\n").removesuffix(b"\r")


def test_parse_invalid_utf8_is_parse_error() -> None:
    result = parse_line(b'{"jsonrpc":"2.0","method":"\xff"}')
    assert isinstance(result, ParseError)
    assert "UTF-8" in result.reason


def test_parse_structurally_invalid_message_is_parse_error() -> None:
    line = b'{"jsonrpc":"2.0","id":{"nested":1},"method":"a"}'
    result = parse_line(line)
    assert isinstance(result, ParseError)
    assert result.raw_bytes == line
    assert result.reason.startswith("invalid message")


def test_parse_invalid_json_is_parse_error() -> None:
    line = b'{"jsonrpc":"2.0",'
    result = parse_line(line)
    assert isinstance(result, ParseError)
    assert result.raw_bytes == line
    assert "JSON" in result.reason


def test_parse_non_object_is_parse_error() -> None:
    result = parse_line(b'"hello"')
    assert isinstance(result, ParseError)
    assert result.raw_bytes == b'"hello"'


@pytest.mark.parametrize(
    "line", [b'{"id":1,"method":"a"}', b'{"jsonrpc":"1.0","id":1,"method":"a"}']
)
def test_missing_or_wrong_version_is_parse_error(line: bytes) -> None:
    result = parse_line(line)
    assert isinstance(result, ParseError)
    assert result.raw_bytes == line


def test_dump_is_compact_and_newline_terminated() -> None:
    msg = Notification(method="notify", params={"b": 2, "a": 1})
    out = dump(msg)
    assert out.endswith(b"\n")
    assert out.count(b"\n") == 1
    assert b": " not in out
    assert b", " not in out
    text = out.decode("utf-8")
    assert text.startswith('{"jsonrpc":"2.0",')


def test_dump_omits_none_params() -> None:
    assert dump(Request(id=1, method="ping")) == b'{"jsonrpc":"2.0","id":1,"method":"ping"}\n'


def test_dump_keeps_chinese() -> None:
    out = dump(Notification(method="notify", params={"city": "北京"}))
    assert "北京".encode() in out


def test_dump_excludes_raw_bytes() -> None:
    msg = Request(id="x", method="tools/list", raw_bytes=b'{"jsonrpc":"2.0"}')
    payload = json.loads(dump(msg))
    assert "raw_bytes" not in payload


def test_dump_keeps_null_and_empty_members() -> None:
    assert dump(Response(id=None, result=None)) == b'{"jsonrpc":"2.0","id":null,"result":null}\n'
    assert (
        dump(ErrorResponse(id=1, error=ErrorObject(code=-1, message="boom")))
        == b'{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"boom","data":null}}\n'
    )


def test_dump_rejects_non_json_payload() -> None:
    with pytest.raises(TypeError):
        dump(Response(id=1, result=object()))


@given(
    st.one_of(
        st.builds(
            Request,
            id=IDS,
            method=METHODS,
            params=st.none() | st.dictionaries(st.text(), JSON_VALUES),
        ),
        st.builds(
            Notification,
            method=METHODS,
            params=st.none() | st.dictionaries(st.text(), JSON_VALUES),
        ),
        st.builds(Response, id=IDS, result=JSON_VALUES),
        st.builds(
            Response,
            id=st.none(),
            result=JSON_VALUES,
        ),
        st.builds(
            ErrorResponse,
            id=IDS,
            error=st.builds(
                ErrorObject,
                code=st.integers(),
                message=st.text(),
                data=JSON_VALUES,
            ),
        ),
    )
)
def test_round_trip(msg: Message) -> None:
    dumped = dump(msg)
    parsed = parse_line(dumped)
    assert not isinstance(parsed, ParseError)
    assert isinstance(parsed, type(msg))
    assert _semantic_key(parsed) == _semantic_key(msg)
