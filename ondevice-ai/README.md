# ondevice-ai

Local-first automation stack with an opinionated SwiftUI client, configurable model profiles, and an offline-first MLX runtime that ships as part of the macOS app bundle.

## Features

- 📦 **Self-contained packaging** – package the automation daemon, configuration, plugins, and bundled TinyLlama weights into a single `.app`.
- 🧠 **Model profiles** – toggle between the bundled TinyLlama model, the on-device planner brain, an Ollama host, or OpenAI GPT-4o-mini directly from Settings.
- 🕹️ **Automation dashboard** – responsive quick actions, live permission footprint, and model status at a glance.
- 🗂️ **Knowledge console** – index raw snippets from the UI, semantic search, and document drill-down with adaptive layout.
- 🧰 **Planning controls** – adjust temperature, token budget, and knowledge grounding when generating automation plans.

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
python -m cli.index diagnostics --output diagnostics.zip
python -m cli.index daemon start --set model.backend=ollama
python -m cli.index daemon status
python -m cli.index daemon stop
```

The daemon supervisor runs automatically and writes logs/state into `~/.mahi/` by default. Use `python -m cli.index daemon status` to view the supervising PID, restart counters, and child PID.

### Configuration overrides

- **Environment variables:** keys that begin with `MAHI_CFG__` update individual paths (e.g. `MAHI_CFG__MODEL__BACKEND=ollama`). Secrets can be injected with `MAHI_SECRET__` or JSON payloads via `MAHI_CONFIG_OVERRIDES` / `MAHI_SECRET_OVERRIDES`. Secret-derived values are applied at runtime and stripped before configs are persisted.
- **CLI overrides:** `daemon start`/`daemon restart` accept repeated `--set section.key=value` flags plus `--secret section.key=ENVVAR` to merge non-secret and secret overrides when spawning the supervisor.

### Continuous integration

Pushing to `main` or opening a pull request triggers `.github/workflows/ci.yml`, which installs requirements on macOS and executes `pytest ondevice-ai/tests` to keep the project green.

Run tests:

```bash
pytest -q
```

## Local planner brain

The default runtime now ships with a lightweight ML classifier that maps natural language goals onto capability-aware automation plans. The planner lives in `core/local_planner.py` and is bundled with labeled training data in `ml_models/planner/training_data.json`.

- Goals are vectorized with a hashed embedding and classified against template centroids.
- Each template renders a structured sequence of `system.*` or `browser.*` actions with JSON payloads ready for the `SystemAgent`.
- The HTTP runtime exposes the planner through `/predict`, and the orchestrator consumes it via the existing `ModelAdapter` without additional wiring.

You can switch to the pure rule-based engine or remote models by updating `config/automation.yaml`:

```yaml
model:
	backend: planner   # or mlx, ollama, openai
	mode: ml
```

Extend the planner by adding labeled examples to `training_data.json` or by swapping in a custom dataset path when constructing `LocalPlannerModel`.

## Bundled model workflow

The default profile targets TinyLlama 1.1B chat (quantized for MLX). Two options exist:

- **Lazy download (default)** – the runtime detects missing weights on first launch and fetches them into `~/.mahi/models/tinyllama-1.1b-chat-q4f16_1`. Set `HUGGINGFACE_TOKEN` (or run `huggingface-cli login`) if the repo requires authentication.
- **Eager download** – stage the weights ahead of time for offline packaging:

	```bash
	make bundle-models
	```

	Optionally use `ML_MODELS_DIR=/custom/path make bundle-models` to control the staging directory. The runtime still resolves `bundle://` URLs to the same location.

## Package the automation daemon

1. Ensure dependencies are installed (`pip install -r requirements.txt`).
2. Build the app bundle with PyInstaller: `make package`.
3. (Optional) Bundle the TinyLlama weights inside the `.app`: `make package-with-models` (requires Hugging Face auth as described above).

The resulting `dist/OnDeviceAI.app` contains:

- `ml_models/` weights for the TinyLlama profile.
- `config/automation.yaml` and editable profiles.
- `plugins/` manifests.
- (Optional) `swift/OnDeviceAIApp/dist` assets if you build the Swift UI as a web wrapper.

> ℹ️ **Repository artifact split** – GitHub enforces a 100 MB limit, so `artifacts/OnDeviceAIApp.dmg` ships as two chunks: `OnDeviceAIApp.dmg.part01` and `OnDeviceAIApp.dmg.part02`. Reconstitute the DMG before signing or distribution:

```bash
cat artifacts/OnDeviceAIApp.dmg.part01 artifacts/OnDeviceAIApp.dmg.part02 > artifacts/OnDeviceAIApp.dmg
shasum -a 256 artifacts/OnDeviceAIApp.dmg && cat artifacts/OnDeviceAIApp.dmg.sha256
```

The SHA256 hash should match the value stored in `OnDeviceAIApp.dmg.sha256`.

## Refined SwiftUI client

- **Planner** – goal templates carousel, sliders for temperature/tokens, and knowledge toggle.
- **Knowledge** – inline text editor to index new snippets, adaptive document grid, and details pane.
- **Automation dashboard** – responsive quick actions, backend model summary, and permission footprint.
- **Settings** – live daemon status, permission toggles, and model profile selector that persists to `automation.yaml`.

## Layout

- `proto/assistant.proto` — gRPC schema
- `core/` — vector store, orchestrator, adapter, gRPC server
- `automation_daemon.py` — unified entry (runs gRPC server + HTTP runtime)
- `tools/` — MLX runtime server and utilities
- `ml_models/` — bundled TinyLlama weights staged for packaging
- `cli/` — CLI subcommand runner (`index`, `query`, `plan`)
- `tests/` — unit and e2e tests
- `swift/` — Swift Package for the macOS front-end (`OnDeviceAIApp`)
- `packaging/` — PyInstaller spec for producing `OnDeviceAI.app`

## License

MIT

- The HTTP runtime persists documents in-memory, exposes `/documents`, `/query`, `/plan`, `/audit`, and `/plugins`.
- gRPC server stores embeddings in SQLite (`VectorStore`) and logs actions through `core.audit`.

## SwiftUI client

The `swift/` directory contains the Swift Package. Open it in Xcode or run:

```bash
open swift/OnDeviceAIApp/Package.swift
```

Ensure the Python daemon is running locally before launching the SwiftUI previews.
