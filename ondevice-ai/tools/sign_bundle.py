# tools/sign_bundle.py
"""Sign a bundle manifest with an ed25519 private key (PyNaCl).

Usage:
  python tools/sign_bundle.py manifest.json <base64_private_key>

Writes the signature into the manifest in-place as field 'ed25519_signature'.
"""
import sys, json, base64

try:
    from nacl.signing import SigningKey
except Exception as e:
    print("PyNaCl required. pip install pynacl", file=sys.stderr)
    sys.exit(2)

def main():
    if len(sys.argv) != 3:
        print("Usage: python tools/sign_bundle.py manifest.json <base64_private_key>", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    sk_b64 = sys.argv[2]
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    body = json.dumps({k: manifest[k] for k in sorted(manifest) if k != "ed25519_signature"},
                      separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    sk = SigningKey(base64.b64decode(sk_b64))
    sig = sk.sign(body).signature
    manifest["ed25519_signature"] = "ed25519:" + base64.b64encode(sig).decode("ascii")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("Signed manifest and updated ed25519_signature")

if __name__ == "__main__":
    main()
