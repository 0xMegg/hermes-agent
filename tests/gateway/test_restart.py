"""Tests for gateway restart supervisor detection."""

from gateway import restart


def test_detect_service_manager_systemd(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "unit-123")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)

    assert restart.detect_service_manager() == "systemd"


def test_detect_service_manager_launchd(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("XPC_SERVICE_NAME", "ai.hermes.gateway")

    assert restart.detect_service_manager() == "launchd"


def test_detect_service_manager_launchd_profile_label(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("XPC_SERVICE_NAME", "ai.hermes.gateway-coder")

    assert restart.detect_service_manager() == "launchd"


def test_detect_service_manager_ignores_interactive_macos_xpc_value(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.setenv("XPC_SERVICE_NAME", "0")

    assert restart.detect_service_manager() is None


def test_detect_service_manager_none_for_unsupervised_process(monkeypatch):
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)

    assert restart.detect_service_manager() is None


def test_detect_service_manager_prefers_systemd_when_both_markers_exist(monkeypatch):
    monkeypatch.setenv("INVOCATION_ID", "unit-123")
    monkeypatch.setenv("XPC_SERVICE_NAME", "ai.hermes.gateway")

    assert restart.detect_service_manager() == "systemd"
