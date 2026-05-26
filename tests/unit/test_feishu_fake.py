"""Tests for FakeLarkCli — records send/consume calls, replays canned events."""

import pytest

from feishu_bot_claude_win.daemon.feishu import FakeLarkCli, LarkCli


@pytest.mark.asyncio
async def test_fake_send_text_records():
    lark: LarkCli = FakeLarkCli()
    msg_id = await lark.send_text(chat_id="oc_xxx", text="hello", idempotency_key="k1")
    assert msg_id.startswith("om_fake_")
    assert lark.send_calls[-1] == {
        "kind": "text",
        "chat_id": "oc_xxx",
        "text": "hello",
        "idempotency_key": "k1",
    }


@pytest.mark.asyncio
async def test_fake_send_card_records():
    lark = FakeLarkCli()
    card = {"elements": [{"tag": "markdown", "content": "hi"}]}
    msg_id = await lark.send_card(chat_id="oc_xxx", card=card, idempotency_key="k2")
    assert msg_id.startswith("om_fake_")
    assert lark.send_calls[-1] == {
        "kind": "card",
        "chat_id": "oc_xxx",
        "card": card,
        "idempotency_key": "k2",
    }


@pytest.mark.asyncio
async def test_fake_update_card_records():
    lark = FakeLarkCli()
    card = {"elements": []}
    await lark.update_card(message_id="om_fake_1", card=card)
    assert lark.send_calls[-1] == {
        "kind": "update",
        "message_id": "om_fake_1",
        "card": card,
    }


@pytest.mark.asyncio
async def test_fake_consume_yields_queued_events():
    lark = FakeLarkCli()
    lark.enqueue_event({"type": "im.message.receive_v1", "event": {"message": {"content": '{"text":"hi"}'}}})
    lark.enqueue_event({"type": "im.message.receive_v1", "event": {"message": {"content": '{"text":"again"}'}}})

    received = []
    async for evt in lark.consume_events(event_key="im.message.receive_v1", max_events=2):
        received.append(evt)

    assert len(received) == 2
    assert received[0]["event"]["message"]["content"] == '{"text":"hi"}'


@pytest.mark.asyncio
async def test_fake_consume_obeys_max_events():
    lark = FakeLarkCli()
    for i in range(5):
        lark.enqueue_event({"event": {"i": i}})

    received = []
    async for evt in lark.consume_events(event_key="im.message.receive_v1", max_events=3):
        received.append(evt)
    assert len(received) == 3


@pytest.mark.asyncio
async def test_fake_auth_bot_new_stream_yields_lines():
    lark = FakeLarkCli()
    lark.set_auth_lines(["line 1", "line 2", '{"app_id":"x","app_secret":"y"}'])
    received = []
    async for line in lark.auth_bot_new_stream("test-bot"):
        received.append(line.rstrip("\n"))
    assert received == ["line 1", "line 2", '{"app_id":"x","app_secret":"y"}']


@pytest.mark.asyncio
async def test_fake_push_menu_records():
    lark = FakeLarkCli()
    await lark.push_menu(app_id="cli_x", menu_json={"a": 1})
    assert lark._menu_pushes == [{"app_id": "cli_x", "menu": {"a": 1}}]


@pytest.mark.asyncio
async def test_fake_push_menu_can_fail():
    lark = FakeLarkCli()
    lark.fail_menu_push(True)
    with pytest.raises(RuntimeError, match="fake menu API failure"):
        await lark.push_menu(app_id="cli_x", menu_json={})


from feishu_bot_claude_win.daemon.feishu import FeishuThrottled


@pytest.mark.asyncio
async def test_fake_simulates_11232_then_succeeds():
    """FakeLarkCli can be configured to fail with 11232 N times before succeeding."""
    lark = FakeLarkCli()
    lark.simulate_throttle(times=2)
    # First two calls should raise; third should succeed
    with pytest.raises(FeishuThrottled):
        await lark.send_text(chat_id="oc", text="hi")
    with pytest.raises(FeishuThrottled):
        await lark.send_text(chat_id="oc", text="hi")
    msg_id = await lark.send_text(chat_id="oc", text="hi")
    assert msg_id.startswith("om_fake_")
    assert lark.throttle_attempts == 2


@pytest.mark.asyncio
async def test_feishu_throttled_is_runtimeerror_subclass():
    """FeishuThrottled is a RuntimeError so it can be caught broadly if needed."""
    e = FeishuThrottled("rate limited")
    assert isinstance(e, RuntimeError)
