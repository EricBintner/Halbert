# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""U4-08 — the NVIDIA driver/CUDA compatibility reference is reachable.

``data/knowledge/linux/nvidia_cuda_compatibility.md`` (added in ``162f3965``)
sat in a directory nothing stages or indexes: the real corpus lives under
``data/{linux,macos,bsd,common}`` and is mirrored into the SourcePrep staging
tree by ``rag/jsonl_to_markdown.py::convert_corpus``, which only discovers
``*.jsonl`` files under ``data/`` — never a bare ``.md`` file, and never one
sitting in a sibling directory the discovery walk does not even reach. The
GPU specialist prompt (``dashboard/routes/gpu.py::_build_diagnostic_prompt``)
told the model to retrieve driver/CUDA compatibility facts from the host
knowledge scope; there was nothing there to retrieve.

This is the quality-gate half of that fix (a live retrieval query needs the
SourcePrep daemon and a rebuilt index, which is a founder-scheduled step, not
something this test suite triggers — see the U4-08 note in
RESULTS-SONNET-05-*.md). What IS provable without the daemon: the content now
lives at a path the real staging pipeline's own discovery function actually
walks, and running that pipeline's conversion step on it (not the daemon,
just the local markdown-generation function) produces a staged document
carrying the current 2026 matrix.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RECORD_PATH = DATA_DIR / "linux" / "nvidia-docs" / "nvidia_cuda_compatibility.jsonl"


def test_the_old_dead_directory_is_gone():
    """Nothing under data/knowledge/ any more — the whole reason this was
    unreachable was that convert_corpus never walks it (it walks data/, but
    the old file's problem was never being staged as *content*, not the
    directory name itself — the more important assertion is the positive one
    below). Still worth pinning: a stray sibling tree parallel to the real
    corpus root is exactly how this kind of thing recurs."""
    assert not (DATA_DIR / "knowledge").exists()


def test_the_record_lives_under_the_real_corpus_root():
    """linux/nvidia-docs/ is already a path convert_corpus's rglob("*.jsonl")
    over data/ actually walks (it holds the pre-existing scraped
    nvidia_cuda_docs.jsonl) and is already listed in data/manifest.json's
    vendor_and_distro_docs.paths — no new staging wiring was needed, only the
    file being in the tree that wiring already covers."""
    assert RECORD_PATH.exists()
    assert RECORD_PATH in sorted(DATA_DIR.rglob("*.jsonl"))


def test_the_record_is_a_well_formed_corpus_document():
    line = RECORD_PATH.read_text(encoding="utf-8").strip()
    assert line.count("\n") == 0, "one record per line — this file should hold exactly one"
    record = json.loads(line)
    for field in ("id", "url", "title", "content", "source", "category", "tags", "scraped_at"):
        assert record.get(field), f"missing or empty {field!r}"
    # First-party curated content, not scraped — same convention macos_support
    # uses (data/macos/support/macos_command_guides.jsonl).
    assert record["license_spdx"] == "LicenseRef-Halbert-Corpus-1.0"
    assert record["metadata"]["authored_by"] == "halbert"


def test_the_matrix_is_current_to_2026():
    """The plan (.handoff/GPU-DEEP-SCAN-REBUILD-PLAN-2026-08-29.md Step 7) calls
    for 580.x / CUDA 13.0 as the newest production branch; the doc as
    originally committed topped out at 575.x / CUDA 12.8 (dev/beta)."""
    record = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
    content = record["content"]
    assert "580.x" in content
    assert "13.0" in content
    assert "2026" in content
    # The row that used to be the top of the table, now demoted to a
    # production (not dev/beta) branch a rung below 580.x.
    assert "| 575.x | 12.8 | Production |" in content


def test_the_gpu_specialist_prompt_points_at_the_real_path():
    """dashboard/routes/gpu.py's docstring told the model where the specialist
    retrieves this from; it must not claim the dead path is where the
    specialist actually finds it any more (a historical footnote mentioning
    the old path is fine — asserting it is gone entirely is not, since that
    breaks the moment someone adds a change-log note)."""
    gpu_py = (
        REPO_ROOT
        / "halbert_core"
        / "halbert_core"
        / "dashboard"
        / "routes"
        / "gpu.py"
    ).read_text(encoding="utf-8")
    assert "moved to the knowledge base (data/knowledge" not in gpu_py, (
        "still claims the dead data/knowledge/ path is the current location"
    )
    assert "data/linux/nvidia-docs/" in gpu_py


def test_convert_jsonl_file_stages_it_with_the_current_matrix(tmp_path):
    """Exercises the REAL staging function (not the daemon) end to end: feed
    it this exact file, the same way convert_corpus would when it walks
    data/, and confirm the generated markdown — what SourcePrep would
    actually index — carries the 2026 matrix, not a stale or missing one."""
    pytest.importorskip("yaml")  # jsonl_to_markdown pulls in halbert_core.utils.paths
    from halbert_core.rag.jsonl_to_markdown import convert_jsonl_file

    staged = convert_jsonl_file(RECORD_PATH, tmp_path)
    assert staged, "convert_jsonl_file produced no output for the record"

    combined = "\n".join(p.read_text(encoding="utf-8") for p in staged)
    assert "NVIDIA Driver / CUDA Compatibility Reference" in combined
    assert "580.x" in combined
    assert "13.0" in combined
    # The meta-comment convert_jsonl_file emits is what lets the daemon's
    # scope filter route a query here at all (source/category tagging).
    assert "source: halbert-linux-gpu-guides" in combined
    assert "category: gpu_reference" in combined
