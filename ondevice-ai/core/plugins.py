# core/plugins.py
import yaml
from dataclasses import dataclass
from typing import List

@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    scopes: List[str]
    api: str
    signature: str
    min_core_version: str
    capabilities: List[str]

    @staticmethod
    def load(path: str) -> "PluginManifest":
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        # Minimal validation
        required = ["id","name","version","scopes","api","signature","min_core_version","capabilities"]
        for r in required:
            if r not in data:
                raise ValueError(f"Missing field in plugin manifest: {r}")
        sig = data.get("signature","")
        if not isinstance(sig, str) or not sig.startswith("ed25519:"):
            raise ValueError("Invalid signature format; expected 'ed25519:<BASE64SIG>'")
        return PluginManifest(
            id=data["id"], name=data["name"], version=data["version"],
            scopes=list(data["scopes"]), api=data["api"], signature=sig,
            min_core_version=data["min_core_version"], capabilities=list(data["capabilities"]) )
