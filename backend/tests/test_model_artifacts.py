"""Guards for the matching-model artifact loader.

Regression context: the bi-encoder folder once held the cross-encoder's
RoBERTa checkpoint. ``AutoModel.from_pretrained`` loaded it without raising,
silently leaving a randomly initialised encoder in place while the API kept
returning 200. ``_verify_checkpoint_covers_model`` exists so that can never
happen again.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch
from safetensors.torch import save_file

from app.ml.matching.inference import (
    MatchingModelsUnavailable,
    _verify_checkpoint_covers_model,
)


class _TinyModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.encoder = torch.nn.Linear(4, 3)
        self.pooler = torch.nn.Linear(3, 3)


def _write_checkpoint(directory: Path, state: dict[str, torch.Tensor]) -> None:
    save_file({key: value.contiguous() for key, value in state.items()}, str(directory / "model.safetensors"))


def test_exact_checkpoint_is_accepted(tmp_path):
    model = _TinyModel()
    _write_checkpoint(tmp_path, model.state_dict())
    _verify_checkpoint_covers_model(tmp_path, model)  # must not raise


def test_missing_tensors_are_rejected(tmp_path):
    model = _TinyModel()
    state = dict(model.state_dict())
    del state["encoder.weight"]
    _write_checkpoint(tmp_path, state)

    with pytest.raises(MatchingModelsUnavailable) as excinfo:
        _verify_checkpoint_covers_model(tmp_path, model)
    assert "encoder.weight" in str(excinfo.value)
    assert "randomly initialised" in str(excinfo.value)


def test_unexpected_tensors_are_rejected(tmp_path):
    model = _TinyModel()
    state = dict(model.state_dict())
    state["classifier.out_proj.weight"] = torch.zeros(1, 3)
    _write_checkpoint(tmp_path, state)

    with pytest.raises(MatchingModelsUnavailable) as excinfo:
        _verify_checkpoint_covers_model(tmp_path, model)
    assert "classifier.out_proj.weight" in str(excinfo.value)


def test_missing_weight_file_is_left_to_from_pretrained(tmp_path):
    # No model.safetensors: the pytorch_model.bin branch is validated
    # elsewhere, so the guard must stay silent rather than raise.
    _verify_checkpoint_covers_model(tmp_path, _TinyModel())


@pytest.mark.skipif(
    not (Path(__file__).parent.parent / "app/ml/matching/artifacts/bi_encoder/model.safetensors").is_file(),
    reason="matching artifacts not provisioned",
)
def test_installed_bi_encoder_matches_its_declared_architecture():
    """The shipped bi-encoder weights must supply every BertModel tensor."""
    from transformers import AutoModel
    from transformers.utils import logging as hf_logging

    hf_logging.set_verbosity_error()
    artifacts = Path(__file__).parent.parent / "app/ml/matching/artifacts"
    model = AutoModel.from_pretrained(str(artifacts / "bi_encoder"))
    assert model.config.hidden_size == 384
    assert model.config.num_hidden_layers == 6
    _verify_checkpoint_covers_model(artifacts / "bi_encoder", model)
