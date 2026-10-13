"""Unit tests for ENTC Signal Analysis & Filter Workbench."""

from pathlib import Path
import pytest

from friday.tools.builtin.signal_lab import (
    AnalyzeTransferFunctionTool,
    DesignAnalogFilterTool,
)


def test_design_analog_filter_butterworth():
    """Verify Butterworth filter design computes correct coefficients and component guidance."""
    tool = DesignAnalogFilterTool()

    # 2nd-order lowpass Butterworth at 1000 Hz
    res = tool.execute(filter_type="butterworth", response="lowpass", order=2, cutoff_hz=1000.0)

    assert res["status"] == "designed"
    assert "Butterworth" in res["filter_name"]
    assert res["order"] == 2
    assert len(res["numerator"]) > 0
    assert len(res["denominator"]) == 3  # 2nd order polynomial has 3 coefficients: a2*s^2 + a1*s + a0
    assert "Sallen-Key" in res["component_guidance"]


def test_design_analog_filter_chebyshev_and_bessel():
    """Verify Chebyshev and Bessel filter synthesis."""
    tool = DesignAnalogFilterTool()

    r_cheby = tool.execute(filter_type="chebyshev", response="highpass", order=3, cutoff_hz=500.0)
    assert r_cheby["status"] == "designed"
    assert "Chebyshev" in r_cheby["filter_name"]

    r_bessel = tool.execute(filter_type="bessel", response="lowpass", order=2, cutoff_hz=2000.0)
    assert r_bessel["status"] == "designed"
    assert "Bessel" in r_bessel["filter_name"]


def test_analyze_transfer_function_stable_system(tmp_path):
    """Verify transfer function pole/zero calculation, stability verdict, and plot generation."""
    attachments = tmp_path / "attachments"
    tool = AnalyzeTransferFunctionTool(attachments_dir=str(attachments))

    # H(s) = 1 / (s + 10) -> single pole at s = -10 (Stable)
    num = [1.0]
    den = [1.0, 10.0]

    res = tool.execute(num=num, den=den, plot_type="bode")

    assert res["status"] == "success"
    assert "STABLE" in res["stability"]
    assert len(res["poles"]) == 1
    assert "-10" in res["poles"][0]
    assert res["cutoff_rad_s"] > 0
    assert "markdown_embed" in res
    assert res["markdown_embed"].startswith("![[")

    # Verify plot PNG was actually created and non-empty
    plot_file = Path(res["plot_path"])
    assert plot_file.exists()
    assert plot_file.stat().st_size > 500


def test_analyze_transfer_function_unstable_system(tmp_path):
    """Verify right-half plane pole triggers UNSTABLE verdict."""
    tool = AnalyzeTransferFunctionTool(attachments_dir=str(tmp_path))

    # H(s) = 1 / (s - 5) -> pole at s = +5 (Unstable)
    num = [1.0]
    den = [1.0, -5.0]

    res = tool.execute(num=num, den=den, plot_type="step")
    assert "UNSTABLE" in res["stability"]


def test_analyze_transfer_function_nyquist(tmp_path):
    """Verify Nyquist plot type generation."""
    tool = AnalyzeTransferFunctionTool(attachments_dir=str(tmp_path))

    num = [10.0]
    den = [1.0, 3.0, 2.0]  # (s+1)(s+2)
    res = tool.execute(num=num, den=den, plot_type="nyquist")
    assert res["status"] == "success"
    assert res["plot_type"] == "nyquist"
    assert Path(res["plot_path"]).exists()
