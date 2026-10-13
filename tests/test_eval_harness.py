"""Unit test for the offline deterministic evaluation runner."""

from pathlib import Path
from evals.run_evals import EvalRunner


def test_eval_runner_passes_all_benchmarks():
    """Verify EvalRunner executes all 20 benchmarks cleanly in under 5.0 seconds."""
    runner = EvalRunner()
    report = runner.run_all()

    assert report["total_evals"] == 20
    assert report["passed"] == 20
    assert report["failed"] == 0
    assert report["total_duration_seconds"] < 5.0

    report_file = Path("evals/latest_report.json")
    assert report_file.exists()
