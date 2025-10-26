"""Lightweight runtime gateway registry used by automation daemon and UI."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Iterator, Optional


_PROTOCOLS = {"grpc", "http", "ws", "ipc"}


@dataclass(frozen=True, slots=True)
class RuntimeEndpoint:
    """Represents a single runtime endpoint exposed by the daemon."""

    name: str
    protocol: str
    address: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        proto = self.protocol.lower()
        if proto not in _PROTOCOLS:
            raise ValueError(f"Unsupported protocol '{self.protocol}'.")
        object.__setattr__(self, "protocol", proto)


@dataclass(frozen=True, slots=True)
class GatewayToken:
    """Authentication token issued for runtime clients."""

    value: str
    scopes: tuple[str, ...]
    issued_at: float

    def as_dict(self) -> dict[str, Any]:
        return {"token": self.value, "scopes": list(self.scopes), "issued_at": self.issued_at}


class RuntimeGateway:
    """Thread-safe registry for runtime endpoints and auth tokens."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._endpoints: dict[str, dict[str, RuntimeEndpoint]] = {protocol: {} for protocol in _PROTOCOLS}
        self._tokens: dict[str, GatewayToken] = {}

    # Endpoint management -------------------------------------------------
    def register(self, endpoint: RuntimeEndpoint) -> None:
        with self._lock:
            endpoints = self._endpoints.setdefault(endpoint.protocol, {})
            endpoints[endpoint.name] = endpoint

    def bulk_register(self, endpoints: Iterable[RuntimeEndpoint]) -> None:
        for endpoint in endpoints:
            self.register(endpoint)

    def unregister(self, protocol: str, name: str) -> None:
        with self._lock:
            proto = protocol.lower()
            proto_map = self._endpoints.get(proto)
            if proto_map and name in proto_map:
                del proto_map[name]

    def endpoints(self, protocol: Optional[str] = None) -> list[RuntimeEndpoint]:
        with self._lock:
            if protocol is None:
                return [endpoint for proto in self._endpoints.values() for endpoint in proto.values()]
            proto = protocol.lower()
            proto_map = self._endpoints.get(proto)
            if not proto_map:
                return []
            return list(proto_map.values())

    def find(self, protocol: str, name: str) -> Optional[RuntimeEndpoint]:
        with self._lock:
            return self._endpoints.get(protocol.lower(), {}).get(name)

    def __iter__(self) -> Iterator[RuntimeEndpoint]:
        return iter(self.endpoints())

    # Token management ----------------------------------------------------
    def issue_token(self, *, scopes: Optional[Iterable[str]] = None, length: int = 32) -> GatewayToken:
        value = secrets.token_urlsafe(length)
        granted = tuple(sorted(set(str(scope).strip() for scope in scopes or ())))
        token = GatewayToken(value=value, scopes=granted, issued_at=time.time())
        with self._lock:
            self._tokens[token.value] = token
        return token

    def revoke_token(self, token_value: str) -> bool:
        with self._lock:
            return self._tokens.pop(token_value, None) is not None

    def authenticate(self, token_value: str, *, required_scope: Optional[str] = None) -> bool:
        with self._lock:
            token = self._tokens.get(token_value)
        if token is None:
            return False
        if required_scope is None:
            return True
        return required_scope in token.scopes

    # Serialization -------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "endpoints": {
                    proto: [asdict(endpoint) for endpoint in endpoints.values()]
                    for proto, endpoints in self._endpoints.items()
                },
                "tokens": [token.as_dict() for token in self._tokens.values()],
            }


__all__ = ["RuntimeGateway", "RuntimeEndpoint", "GatewayToken"]
