from __future__ import annotations

import subprocess

import pytest

from backend.utils import secrets


@pytest.fixture(autouse=True)
def reset_provider_cache():
    secrets.reset_secret_provider_cache()
    yield
    secrets.reset_secret_provider_cache()


def test_env_secret_provider_reads_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-key")

    provider = secrets.EnvSecretProvider()

    assert provider.get("OPENROUTER_API_KEY") == "env-key"
    assert provider.get("MISSING_SECRET", "fallback") == "fallback"


def test_sops_secret_provider_decrypts_json(monkeypatch, tmp_path):
    sops_file = tmp_path / "secrets.enc.yaml"
    sops_file.write_text("encrypted", encoding="utf-8")

    def fake_run(*args, **kwargs):
        assert args[0] == ["sops", "--decrypt", str(sops_file)]
        assert kwargs["check"] is True
        return subprocess.CompletedProcess(args[0], 0, stdout='{"SUPABASE_KEY": "sops-key"}')

    monkeypatch.setattr(secrets.subprocess, "run", fake_run)

    provider = secrets.SopsSecretProvider(sops_file)

    assert provider.get("SUPABASE_KEY") == "sops-key"
    assert provider.get("MISSING_SECRET", "fallback") == "fallback"


def test_gcp_secret_provider_reads_cloud_run_env_binding(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://bound.example")

    provider = secrets.GcpSecretProvider()

    assert provider.get("SUPABASE_URL") == "https://bound.example"
    assert provider.get("MISSING_SECRET", "fallback") == "fallback"


def test_vault_secret_provider_reads_kv_payload():
    class FakeVaultClient:
        def read(self, path: str):
            assert path == "secret/data/engineer-cafe"
            return {"data": {"data": {"EVENT_SHEET_GAS_TOKEN": "vault-token"}}}

    provider = secrets.VaultSecretProvider(
        vault_addr="https://vault.example",
        token="token",
        client=FakeVaultClient(),
    )

    assert provider.get("EVENT_SHEET_GAS_TOKEN") == "vault-token"
    assert provider.get("MISSING_SECRET", "fallback") == "fallback"


def test_get_secret_provider_rejects_unknown_backend(monkeypatch):
    monkeypatch.setenv("SECRET_BACKEND", "bogus")

    with pytest.raises(ValueError, match="Unsupported SECRET_BACKEND"):
        secrets.get_secret_provider()
