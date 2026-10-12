"""Unit tests for ObsidianVault file management."""

import pytest
from pathlib import Path
from friday.memory.models import MemoryNode
from friday.memory.obsidian_vault import ObsidianVault, slugify


def test_slugify_windows_safe():
    assert slugify("Digital Signal Processing: Filter Design?") == "Digital-Signal-Processing-Filter-Design"
    assert slugify("Test / Path \\ Bad * Char") == "Test-Path-Bad-Char"


def test_vault_save_and_load(tmp_path: Path):
    vault = ObsidianVault(vault_dir=str(tmp_path))

    node = MemoryNode(
        id="dsp-filters",
        title="DSP Filter Design",
        content="Notes on Butterworth and Chebyshev IIR filters.\nSee [[Fourier Transform]] and [[Bode Plots]].",
        category="entc_coursework",
        tags=["dsp", "signals"],
        links=["Sampling Theorem"],
    )

    saved_path = vault.save_node(node)
    assert Path(saved_path).exists()
    assert saved_path.endswith(".md")

    # Load back
    loaded = vault.load_node_from_file(Path(saved_path))
    assert loaded is not None
    assert loaded.title == "DSP Filter Design"
    assert loaded.category == "entc_coursework"
    assert "dsp" in loaded.tags
    assert "Butterworth" in loaded.content

    # Check wikilinks extraction
    wikilinks = loaded.extract_wikilinks()
    assert "Fourier Transform" in wikilinks
    assert "Bode Plots" in wikilinks
    assert "Sampling Theorem" in wikilinks
