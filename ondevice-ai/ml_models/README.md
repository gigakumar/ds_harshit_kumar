# Bundled model assets# Local Model Storage



This directory contains on-device language models that ship with the packaged automation daemon.  The default profile expects the TinyLlama 1.1B chat model quantized for MLX (`tinyllama-1.1b-chat-q4f16_1`).Place all downloaded or fine-tuned model weights here so they can be deleted or swapped easily. The runtime will look for the following folders by default:



Models are not committed to source control.  Run:- `embeddings/` — sentence embedding models (e.g. `mlx-community/e5-small`).

- `planner/` — instruction-tuned LLM checkpoints for planning actions (e.g. `mlx-community/mistral-7b-instruct-q4_0`).

```- `lora/` — LoRA adapter weights for personalization.

make bundle-models

```You can override the location by setting the `ML_MODELS_DIR` environment variable before starting the automation daemon or runtime. Removing this directory is safe; the system will fall back to deterministic stubs if no models are present.


or

```
python -m tools.fetch_models
```

before building the macOS application to download the weights into this folder.
