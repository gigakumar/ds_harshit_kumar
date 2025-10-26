"""Authentication and token management utilities."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Mapping, Optional

import keyring  # type: ignore[import-untyped]
from cryptography.fernet import Fernet, InvalidToken  # type: ignore[import-untyped]

from core.audit import write_event

_DEFAULT_SERVICE_NAME = "mahi-automation"
_TOKEN_STORE_USERNAME = "token-store"
_ENCRYPTION_KEY_USER = "token-store-key"


@dataclass(slots=True)
class TokenMetadata:
    """Metadata describing an issued token."""

    token: str
    subject: str
    scopes: tuple[str, ...]
    issued_at: float
    expires_at: Optional[float]
    admin: bool = False
    rate_limit_per_minute: int = 120
    last_used_at: Optional[float] = None
    _window_start: float = field(default_factory=lambda: 0.0, repr=False)
    _window_count: int = field(default=0, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "subject": self.subject,
            "scopes": list(self.scopes),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "admin": self.admin,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "last_used_at": self.last_used_at,
            "window_start": self._window_start,
            "window_count": self._window_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TokenMetadata":
        return cls(
            token=str(data.get("token", "")),
            subject=str(data.get("subject", "")),
            scopes=tuple(data.get("scopes", []) or []),
            issued_at=float(data.get("issued_at", time.time())),
            expires_at=float(data["expires_at"]) if data.get("expires_at") is not None else None,
            admin=bool(data.get("admin", False)),
            rate_limit_per_minute=int(data.get("rate_limit_per_minute", 120)),
            last_used_at=float(data["last_used_at"]) if data.get("last_used_at") is not None else None,
            _window_start=float(data.get("window_start", 0.0)),
            _window_count=int(data.get("window_count", 0)),
        )

    def is_expired(self, *, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or time.time()) >= self.expires_at


class TokenStoreError(RuntimeError):
    pass


class TokenStore:
    """Persist issued tokens using keyring or encrypted file storage."""

    def __init__(
        self,
        *,
        backend: str = "keyring",
        keyring_service: str = _DEFAULT_SERVICE_NAME,
        encrypted_file: Optional[Path] = None,
    ) -> None:
        self._backend = backend
        self._service = keyring_service or _DEFAULT_SERVICE_NAME
        self._encrypted_file = encrypted_file
        self._lock = RLock()
        self._memory_payload: Optional[str] = "{}" if backend == "memory" else None

    # ------------------------------------------------------------------
    def load(self) -> dict[str, TokenMetadata]:
        with self._lock:
            payload = self._load_raw()
            data = json.loads(payload) if payload else {}
            tokens: dict[str, TokenMetadata] = {}
            for token_value, entry in data.items():
                try:
                    meta = TokenMetadata.from_dict(entry)
                except Exception:
                    continue
                tokens[token_value] = meta
            return tokens

    def save(self, records: Mapping[str, TokenMetadata]) -> None:
        with self._lock:
            serializable = {token: meta.to_dict() for token, meta in records.items()}
            self._store_raw(json.dumps(serializable))

    # ------------------------------------------------------------------
    def _load_raw(self) -> str:
        if self._backend == "memory":
            return self._memory_payload or "{}"
        if self._backend == "file":
            return self._load_file_ciphertext()
        return keyring.get_password(self._service, _TOKEN_STORE_USERNAME) or "{}"

    def _store_raw(self, payload: str) -> None:
        if self._backend == "memory":
            self._memory_payload = payload
            return
        if self._backend == "file":
            self._store_file_ciphertext(payload)
            return
        keyring.set_password(self._service, _TOKEN_STORE_USERNAME, payload)

    # Encrypted file backend helpers -----------------------------------
    def _ensure_cipher(self) -> Fernet:
        if self._encrypted_file is None:
            raise TokenStoreError("Encrypted file path is required for file backend")
        key = keyring.get_password(self._service, _ENCRYPTION_KEY_USER)
        if not key:
            key = Fernet.generate_key().decode("utf-8")
            keyring.set_password(self._service, _ENCRYPTION_KEY_USER, key)
        return Fernet(key.encode("utf-8"))

    def _load_file_ciphertext(self) -> str:
        cipher = self._ensure_cipher()
        if self._encrypted_file is None or not self._encrypted_file.exists():
            return "{}"
        try:
            ciphertext = self._encrypted_file.read_bytes()
            if not ciphertext:
                return "{}"
            plaintext = cipher.decrypt(ciphertext)
            return plaintext.decode("utf-8")
        except (OSError, InvalidToken):
            raise TokenStoreError("Failed to decrypt token store")

    def _store_file_ciphertext(self, payload: str) -> None:
        cipher = self._ensure_cipher()
        ciphertext = cipher.encrypt(payload.encode("utf-8"))
        assert self._encrypted_file is not None
        self._encrypted_file.parent.mkdir(parents=True, exist_ok=True)
        self._encrypted_file.write_bytes(ciphertext)


class AuthManager:
    """Mint, persist, and validate access tokens."""

    def __init__(
        self,
        *,
        store: TokenStore,
        bootstrap_token: str | None,
        default_ttl: float,
        rate_limit_per_minute: int,
    ) -> None:
        self._store = store
        self._bootstrap_token = bootstrap_token.strip() if bootstrap_token else ""
        self._default_ttl = default_ttl
        self._default_rate_limit = rate_limit_per_minute
        self._records = store.load()
        self._lock = RLock()
        if self._bootstrap_token and self._bootstrap_token not in self._records:
            # Persist bootstrap token with admin privileges but no expiry.
            meta = TokenMetadata(
                token=self._bootstrap_token,
                subject="bootstrap",
                scopes=("admin", "*"),
                issued_at=time.time(),
                expires_at=None,
                admin=True,
                rate_limit_per_minute=self._default_rate_limit,
            )
            self._records[self._bootstrap_token] = meta
            self._store.save(self._records)

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> "AuthManager":
        auth_cfg = config.get("auth", {}) if isinstance(config, Mapping) else {}
        backend = "keyring"
        file_path: Optional[Path] = None
        rate_limit = 120
        default_ttl = 3600.0
        bootstrap = ""
        if isinstance(auth_cfg, Mapping):
            backend = str(auth_cfg.get("token_store", {}).get("backend", "keyring"))
            file_value = auth_cfg.get("token_store", {}).get("file_path")
            if isinstance(file_value, str) and file_value:
                file_path = Path(file_value).expanduser().resolve()
            rate_limit = int(auth_cfg.get("rate_limit_per_minute", rate_limit))
            default_ttl = float(auth_cfg.get("token_ttl_seconds", default_ttl))
            bootstrap = str(auth_cfg.get("bootstrap_token", ""))
        store = TokenStore(
            backend=backend,
            keyring_service=str(auth_cfg.get("token_store", {}).get("keyring_service", _DEFAULT_SERVICE_NAME)),
            encrypted_file=file_path,
        )
        return cls(
            store=store,
            bootstrap_token=bootstrap,
            default_ttl=default_ttl,
            rate_limit_per_minute=rate_limit,
        )

    # ------------------------------------------------------------------
    def mint_token(
        self,
        *,
        subject: str,
        scopes: Iterable[str],
        ttl_seconds: Optional[float] = None,
        admin: bool = False,
        rate_limit_per_minute: Optional[int] = None,
    ) -> TokenMetadata:
        token_value = secrets.token_urlsafe(32)
        issued = time.time()
        if ttl_seconds is None:
            expires_at = issued + self._default_ttl if self._default_ttl > 0 else None
        elif ttl_seconds <= 0:
            expires_at = None
        else:
            expires_at = issued + ttl_seconds
        metadata = TokenMetadata(
            token=token_value,
            subject=subject,
            scopes=tuple(sorted(set(str(scope).strip() for scope in scopes if scope))),
            issued_at=issued,
            expires_at=expires_at,
            admin=admin,
            rate_limit_per_minute=rate_limit_per_minute or self._default_rate_limit,
        )
        with self._lock:
            self._records[token_value] = metadata
            self._store.save(self._records)
        write_event({"type": "auth_token_minted", "subject": subject, "admin": admin})
        return metadata

    def revoke_token(self, token: str) -> bool:
        with self._lock:
            existed = self._records.pop(token, None) is not None
            if existed:
                self._store.save(self._records)
        if existed:
            write_event({"type": "auth_token_revoked", "token": _hash_token(token)})
        return existed

    def validate(self, token: str, *, scope: Optional[str] = None) -> TokenMetadata | None:
        with self._lock:
            metadata = self._records.get(token)
        if metadata is None:
            return None
        if metadata.is_expired():
            return None
        if scope and scope not in metadata.scopes and "*" not in metadata.scopes:
            return None
        return metadata

    def record_usage(self, token: str) -> None:
        now = time.time()
        with self._lock:
            metadata = self._records.get(token)
            if metadata is None:
                return
            window = metadata._window_start
            if now - window >= 60:
                metadata._window_start = now
                metadata._window_count = 0
            metadata._window_count += 1
            metadata.last_used_at = now
            if metadata._window_count > metadata.rate_limit_per_minute:
                raise PermissionError("rate_limit_exceeded")
            self._store.save(self._records)
        write_event({"type": "auth_token_used", "token": _hash_token(token), "ts": now})

    def list_tokens(self) -> List[TokenMetadata]:
        with self._lock:
            return list(self._records.values())

    def rotate_bootstrap(self) -> TokenMetadata:
        if not self._bootstrap_token:
            raise TokenStoreError("Bootstrap token not configured")
        self.revoke_token(self._bootstrap_token)
        metadata = self.mint_token(
            subject="bootstrap",
            scopes=("admin", "*"),
            ttl_seconds=0,
            admin=True,
        )
        self._bootstrap_token = metadata.token
        return metadata

    def ensure_bootstrap_token(self) -> TokenMetadata:
        with self._lock:
            if self._bootstrap_token and self._bootstrap_token in self._records:
                return self._records[self._bootstrap_token]
        metadata = self.mint_token(
            subject="bootstrap",
            scopes=("admin", "*", "query", "index", "status", "plan", "stream"),
            ttl_seconds=0,
            admin=True,
        )
        with self._lock:
            self._bootstrap_token = metadata.token
        return metadata


def _hash_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"token:{token[:4]}…{digest[:16]}"
