# Planner LLM Training Pipeline

This document describes how to fine-tune the automation planner language model using the refreshed tooling in `tools/train_llm.py`.

## Prerequisites

1. Install the optional training dependencies:
   ```bash
   python -m pip install -r requirements-train.txt
   ```
2. Prepare a JSONL dataset with each row containing `instruction`/`prompt` and `output`/`completion` fields.

## Running a Training Job

You can drive the trainer entirely from the command line:

```bash
python tools/train_llm.py \
  --model-id mistralai/Mistral-7B-Instruct-v0.2 \
  --dataset data/automation_llm_training.jsonl \
  --output-dir artifacts/llm-adapter \
  --val-split 0.1 \
  --epochs 3 \
  --batch-size 1
```

Alternatively, place hyperparameters in a JSON/TOML/YAML file and pass `--config-path path/to/config.json`. Command-line arguments always override config values.

## Artifacts and Reporting

- The fine-tuned LoRA adapter and tokenizer are saved under the chosen `output_dir`.
- A `manifest.json` file captures the configuration, dataset checksum, evaluation metrics, and a handful of sample generations for quick inspection.
- The script prints a JSON payload upon completion that includes the adapter directory, manifest path, and metrics.

## Integration with the Runtime

Copy the adapter directory into `ml_models/lora/` (or the directory pointed to by `ML_MODELS_DIR`). Update your runtime configuration to reference the new adapter path if required.

## Reproducibility Tips

- Use `--seed` to control dataset shuffling and generation sampling.
- Limit experiments to a subset of data with `--max-samples` during rapid iteration.
- Enable bfloat16 kernels on supported hardware via `--bf16` for better throughput.
