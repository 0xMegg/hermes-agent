"""Minimal e2e tests for Discord mention stripping + /command detection.

Covers the fix for slash commands not being recognized when sent via
@mention in a channel, especially after auto-threading.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.e2e.conftest import (
    BOT_USER_ID,
    DiscordAdapter,
    E2E_MESSAGE_SETTLE_DELAY,
    get_response_text,
    make_discord_message,
    make_fake_dm_channel,
    make_fake_thread,
)

pytestmark = pytest.mark.asyncio


async def dispatch(adapter, msg):
    await adapter._handle_message(msg)
    await asyncio.sleep(E2E_MESSAGE_SETTLE_DELAY)


class TestMentionStrippedCommandDispatch:
    async def test_mention_then_command(self, discord_adapter, bot_user):
        """<@BOT> /help → mention stripped, /help dispatched."""
        msg = make_discord_message(
            content=f"<@{BOT_USER_ID}> /help",
            mentions=[bot_user],
        )
        await dispatch(discord_adapter, msg)
        response = get_response_text(discord_adapter)
        assert response is not None
        assert "/new" in response

    async def test_nickname_mention_then_command(self, discord_adapter, bot_user):
        """<@!BOT> /help → nickname mention also stripped, /help works."""
        msg = make_discord_message(
            content=f"<@!{BOT_USER_ID}> /help",
            mentions=[bot_user],
        )
        await dispatch(discord_adapter, msg)
        response = get_response_text(discord_adapter)
        assert response is not None
        assert "/new" in response

    async def test_text_before_command_not_detected(self, discord_adapter, bot_user):
        """'<@BOT> something else /help' → mention stripped, but 'something else /help'
        doesn't start with / so it's treated as text, not a command."""
        msg = make_discord_message(
            content=f"<@{BOT_USER_ID}> something else /help",
            mentions=[bot_user],
        )
        await dispatch(discord_adapter, msg)
        # Message is accepted (not dropped by mention gate), but since it doesn't
        # start with / it's routed as text — no command output, and no agent in this
        # mock setup means no send call either.
        response = get_response_text(discord_adapter)
        assert response is None or "/new" not in response

    async def test_no_mention_in_channel_dropped(self, discord_adapter):
        """Message without @mention in server channel → silently dropped."""
        msg = make_discord_message(content="/help", mentions=[])
        await dispatch(discord_adapter, msg)
        assert get_response_text(discord_adapter) is None

    async def test_dm_no_mention_needed(self, discord_adapter):
        """DMs don't require @mention — /help works directly."""
        dm = make_fake_dm_channel()
        msg = make_discord_message(content="/help", channel=dm, mentions=[])
        await dispatch(discord_adapter, msg)
        response = get_response_text(discord_adapter)
        assert response is not None
        assert "/new" in response


class TestPresetThreadNaming:
    async def test_explicit_task_becomes_human_readable_suffix(self):
        name, starter = DiscordAdapter._build_preset_thread(
            object.__new__(DiscordAdapter),
            "kody-workspace",
            task="orders api",
            message="Please inspect the shipment flow.",
        )

        assert name == "kody-workspace · orders api"
        assert "Initial request:\nPlease inspect the shipment flow." in starter

    async def test_known_task_mode_adds_lifecycle_guidance(self):
        name, starter = DiscordAdapter._build_preset_thread(
            object.__new__(DiscordAdapter),
            "divebase",
            task="seed",
            message="Turn the release checklist into acceptance criteria.",
        )

        assert name == "divebase · seed"
        assert "Task mode: seed" in starter
        assert "Seed Candidate" in starter
        assert "Initial request:\nTurn the release checklist" in starter

    async def test_task_mode_drives_auto_archive_when_user_selects_auto(self):
        assert DiscordAdapter._resolve_thread_auto_archive_duration("seed", 0) == 4320
        assert DiscordAdapter._resolve_thread_auto_archive_duration("incident", 0) == 10080
        assert DiscordAdapter._resolve_thread_auto_archive_duration("archive", 0) == 1440
        assert DiscordAdapter._resolve_thread_auto_archive_duration("custom free text", 0) == 10080

    async def test_explicit_archive_duration_overrides_task_mode_default(self):
        assert DiscordAdapter._resolve_thread_auto_archive_duration("archive", 10080) == 10080
        assert DiscordAdapter._resolve_thread_auto_archive_duration("incident", 60) == 60

    async def test_initial_message_supplies_suffix_when_task_is_empty(self):
        name, _starter = DiscordAdapter._build_preset_thread(
            object.__new__(DiscordAdapter),
            "kamill-init",
            message="Improve Discord thread names from the first request and target metadata.",
        )

        assert name == "kamill-init · Improve Discord thread names from the first request"
        assert len(name) <= 100

    async def test_korean_initial_message_is_preserved_and_trimmed(self):
        name, _starter = DiscordAdapter._build_preset_thread(
            object.__new__(DiscordAdapter),
            "general",
            message="쓰레드 기능을 사용해서 만들어지는 이름이 단순히 레포 이름이라 구분이 어려워",
        )

        assert name.startswith("general · 쓰레드 기능을 사용해서")
        assert len(name) <= 100

    async def test_secret_like_initial_message_does_not_leak_into_thread_name(self):
        name, _starter = DiscordAdapter._build_preset_thread(
            object.__new__(DiscordAdapter),
            "general",
            message="Use API_KEY=DUMMY_VALUE to debug the gateway",
        )

        assert name == "general"

    async def test_main_project_and_kamill_presets_are_available(self):
        adapter = object.__new__(DiscordAdapter)

        kody_name, kody_starter = DiscordAdapter._build_preset_thread(adapter, "kody-workspace")
        ops_name, ops_starter = DiscordAdapter._build_preset_thread(adapter, "kamill-ops")
        forge_name, forge_starter = DiscordAdapter._build_preset_thread(adapter, "kamill-forge")
        init_name, init_starter = DiscordAdapter._build_preset_thread(adapter, "kamill-init")

        assert kody_name == "kody-workspace"
        assert "coordination of kody-frontend/kody-backend work" in kody_starter
        assert ops_name == "kamill-ops"
        assert "Kamill runtime operations" in ops_starter
        assert "Project/product work belongs" in ops_starter
        assert forge_name == "kamill-forge"
        assert "No repo is anchored by default." in forge_starter
        assert "explicit approval" in forge_starter
        assert init_name == "kamill-init"
        assert "pre-project conversation" in init_starter

    async def test_retired_or_consolidated_presets_are_not_available(self):
        adapter = object.__new__(DiscordAdapter)

        for target in [
            "hermes-core",
            "hermes-agent",
            "discord-gateway",
            "kamill-memory-skills",
            "kody-frontend",
            "kody-backend",
        ]:
            with pytest.raises(ValueError, match="Unknown thread preset"):
                DiscordAdapter._build_preset_thread(adapter, target)

    async def test_thread_seed_message_is_short_public_anchor(self):
        seed = DiscordAdapter._build_thread_seed_message("general · test")

        assert seed == "🧵 Kamill thread: **general · test**"
        assert "Repo path" not in seed

    async def test_create_thread_prefers_visible_seed_message_without_public_starter(self):
        adapter = object.__new__(DiscordAdapter)
        thread = SimpleNamespace(id=33333, name="general · test", send=AsyncMock())
        seed_message = SimpleNamespace(create_thread=AsyncMock(return_value=thread))
        parent_channel = SimpleNamespace(id=22222, name="hermes", send=AsyncMock(return_value=seed_message))
        interaction = SimpleNamespace(
            channel=parent_channel,
            user=SimpleNamespace(display_name="tester"),
        )

        result = await DiscordAdapter._create_thread(
            adapter,
            interaction,
            name="general · test",
            message="long starter prompt that should stay synthetic",
            auto_archive_duration=10080,
            seed_message="🧵 Kamill thread: **general · test**",
            post_initial_message=False,
        )

        assert result == {"success": True, "thread_id": "33333", "thread_name": "general · test"}
        parent_channel.send.assert_awaited_once_with("🧵 Kamill thread: **general · test**")
        seed_message.create_thread.assert_awaited_once()
        assert seed_message.create_thread.await_args.kwargs["auto_archive_duration"] == 10080
        thread.send.assert_not_awaited()


class TestAutoThreadingPreservesCommand:
    async def test_command_detected_after_auto_thread(self, discord_adapter, bot_user, monkeypatch):
        """@mention /help in channel with auto-thread → thread created AND command dispatched."""
        monkeypatch.setenv("DISCORD_AUTO_THREAD", "true")
        fake_thread = make_fake_thread(thread_id=90001, name="help")
        msg = make_discord_message(
            content=f"<@{BOT_USER_ID}> /help",
            mentions=[bot_user],
        )

        # Simulate discord.py restoring the original raw content (with mention)
        # after create_thread(), which undoes any prior mention stripping.
        original_content = msg.content

        async def clobber_content(**kwargs):
            msg.content = original_content
            return fake_thread

        msg.create_thread = AsyncMock(side_effect=clobber_content)
        await dispatch(discord_adapter, msg)

        msg.create_thread.assert_awaited_once()
        response = get_response_text(discord_adapter)
        assert response is not None
        assert "/new" in response
