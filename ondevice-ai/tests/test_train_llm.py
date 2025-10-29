from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

import pytest

from tools import train_llm


def _build_args(**overrides: object) -> argparse.Namespace:
    data: dict[str, object | None] = {
        field.name: None for field in dataclasses.fields(train_llm.TrainingConfig)
    }
    for key, value in overrides.items():
        data[key] = value
    return argparse.Namespace(**data)


def test_load_jsonl_records_success(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.jsonl"
    rows = [
        {
            "instruction": "Do thing",
            "output": "[{\"name\": \"system.shell.run\"}]",
        },
        {
            "prompt": "Another instruction",
            "completion": "[{\"name\": \"system.browser.navigate\"}]",
        },
    ]
    dataset.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    records = train_llm._load_jsonl_records(dataset)

    assert len(records) == 2
    assert records[0]["instruction"] == "Do thing"
    assert records[1]["completion"].startswith("[")


def test_load_jsonl_records_validation(tmp_path: Path) -> None:
    dataset = tmp_path / "bad.jsonl"
    dataset.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError):
        train_llm._load_jsonl_records(dataset)


def test_dataset_sha256_is_deterministic(tmp_path: Path) -> None:
    records = [
        {"instruction": "a", "output": "b"},
        {"instruction": "c", "output": "d"},
    ]
    first = train_llm._dataset_sha256(records)
    second = train_llm._dataset_sha256(list(reversed(records)))
    assert first == second


def test_train_validation_split_respects_max_samples() -> None:
    records = [{"instruction": str(i), "output": "x"} for i in range(20)]
    train, val = train_llm._train_validation_split(records, val_split=0.2, seed=123, max_samples=10)
    assert len(train) + len(val) == 10
    assert len(val) > 0


def test_training_config_merges_config_file_overrides(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"training": {"epochs": 7, "batch_size": 2}}), encoding="utf-8")

    args = _build_args(config_path=config_file)
    overrides = train_llm._load_config_file(args.config_path)
    config = train_llm.TrainingConfig.from_sources(args, overrides)

    assert config.epochs == 7
    assert config.batch_size == 2


def test_training_config_cli_wins_over_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"epochs": 1, "batch_size": 1}), encoding="utf-8")

    args = _build_args(config_path=config_file, epochs=4)
    overrides = train_llm._load_config_file(args.config_path)
    config = train_llm.TrainingConfig.from_sources(args, overrides)

    assert config.epochs == 4
    assert config.batch_size == 1
