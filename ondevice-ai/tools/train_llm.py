#!/usr/bin/env python3
"""Fine-tune the automation planner LLM with LoRA and structured reporting."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import hashlib
import json
import logging
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

try:  # Python ≥3.11
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    tomllib = None  # type: ignore[assignment]

try:  # Optional YAML support when PyYAML is installed.
    import yaml  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - yaml support is optional
    yaml = None

_PROMPT_TEMPLATE = """<s>[SYSTEM] You are an automation planner that emits JSON action lists.\n"""
_PROMPT_TEMPLATE += "[USER] {instruction}\n[ASSISTANT] {output}</s>\n"

_GENERATION_TEMPLATE = """<s>[SYSTEM] You are an automation planner that emits JSON action lists.\n"""
_GENERATION_TEMPLATE += "[USER] {instruction}\n[ASSISTANT] "


@dataclass
class TrainingConfig:
    """Configuration for planner LoRA fine-tuning."""

    model_id: str = "mistralai/Mistral-7B-Instruct-v0.2"
    dataset: Path = Path("data/automation_llm_training.jsonl")
    output_dir: Path = Path("artifacts/llm-adapter")
    val_split: float = 0.1
    epochs: int = 3
    learning_rate: float = 2e-4
    batch_size: int = 1
    gradient_accumulation_steps: int = 4
    lora_r: int = 32
    lora_alpha: int = 64
    lora_dropout: float = 0.05
    max_length: int = 1024
    max_samples: Optional[int] = None
    seed: int = 42
    evaluation_samples: int = 3
    generation_max_tokens: int = 256
    save_total_limit: int = 2
    log_steps: int = 10
    bf16: bool = False
    trust_remote_code: bool = True
    config_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        data = dataclasses.asdict(self)
        data["dataset"] = str(self.dataset)
        data["output_dir"] = str(self.output_dir)
        if self.config_path is not None:
            data["config_path"] = str(self.config_path)
        return data

    def validate(self) -> None:
        if not 0.0 < self.val_split < 1.0:
            raise ValueError("val_split must be between 0 and 1")
        if self.max_samples is not None and self.max_samples <= 0:
            raise ValueError("max_samples must be positive when provided")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.gradient_accumulation_steps <= 0:
            raise ValueError("gradient_accumulation_steps must be positive")
        if self.evaluation_samples < 0:
            raise ValueError("evaluation_samples must be non-negative")
        if self.generation_max_tokens <= 0:
            raise ValueError("generation_max_tokens must be positive")

    @classmethod
    def from_sources(
        cls,
        args: argparse.Namespace,
        config_overrides: Optional[Mapping[str, Any]] = None,
    ) -> "TrainingConfig":
        base_values = {field.name: getattr(cls(), field.name) for field in dataclasses.fields(cls)}
        cli_values = {
            field.name: getattr(args, field.name, None)
            for field in dataclasses.fields(cls)
        }
        normalized_cli = {k: v for k, v in cli_values.items() if v is not None}

        overrides: Dict[str, Any] = {}
        if config_overrides:
            overrides = _normalize_keys(config_overrides)

        merged: Dict[str, Any] = {**base_values, **overrides, **normalized_cli}
        config_path = getattr(args, "config_path", None)
        if config_path is not None:
            merged["config_path"] = config_path

        coerced = _coerce_types(merged)
        config = cls(**coerced)
        config.validate()
        return config


def _normalize_keys(overrides: Mapping[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in overrides.items():
        normalized = key.replace("-", "_")
        if normalized == "training" and isinstance(value, Mapping):
            result.update(_normalize_keys(value))
        else:
            result[normalized] = value
    return result


def _coerce_types(values: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(values)
    if "dataset" in data:
        data["dataset"] = Path(data["dataset"])
    if "output_dir" in data:
        data["output_dir"] = Path(data["output_dir"])
    if "config_path" in data and data["config_path"] is not None:
        data["config_path"] = Path(data["config_path"])
    if "val_split" in data:
        data["val_split"] = float(data["val_split"])
    if "epochs" in data:
        data["epochs"] = int(data["epochs"])
    if "learning_rate" in data:
        data["learning_rate"] = float(data["learning_rate"])
    if "batch_size" in data:
        data["batch_size"] = int(data["batch_size"])
    if "gradient_accumulation_steps" in data:
        data["gradient_accumulation_steps"] = int(data["gradient_accumulation_steps"])
    if "lora_r" in data:
        data["lora_r"] = int(data["lora_r"])
    if "lora_alpha" in data:
        data["lora_alpha"] = int(data["lora_alpha"])
    if "max_length" in data:
        data["max_length"] = int(data["max_length"])
    if "max_samples" in data and data["max_samples"] is not None:
        data["max_samples"] = int(data["max_samples"])
    if "seed" in data:
        data["seed"] = int(data["seed"])
    if "evaluation_samples" in data:
        data["evaluation_samples"] = int(data["evaluation_samples"])
    if "generation_max_tokens" in data:
        data["generation_max_tokens"] = int(data["generation_max_tokens"])
    if "save_total_limit" in data:
        data["save_total_limit"] = int(data["save_total_limit"])
    if "log_steps" in data:
        data["log_steps"] = int(data["log_steps"])
    if "bf16" in data:
        data["bf16"] = bool(data["bf16"])
    if "trust_remote_code" in data:
        data["trust_remote_code"] = bool(data["trust_remote_code"])
    return data


def _load_config_file(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".json", ".jsonc"}:
        return json.loads(path.read_text())
    if suffix in {".toml", ".tml"}:
        if tomllib is None:
            raise RuntimeError("TOML configuration requires Python 3.11+ or the tomli package")
        return tomllib.loads(path.read_text())
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("YAML configuration requested but PyYAML is not installed")
        return yaml.safe_load(path.read_text())
    raise RuntimeError(f"Unsupported config format: {path}")


def _load_optional_dependencies():  # pragma: no cover - exercised in integration tests
    try:
        from datasets import Dataset  # type: ignore[import-untyped]
        from peft import LoraConfig, get_peft_model  # type: ignore[import-untyped]
        from transformers import (  # type: ignore[import-untyped]
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForLanguageModeling,
            Trainer,
            TrainingArguments,
        )
    except Exception as exc:  # pragma: no cover - missing optional deps
        raise SystemExit(
            "Install optional training deps via `pip install -r requirements-train.txt` before running this script."
        ) from exc

    return {
        "Dataset": Dataset,
        "LoraConfig": LoraConfig,
        "get_peft_model": get_peft_model,
        "AutoModelForCausalLM": AutoModelForCausalLM,
        "AutoTokenizer": AutoTokenizer,
        "DataCollatorForLanguageModeling": DataCollatorForLanguageModeling,
        "Trainer": Trainer,
        "TrainingArguments": TrainingArguments,
    }


def _format_prompt(example: Mapping[str, Any]) -> str:
    instruction = example.get("instruction") or example.get("prompt")
    output = example.get("output") or example.get("completion")
    if not instruction or not output:
        raise ValueError(f"Dataset row missing instruction/output: {example}")
    return _PROMPT_TEMPLATE.format(instruction=str(instruction).strip(), output=str(output).strip())


def _format_generation_prompt(example: Mapping[str, Any]) -> str:
    instruction = example.get("instruction") or example.get("prompt")
    if not instruction:
        raise ValueError("Example missing instruction for generation preview")
    return _GENERATION_TEMPLATE.format(instruction=str(instruction).strip())


def _tokenize(tokenizer, example: Mapping[str, Any], *, max_length: int) -> Dict[str, Any]:
    text = _format_prompt(example)
    tokens = tokenizer(text, truncation=True, max_length=max_length)
    tokens["labels"] = tokens["input_ids"].copy()
    return tokens


def _load_jsonl_records(dataset_path: Path) -> List[Dict[str, Any]]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    records: List[Dict[str, Any]] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Dataset rows must be objects (line {line_number})")
            if not record.get("instruction") and not record.get("prompt"):
                raise ValueError(f"Row missing 'instruction' or 'prompt' field (line {line_number})")
            if not record.get("output") and not record.get("completion"):
                raise ValueError(f"Row missing 'output' or 'completion' field (line {line_number})")
            records.append(record)
    if not records:
        raise ValueError("Dataset is empty after filtering blank lines")
    return records


def _dataset_sha256(records: Iterable[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    canonical_rows = [
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        for record in records
    ]
    for row in sorted(canonical_rows):
        digest.update(row)
    return digest.hexdigest()


def _train_validation_split(
    records: List[Dict[str, Any]],
    *,
    val_split: float,
    seed: int,
    max_samples: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if max_samples is not None:
        if max_samples < len(records):
            records = records[:max_samples]
    random.Random(seed).shuffle(records)
    split_index = max(1, int(len(records) * (1 - val_split)))
    train_records = records[:split_index]
    val_records = records[split_index:]
    if not train_records:
        raise ValueError("Not enough data for training after split")
    if not val_records:
        logging.warning("Validation split produced no records; evaluation will be skipped")
    return train_records, val_records


def _prepare_datasets(tokenizer, dataset_modules, config: TrainingConfig, train_records, val_records):
    Dataset = dataset_modules["Dataset"]

    def _tokenizer_map(example: Mapping[str, Any]):
        return _tokenize(tokenizer, example, max_length=config.max_length)

    datasets = {"train": Dataset.from_list(train_records)}
    if val_records:
        datasets["validation"] = Dataset.from_list(val_records)

    tokenized = {}
    for split, dataset in datasets.items():
        tokenized[split] = dataset.map(_tokenizer_map, remove_columns=dataset.column_names)
    return tokenized


def _generate_eval_samples(model, tokenizer, records: List[Dict[str, Any]], config: TrainingConfig) -> List[Dict[str, str]]:
    if not records or config.evaluation_samples == 0:
        return []
    samples: List[Dict[str, str]] = []
    for record in records[: config.evaluation_samples]:
        prompt = _format_generation_prompt(record)
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(model.device)
        generated = model.generate(
            input_ids,
            max_new_tokens=config.generation_max_tokens,
            do_sample=True,
            top_p=0.9,
            temperature=0.8,
        )
        output_tokens = generated[0][input_ids.shape[-1] :]
        decoded = tokenizer.decode(output_tokens, skip_special_tokens=True)
        samples.append(
            {
                "instruction": record.get("instruction") or record.get("prompt") or "",
                "reference": record.get("output") or record.get("completion") or "",
                "generation": decoded.strip(),
            }
        )
    return samples


def _save_manifest(
    output_dir: Path,
    config: TrainingConfig,
    dataset_hash: str,
    metrics: Dict[str, Any],
    samples: List[Dict[str, str]],
) -> Path:
    manifest = {
        "generated_at": _dt.datetime.utcnow().isoformat() + "Z",
        "config": config.to_dict(),
        "dataset_sha256": dataset_hash,
        "metrics": metrics,
        "samples": samples,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def run_training(config: TrainingConfig) -> Dict[str, Any]:  # pragma: no cover - heavy deps exercised via CLI
    deps = _load_optional_dependencies()

    AutoTokenizer = deps["AutoTokenizer"]
    AutoModelForCausalLM = deps["AutoModelForCausalLM"]
    LoraConfig = deps["LoraConfig"]
    get_peft_model = deps["get_peft_model"]
    DataCollatorForLanguageModeling = deps["DataCollatorForLanguageModeling"]
    Trainer = deps["Trainer"]
    TrainingArguments = deps["TrainingArguments"]

    logging.info("Loading dataset from %s", config.dataset)
    records = _load_jsonl_records(config.dataset)
    dataset_hash = _dataset_sha256(records)
    train_records, val_records = _train_validation_split(
        list(records),
        val_split=config.val_split,
        seed=config.seed,
        max_samples=config.max_samples,
    )

    logging.info("Preparing tokenizer and base model: %s", config.model_id)
    tokenizer = AutoTokenizer.from_pretrained(config.model_id, trust_remote_code=config.trust_remote_code)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        config.model_id,
        load_in_8bit=False,
        torch_dtype="auto",
        trust_remote_code=config.trust_remote_code,
    )

    lora_config = deps["LoraConfig"](
        r=config.lora_r,
        lora_alpha=config.lora_alpha,
        lora_dropout=config.lora_dropout,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)

    logging.info("Tokenizing dataset (train=%d, val=%d)", len(train_records), len(val_records))
    tokenized = _prepare_datasets(tokenizer, deps, config, train_records, val_records)

    collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    evaluation_strategy = "epoch" if val_records else "no"
    training_args = TrainingArguments(
        output_dir=str(config.output_dir),
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        num_train_epochs=config.epochs,
        learning_rate=config.learning_rate,
        logging_steps=config.log_steps,
        evaluation_strategy=evaluation_strategy,
        save_strategy="epoch",
        save_total_limit=config.save_total_limit,
        report_to=[],
        seed=config.seed,
        bf16=config.bf16,
        fp16=not config.bf16,
        load_best_model_at_end=bool(val_records),
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized.get("validation"),
        data_collator=collator,
    )

    logging.info("Starting training")
    trainer.train()

    metrics: Dict[str, Any] = {}
    if val_records:
        logging.info("Evaluating on validation split (%d records)", len(val_records))
        eval_metrics = trainer.evaluate()
        metrics.update(eval_metrics)
        if "eval_loss" in eval_metrics and eval_metrics["eval_loss"] is not None:
            try:
                metrics["perplexity"] = float(math.exp(eval_metrics["eval_loss"]))
            except OverflowError:
                metrics["perplexity"] = float("inf")

    logging.info("Saving adapter and tokenizer to %s", config.output_dir)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(str(config.output_dir))
    tokenizer.save_pretrained(str(config.output_dir / "tokenizer"))

    samples = _generate_eval_samples(trainer.model, tokenizer, val_records or train_records, config)
    manifest_path = _save_manifest(config.output_dir, config, dataset_hash, metrics, samples)

    result = {
        "adapter_dir": str(config.output_dir),
        "manifest": str(manifest_path),
        "metrics": metrics,
        "dataset_sha256": dataset_hash,
        "samples": samples,
    }
    return result


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune the automation planner LLM with LoRA")
    parser.add_argument("--config-path", dest="config_path", type=Path, default=None, help="Optional JSON/TOML/YAML config file")
    parser.add_argument("--model-id", dest="model_id", default=None, help="Base Hugging Face model to fine-tune")
    parser.add_argument("--dataset", dest="dataset", type=Path, default=None, help="Path to JSONL dataset")
    parser.add_argument("--output-dir", dest="output_dir", type=Path, default=None, help="Directory to store artifacts")
    parser.add_argument("--val-split", dest="val_split", type=float, default=None, help="Validation split ratio (0-1)")
    parser.add_argument("--epochs", dest="epochs", type=int, default=None, help="Number of training epochs")
    parser.add_argument("--learning-rate", dest="learning_rate", type=float, default=None, help="AdamW learning rate")
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=None, help="Per-device batch size")
    parser.add_argument(
        "--gradient-steps",
        dest="gradient_accumulation_steps",
        type=int,
        default=None,
        help="Gradient accumulation steps",
    )
    parser.add_argument("--lora-r", dest="lora_r", type=int, default=None, help="LoRA rank")
    parser.add_argument("--lora-alpha", dest="lora_alpha", type=int, default=None, help="LoRA alpha")
    parser.add_argument("--lora-dropout", dest="lora_dropout", type=float, default=None, help="LoRA dropout")
    parser.add_argument("--max-length", dest="max_length", type=int, default=None, help="Maximum tokenized sequence length")
    parser.add_argument(
        "--max-samples",
        dest="max_samples",
        type=int,
        default=None,
        help="Limit dataset records (post-validation)",
    )
    parser.add_argument("--seed", dest="seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--evaluation-samples",
        dest="evaluation_samples",
        type=int,
        default=None,
        help="Number of generations to sample for manifest",
    )
    parser.add_argument(
        "--generation-max-tokens",
        dest="generation_max_tokens",
        type=int,
        default=None,
        help="Max new tokens for sample generations",
    )
    parser.add_argument(
        "--save-total-limit",
        dest="save_total_limit",
        type=int,
        default=None,
        help="Max checkpoints to keep",
    )
    parser.add_argument("--log-steps", dest="log_steps", type=int, default=None, help="Trainer logging steps")
    parser.add_argument(
        "--bf16",
        dest="bf16",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable (or disable) bfloat16 training",
    )
    parser.add_argument(
        "--trust-remote-code",
        dest="trust_remote_code",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow custom model code from remote repositories",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    args = parse_args(argv)
    overrides = _load_config_file(getattr(args, "config_path", None))
    config = TrainingConfig.from_sources(args, overrides)

    logging.info("Starting LoRA fine-tune with config: %s", json.dumps(config.to_dict(), indent=2))
    result = run_training(config)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
