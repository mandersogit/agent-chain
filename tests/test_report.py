"""Tests for report generation."""

import datetime as _datetime
import json as _json
import pathlib as _pathlib

import agent_chain.chain as _chain
import agent_chain.report as _report
import agent_chain.runner as _runner
import agent_chain.types as _types

_FIXTURES = _pathlib.Path(__file__).parent / "fixtures"
_UTC = _datetime.UTC


def _make_step_result(
    name: str = "step1",
    step_type: str = "verify",
    agent: str = "none",
    status: _types.StepStatus = _types.StepStatus.SUCCESS,
    wall_time: float = 10.0,
    exit_code: int | None = 0,
    telemetry: _types.TelemetryRecord | None = None,
    gate_result: dict[str, object] | None = None,
) -> _runner.StepResult:
    return _runner.StepResult(
        name=name,
        step_type=step_type,
        agent=agent,
        status=status,
        wall_time_seconds=wall_time,
        exit_code=exit_code,
        output_path=None,
        telemetry_path=None,
        telemetry=telemetry,
        gate_result=gate_result,
    )


class TestBuildReport:
    """Tests for report dict construction."""

    def test_full_success_report(self, tmp_path: _pathlib.Path) -> None:
        """Fully successful chain produces status='success'."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report = _report.build_report(chain, tmp_path, started, finished, results)
        assert report["schema_version"] == 1
        assert report["chain"]["status"] == "success"  # type: ignore[index]
        assert len(report["steps"]) == 1  # type: ignore[arg-type]

    def test_failed_step_produces_failed_status(self, tmp_path: _pathlib.Path) -> None:
        """Chain with a failed step produces status='failed'."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(status=_types.StepStatus.FAILED)]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report = _report.build_report(chain, tmp_path, started, finished, results)
        assert report["chain"]["status"] == "failed"  # type: ignore[index]

    def test_interrupted_produces_interrupted_status(self, tmp_path: _pathlib.Path) -> None:
        """Interrupted chain produces status='interrupted'."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(status=_types.StepStatus.INTERRUPTED)]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 1, 0, tzinfo=_UTC)

        report = _report.build_report(chain, tmp_path, started, finished, results)
        assert report["chain"]["status"] == "interrupted"  # type: ignore[index]

    def test_totals_include_step_counts(self, tmp_path: _pathlib.Path) -> None:
        """Report totals include steps_completed, steps_failed, steps_skipped."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [
            _make_step_result(name="s1", status=_types.StepStatus.SUCCESS),
        ]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report = _report.build_report(chain, tmp_path, started, finished, results)
        totals = report["totals"]
        assert totals["steps_completed"] == 1  # type: ignore[index]
        assert totals["steps_failed"] == 0  # type: ignore[index]
        assert totals["steps_skipped"] == 0  # type: ignore[index]

    def test_partial_failure_counts(self, tmp_path: _pathlib.Path) -> None:
        """Partial failure counts completed, failed, and skipped steps correctly."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [
            _make_step_result(name="s1", status=_types.StepStatus.SUCCESS),
            _make_step_result(name="s2", status=_types.StepStatus.FAILED),
            _make_step_result(name="s3", status=_types.StepStatus.NOT_STARTED),
        ]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report = _report.build_report(chain, tmp_path, started, finished, results)
        totals = report["totals"]
        assert totals["steps_completed"] == 1  # type: ignore[index]
        assert totals["steps_failed"] == 1  # type: ignore[index]
        assert totals["steps_skipped"] == 1  # type: ignore[index]


class TestWriteReport:
    """Tests for writing report.json and DONE sentinel."""

    def test_write_creates_report_json(self, tmp_path: _pathlib.Path) -> None:
        """write_report creates a valid report.json."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report_path = _report.write_report(chain, tmp_path, started, finished, results)
        assert report_path.exists()
        data = _json.loads(report_path.read_text())
        assert data["schema_version"] == 1

    def test_write_creates_done_sentinel(self, tmp_path: _pathlib.Path) -> None:
        """write_report creates a DONE sentinel file."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        _report.write_report(chain, tmp_path, started, finished, results)
        sentinel = tmp_path / "DONE"
        assert sentinel.exists()
        assert sentinel.read_text().strip() == "success"

    def test_sentinel_reflects_failure(self, tmp_path: _pathlib.Path) -> None:
        """DONE sentinel contains failure status for failed chains."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(status=_types.StepStatus.FAILED)]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 1, 0, tzinfo=_UTC)

        _report.write_report(chain, tmp_path, started, finished, results)
        sentinel = tmp_path / "DONE"
        assert sentinel.read_text().strip() == "failed"


class TestRenderReport:
    """Tests for report rendering."""

    def test_render_text_format(self, tmp_path: _pathlib.Path) -> None:
        """Text format renders chain name and status."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report_path = _report.write_report(chain, tmp_path, started, finished, results)
        rendered = _report.render_report(report_path, output_format="text")
        assert "minimal" in rendered
        assert "success" in rendered

    def test_render_json_format(self, tmp_path: _pathlib.Path) -> None:
        """JSON format renders valid JSON."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report_path = _report.write_report(chain, tmp_path, started, finished, results)
        rendered = _report.render_report(report_path, output_format="json")
        data = _json.loads(rendered)
        assert data["schema_version"] == 1

    def test_render_markdown_format(self, tmp_path: _pathlib.Path) -> None:
        """Markdown format includes # headers."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        results = [_make_step_result(name="check")]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report_path = _report.write_report(chain, tmp_path, started, finished, results)
        rendered = _report.render_report(report_path, output_format="markdown")
        assert "# Chain Report" in rendered

    def test_render_with_telemetry(self, tmp_path: _pathlib.Path) -> None:
        """include_telemetry shows token details."""
        chain = _chain.load(_FIXTURES / "minimal_chain.toml")
        telemetry = _types.TelemetryRecord(
            fresh_input_tokens=100,
            cached_input_tokens=200,
            output_tokens=50,
            total_input_tokens=300,
            num_turns=5,
            wall_time_seconds=30.0,
            shadow_cost_usd=1.50,
        )
        results = [_make_step_result(name="check", telemetry=telemetry)]
        started = _datetime.datetime(2026, 2, 25, 14, 0, 0, tzinfo=_UTC)
        finished = _datetime.datetime(2026, 2, 25, 14, 5, 0, tzinfo=_UTC)

        report_path = _report.write_report(chain, tmp_path, started, finished, results)
        rendered = _report.render_report(
            report_path, output_format="text", include_telemetry=True
        )
        assert "Tokens:" in rendered
        assert "Turns:" in rendered
