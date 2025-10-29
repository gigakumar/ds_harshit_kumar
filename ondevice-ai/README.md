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

## Open-source LLM planner

The automation runtime now relies on an open-source Hugging Face LLM (defaults to `mistralai/Mistral-7B-Instruct-v0.2`) to draft structured automation plans. The `/predict` endpoint asks the model for a JSON array of actions and gracefully falls back to deterministic heuristics if the call fails or returns unparseable output.

- Configure tokens, model IDs, and embedding model inside `config/automation.yaml` (`model.backend: huggingface`).
- Provide `HUGGINGFACEHUB_API_TOKEN` to authenticate with the Hugging Face Inference API or override `model.huggingface.model_id` to point at a self-hosted endpoint.
- Tests monkeypatch the runtime `generate` hook so you can still run the suite offline.

You can still opt into other planners by switching profiles: `backend: mlx` for fully offline TinyLlama, `backend: ollama` for LAN deployments, and `backend: openai` for GPT-4o mini.

### Fine-tuning the LLM

- Curate instruction/plan pairs in `data/automation_llm_training.jsonl` (JSONL with `instruction`/`output` fields). A starter file is included.
- Install the optional tooling: `pip install -r requirements-train.txt`.
- Run the helper to produce LoRA adapter weights:

	```bash
	python tools/train_llm.py --model-id mistralai/Mistral-7B-Instruct-v0.2 --output-dir artifacts/llm-adapter
	```

- Point `config/automation.yaml` → `model.huggingface.model_id` (and optionally `huggingface.lora_path`) at the fine-tuned weights or merge them back into the base model using the Hugging Face `peft` utilities.

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

Running `make package` also refreshes `dist/OnDeviceAI.dmg` using `tools/build_dmg.sh`. The script now stages a proper macOS installer layout with an Applications alias and inline README guidance. You can tweak the DMG by exporting environment variables before the build:

- `DMG_VOLNAME` – override the mounted volume name (default `OnDeviceAI`).
- `DMG_BACKGROUND_IMAGE` – path to a background image copied into `.background/` (optional).
- `DMG_README_SOURCE` – path to a custom README to copy beside the app; omit to use the autogenerated helper text.
- `DMG_VOLUME_ICON` – `.icns` to apply as the mounted volume icon (requires Xcode command-line tools for `SetFile`).
- `DMG_APPLICATIONS_SYMLINK=false` – opt out of creating the `/Applications` shortcut.

Example:

```bash
DMG_VOLNAME="OnDevice AI Nightly" \
DMG_BACKGROUND_IMAGE="assets/dmg-nightly.png" \
DMG_README_SOURCE="docs/release-notes.txt" \
make package
```

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
