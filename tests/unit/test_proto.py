"""Tests for IPC protocol types."""

import json

import pytest

from feishu_bot_claude_win.proto import Request


def test_request_serializes_to_json_line():
    """A Request can be serialized to a single-line JSON string."""
    req = Request(op="bind", args={"name": "foo-bot", "cwd": "/x/y"}, request_id="r-1")
    line = req.to_json_line()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed == {
        "op": "bind",
        "args": {"name": "foo-bot", "cwd": "/x/y"},
        "request_id": "r-1",
    }


def test_request_parses_from_json_line():
    """A JSON line round-trips into an equivalent Request."""
    line = '{"op": "list", "args": {}, "request_id": "r-2"}'
    req = Request.from_json_line(line)
    assert req.op == "list"
    assert req.args == {}
    assert req.request_id == "r-2"


def test_request_roundtrip():
    """Serializing then parsing produces an equal Request."""
    original = Request(op="start", args={"cwd": "/p"}, request_id="r-3")
    restored = Request.from_json_line(original.to_json_line())
    assert restored == original


from feishu_bot_claude_win.proto import (
    LogEvent,
    QRCodeEvent,
    ProgressEvent,
    ResultEvent,
    DoneEvent,
    parse_response_line,
)


def test_log_event_roundtrip():
    e = LogEvent(level="info", msg="hello")
    line = e.to_json_line()
    parsed = parse_response_line(line)
    assert parsed == e


def test_qrcode_event_roundtrip():
    e = QRCodeEvent(ascii="█▀█", url="https://example/qr")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_progress_event_roundtrip():
    e = ProgressEvent(value=0.42, msg="working")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_result_event_roundtrip_ok():
    e = ResultEvent(ok=True, data={"x": 1}, error=None)
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_result_event_roundtrip_err():
    e = ResultEvent(ok=False, data=None, error="something failed")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_done_event_roundtrip():
    e = DoneEvent()
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_parse_unknown_event_type_raises():
    with pytest.raises(ValueError, match="unknown event type"):
        parse_response_line('{"type": "alien", "foo": 1}')


def test_request_rejects_unknown_op():
    with pytest.raises(ValueError, match="unknown op"):
        Request(op="not-a-real-op", args={}).validate()


def _args_for(op: str) -> dict:
    """Return minimal valid args for each op (helper for the test above)."""
    return {
        "bind": {"name": "x", "cwd": "/x"},
        "unbind": {"name": "x"},
        "start": {"cwd": "/x"},
        "stop": {"cwd": "/x"},
        "config": {"cwd": "/x"},
        "status": {},
        "list": {},
        "shell": {"cwd": "/x"},
    }[op]


def test_request_accepts_known_ops():
    for op in ["bind", "unbind", "start", "stop", "list", "config", "status", "shell"]:
        Request(op=op, args=_args_for(op)).validate()  # no raise


def test_request_bind_requires_name_and_cwd():
    with pytest.raises(ValueError, match="bind requires"):
        Request(op="bind", args={"name": "foo"}).validate()
    with pytest.raises(ValueError, match="bind requires"):
        Request(op="bind", args={"cwd": "/x"}).validate()
    Request(op="bind", args={"name": "foo", "cwd": "/x"}).validate()  # ok


def test_request_start_requires_cwd():
    with pytest.raises(ValueError, match="start requires"):
        Request(op="start", args={}).validate()
    Request(op="start", args={"cwd": "/x"}).validate()  # ok
