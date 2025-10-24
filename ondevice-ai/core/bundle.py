"""Model bundle manifest verification utilities.

Bundle layout (zip):
  - model.(mlxq|onnx)
  - tokenizer.json
  - config.json
  - adapters/*.lora
  - manifest.json { version, sha256, ed25519_signature }
"""
import base64, hashlib, json
from typing import Dict

def _parse_sig(sig: str) -> bytes:
    if not isinstance(sig, str) or not sig.startswith("ed25519:"):
        raise ValueError("Invalid signature field; expected 'ed25519:<BASE64SIG>'")
    b64 = sig.split(":", 1)[1]
    return base64.b64decode(b64)

def verify_manifest_signature(manifest: Dict, pubkey_b64: str) -> bool:
    """Verify ed25519 signature on manifest using optional PyNaCl.

    Returns True if signature verifies; False if PyNaCl is absent or verification fails.
    """
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except Exception:
        # PyNaCl not available; cannot verify
        return False

    sig = _parse_sig(manifest.get("ed25519_signature", ""))
    body = json.dumps({k: manifest[k] for k in sorted(manifest) if k != "ed25519_signature"},
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    try:
        vk = VerifyKey(base64.b64decode(pubkey_b64))
        vk.verify(body, sig)
        return True
    except Exception:
        return False

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
