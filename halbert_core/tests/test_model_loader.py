# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""model/loader.py: ModelConfig.from_file for both the JSON and YAML shapes
it advertises."""

from pathlib import Path

from halbert_core.model.loader import ModelConfig


def test_from_file_loads_yaml(tmp_path):
    # own-bug: loader.py calls yaml.safe_load at the non-.json branch of
    # from_file without ever importing yaml — every .yml/.yaml config raises
    # NameError instead of loading.
    path = tmp_path / "model.yml"
    path.write_text("runtime: ollama\nmodel_id: family-a:8b\n")
    config = ModelConfig.from_file(path)
    assert config.runtime == "ollama"
    assert config.model_id == "family-a:8b"


def test_from_file_loads_json(tmp_path):
    path = tmp_path / "model.json"
    path.write_text('{"runtime": "ollama", "model_id": "family-a:8b"}')
    config = ModelConfig.from_file(path)
    assert config.runtime == "ollama"
    assert config.model_id == "family-a:8b"
