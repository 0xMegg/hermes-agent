"""Focused tests for DELIVER_ONLY gateway turn intent notices."""

from __future__ import annotations

import asyncio
import sys
import types
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

# Minimal telegram stub so importing gateway.platforms.base does not pull in
# the real python-telegram-bot dependency in focused unit tests.
_tg = sys.modules.get("telegram") or types.ModuleType("telegram")
setattr(_tg, "constants", sys.modules.get("telegram.constants") or types.ModuleType("telegram.constants"))
_ct = MagicMock()
_ct.PRIVATE = "private"
_ct.GROUP = "group"
_ct.SUPERGROUP = "supergroup"
setattr(_tg.constants, "ChatType", _ct)
sys.modules.setdefault("telegram", _tg)
sys.modules.setdefault("telegram.constants", _tg.constants)
sys.modules.setdefault("telegram.ext", types.ModuleType("telegram.ext"))

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.base import (
    BasePlatformAdapter,
    MessageEvent,
    MessageType,
    SendResult,
    TurnIntent,
)
from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key


class _DummyAdapter(BasePlatformAdapter):  # type: ignore[misc]
    async def connect(self):
        return True

    async def disconnect(self):
        pass

    async def get_chat_info(self, chat_id):
        return {}

    async def send(self, *args, **kwargs):
        return SendResult(success=True, message_id="sent")


def _make_adapter() -> BasePlatformAdapter:
    adapter = _DummyAdapter(PlatformConfig(enabled=True, token="***"), Platform.TELEGRAM)
    cast(Any, adapter)._message_handler = AsyncMock(return_value="agent response")
    adapter._busy_session_handler = None
    cast(Any, adapter)._send_with_retry = AsyncMock(return_value=SendResult(success=True, message_id="notice"))
    return adapter


def _send_mock(adapter: BasePlatformAdapter) -> AsyncMock:
    return cast(AsyncMock, cast(Any, adapter)._send_with_retry)


def _handler_mock(adapter: BasePlatformAdapter) -> AsyncMock:
    return cast(AsyncMock, cast(Any, adapter)._message_handler)


def _make_event(
    text: str = "notice",
    *,
    turn_intent: TurnIntent = TurnIntent.TRIGGER,
    user_id: str | None = "u1",
    chat_id: str = "12345",
) -> MessageEvent:
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.TELEGRAM,
            chat_id=chat_id,
            chat_type="dm",
            user_id=user_id,
            user_name="alice" if user_id else None,
        ),
        message_id="msg-1",
        turn_intent=turn_intent,
    )


@pytest.mark.asyncio
async def test_active_deliver_only_sends_once_without_pending_or_handler():
    adapter = _make_adapter()
    event = _make_event("watch matched", turn_intent=TurnIntent.DELIVER_ONLY)
    session_key = build_session_key(event.source)
    adapter._active_sessions[session_key] = asyncio.Event()

    await adapter.handle_message(event)

    _send_mock(adapter).assert_awaited_once()
    assert _send_mock(adapter).await_args.kwargs["chat_id"] == "12345"
    assert _send_mock(adapter).await_args.kwargs["content"] == "watch matched"
    _handler_mock(adapter).assert_not_awaited()
    assert session_key not in adapter._pending_messages
    assert session_key in adapter._active_sessions
    assert not adapter._active_sessions[session_key].is_set()


@pytest.mark.asyncio
async def test_deliver_only_does_not_replace_existing_human_pending():
    adapter = _make_adapter()
    existing = _make_event("human followup")
    event = _make_event("watch matched", turn_intent=TurnIntent.DELIVER_ONLY)
    session_key = build_session_key(event.source)
    adapter._active_sessions[session_key] = asyncio.Event()
    adapter._pending_messages[session_key] = existing

    await adapter.handle_message(event)

    _send_mock(adapter).assert_awaited_once()
    assert adapter._pending_messages[session_key] is existing
    assert adapter._pending_messages[session_key].text == "human followup"
    _handler_mock(adapter).assert_not_awaited()


@pytest.mark.asyncio
async def test_idle_deliver_only_sends_once_without_starting_agent():
    adapter = _make_adapter()
    event = _make_event("idle notice", turn_intent=TurnIntent.DELIVER_ONLY)
    session_key = build_session_key(event.source)

    await adapter.handle_message(event)

    _send_mock(adapter).assert_awaited_once()
    assert _send_mock(adapter).await_args.kwargs["content"] == "idle notice"
    _handler_mock(adapter).assert_not_awaited()
    assert session_key not in adapter._active_sessions
    assert session_key not in adapter._session_tasks
    assert session_key not in adapter._pending_messages


@pytest.mark.asyncio
async def test_runner_direct_deliver_only_defense_returns_none_without_agent(monkeypatch, tmp_path):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")

    runner = GatewayRunner(GatewayConfig())
    event = MessageEvent(
        text="notice",
        source=SessionSource(
            platform=Platform.DISCORD,
            chat_id="c1",
            chat_type="dm",
            user_id=None,
        ),
        internal=True,
        turn_intent=TurnIntent.DELIVER_ONLY,
    )

    agent = AsyncMock(return_value="agent response")
    auth = MagicMock(return_value=True)
    monkeypatch.setattr(GatewayRunner, "_handle_message_with_agent", agent)
    monkeypatch.setattr(GatewayRunner, "_is_user_authorized", auth)

    result = await runner._handle_message(event)

    assert result is None
    agent.assert_not_awaited()
    auth.assert_not_called()


def test_internal_default_preserves_trigger_turn_intent():
    event = MessageEvent(
        text="completion",
        source=SessionSource(platform=Platform.DISCORD, chat_id="c1", chat_type="dm"),
        internal=True,
    )

    assert event.internal is True
    assert event.turn_intent == TurnIntent.TRIGGER


@pytest.mark.asyncio
async def test_inject_watch_notification_constructs_deliver_only(monkeypatch, tmp_path):
    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_hermes_home", tmp_path)
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")

    runner = GatewayRunner(GatewayConfig())
    adapter = MagicMock()
    adapter.handle_message = AsyncMock()
    runner.adapters[Platform.DISCORD] = adapter

    await runner._inject_watch_notification(
        "watch matched",
        {
            "session_id": "proc-1",
            "platform": "discord",
            "chat_type": "dm",
            "chat_id": "c1",
            "user_id": "u1",
            "user_name": "alice",
            "message_id": "m1",
        },
    )

    adapter.handle_message.assert_awaited_once()
    event = adapter.handle_message.await_args.args[0]
    assert event.text == "watch matched"
    assert event.internal is True
    assert event.turn_intent == TurnIntent.DELIVER_ONLY
    assert event.source.chat_id == "c1"
