"""Runtime secret provider abstraction.

The default provider is environment variables because Cloud Run secret
bindings, docker-compose, systemd, and GitHub Actions can all expose secrets as
env vars. Other providers are optional and degrade to caller defaults when
their backing tool or dependency is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_SOPS_FILE = "secrets.enc.yaml"
DEFAULT_VAULT_KV_PATH = "secret/data/engineer-cafe"


class SecretProvider(Protocol):
    """Provider contract for runtime secrets."""

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the secret value for key, or default when unavailable."""


class EnvSecretProvider:
    """Read secrets from process environment variables."""

    def get(self, key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


class SopsSecretProvider:
    """Read top-level secrets from a SOPS-encrypted JSON/YAML document."""

    def __init__(self, sops_file: str | os.PathLike[str] | None = None) -> None:
        self.sops_file = Path(
            sops_file
            or os.getenv("SOPS_SECRETS_FILE")
            or os.getenv("SECRET_SOPS_FILE")
            or DEFAULT_SOPS_FILE
        )
        self._cache: dict[str, str] | None = None

    def get(self, key: str, default: str | None = None) -> str | None:
        data = self._load()
        return data.get(key, default)

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self.sops_file.exists():
            logger.info("SOPS secrets file does not exist: %s", self.sops_file)
            self._cache = {}
            return self._cache

        try:
            result = subprocess.run(
                ["sops", "--decrypt", str(self.sops_file)],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            logger.warning("sops CLI is not installed; SOPS secrets are unavailable")
            self._cache = {}
            return self._cache
        except subprocess.CalledProcessError as exc:
            logger.warning("sops decrypt failed for %s: %s", self.sops_file, exc.stderr.strip())
            self._cache = {}
            return self._cache

        self._cache = _string_map(_parse_secret_document(result.stdout))
        return self._cache


class GcpSecretProvider:
    """Read GCP secrets from Cloud Run environment bindings.

    This provider intentionally avoids importing Google SDKs so OSS installs and
    backend import checks stay free of GCP client dependencies.
    """

    def __init__(
        self,
        project_id: str | None = None,
        *,
        client: Any | None = None,
        version: str | None = None,
    ) -> None:
        self.project_id = project_id
        self.version = version
        self._client = client

    def get(self, key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


class VaultSecretProvider:
    """Read secrets from a HashiCorp Vault KV path."""

    def __init__(
        self,
        vault_addr: str | None = None,
        token: str | None = None,
        *,
        path: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.vault_addr = (vault_addr or os.getenv("VAULT_ADDR", "")).rstrip("/")
        self.token = token or os.getenv("VAULT_TOKEN", "")
        self.path = (path or os.getenv("VAULT_SECRET_PATH") or DEFAULT_VAULT_KV_PATH).strip("/")
        self._client = client
        self._cache: dict[str, str] | None = None

    def get(self, key: str, default: str | None = None) -> str | None:
        data = self._load()
        return data.get(key, default)

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if self._client is not None:
            self._cache = _string_map(self._read_with_client())
            return self._cache
        if not self.vault_addr or not self.token:
            self._cache = {}
            return self._cache

        url = f"{self.vault_addr}/v1/{self.path}"
        request = Request(url, headers={"X-Vault-Token": self.token})
        try:
            with urlopen(request, timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (
            HTTPError,
            URLError,
            TimeoutError,
            json.JSONDecodeError,
            OSError,
        ) as exc:
            logger.warning("Vault lookup failed for path %s: %s", self.path, exc)
            self._cache = {}
            return self._cache

        self._cache = _string_map(_unwrap_vault_payload(payload))
        return self._cache

    def _read_with_client(self) -> Mapping[str, Any]:
        if hasattr(self._client, "read"):
            payload = self._client.read(self.path)
            return _unwrap_vault_payload(payload or {})
        if hasattr(self._client, "secrets"):
            mount_point, secret_path = _split_vault_kv_path(self.path)
            payload = self._client.secrets.kv.v2.read_secret_version(
                mount_point=mount_point,
                path=secret_path,
            )
            return _unwrap_vault_payload(payload or {})
        return {}


_provider_cache: SecretProvider | None = None


def get_secret_provider() -> SecretProvider:
    """Return the configured secret provider.

    SECRET_BACKEND values:
      - env: process env vars; default and Cloud Run-compatible
      - sops: SOPS encrypted JSON/YAML file
      - gcp: Cloud Run env bindings only
      - vault: HashiCorp Vault KV path
    """

    global _provider_cache
    if _provider_cache is not None:
        return _provider_cache

    backend = os.getenv("SECRET_BACKEND", "env").strip().lower() or "env"
    providers: dict[str, type[SecretProvider]] = {
        "env": EnvSecretProvider,
        "sops": SopsSecretProvider,
        "gcp": GcpSecretProvider,
        "vault": VaultSecretProvider,
    }
    provider_cls = providers.get(backend)
    if provider_cls is None:
        supported = ", ".join(sorted(providers))
        raise ValueError(f"Unsupported SECRET_BACKEND={backend!r}; expected one of: {supported}")

    _provider_cache = provider_cls()
    return _provider_cache


def get(key: str, default: str | None = None) -> str | None:
    """Return one secret from the configured provider."""

    return get_secret_provider().get(key, default)


def reset_secret_provider_cache() -> None:
    """Reset provider cache for tests and runtime reconfiguration."""

    global _provider_cache
    _provider_cache = None


def _parse_secret_document(text: str) -> Mapping[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, Mapping) else {}
    except json.JSONDecodeError:
        pass

    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        return _parse_simple_key_values(text)

    data = yaml.safe_load(text) or {}
    return data if isinstance(data, Mapping) else {}


def _parse_simple_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip("'\"")
    return values


def _string_map(data: Mapping[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in data.items():
        if value is None or isinstance(value, Mapping):
            continue
        values[str(key)] = str(value)
    return values


def _unwrap_vault_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    data = payload.get("data", payload)
    if isinstance(data, Mapping) and isinstance(data.get("data"), Mapping):
        return data["data"]
    return data if isinstance(data, Mapping) else {}


def _split_vault_kv_path(path: str) -> tuple[str, str]:
    parts = path.strip("/").split("/", 2)
    if len(parts) >= 3 and parts[1] == "data":
        return parts[0], parts[2]
    if len(parts) >= 2:
        return parts[0], "/".join(parts[1:])
    return "secret", parts[0] if parts else ""
