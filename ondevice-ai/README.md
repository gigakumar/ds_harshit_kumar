# ondevice-ai

Minimal local-first assistant runtime with gRPC, deterministic embeddings, and a SwiftUI front-end scaffold.

## Quickstart

Requirements:
- Python 3.11+
- macOS with Xcode (for the SwiftUI client, optional)

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
make proto
```

Launch the automation daemon (gRPC server + MLX-compatible HTTP runtime):

```bash
python automation_daemon.py
```

CLI helpers use the same binary:

```bash
python -m cli.index index "hello world"
python -m cli.index query "hello"
python -m cli.index plan "organise my notes"
```

Run tests:

```bash
pytest -q
```

## Layout

- `proto/assistant.proto` — gRPC schema
- `core/` — vector store, orchestrator, adapter, gRPC server
- `automation_daemon.py` — unified entry (runs gRPC server + HTTP runtime)
- `tools/` — MLX runtime server and utilities
- `cli/` — CLI subcommand runner (`index`, `query`, `plan`)
- `tests/` — unit and e2e tests

## License

MIT

- The HTTP runtime persists documents in-memory, exposes `/documents`, `/query`, `/plan`, `/audit`, and `/plugins`.
- gRPC server stores embeddings in SQLite (`VectorStore`) and logs actions through `core.audit`.

## SwiftUI client

The `swift/` directory contains a Swift Package with basic views. Open the package in Xcode or run:

```bash
open swift/OnDeviceAIApp/Package.swift
```

Ensure the Python daemon is running locally before launching the SwiftUI previews.
