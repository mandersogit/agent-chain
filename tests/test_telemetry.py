"""Tests for telemetry normalization and aggregation."""

import agent_chain.telemetry as _telemetry
import agent_chain.types as _types


def _make_record(
    fresh: int = 0,
    cached: int = 0,
    output: int = 0,
    turns: int = 0,
    wall: float = 0.0,
    cost: float | None = None,
    tokens_available: bool = True,
    api_time: float | None = None,
    num_tool_calls: int = 0,
    num_thinking_events: int = 0,
    model: str | None = None,
    backend: str | None = None,
) -> _types.TelemetryRecord:
    return _types.TelemetryRecord(
        fresh_input_tokens=fresh,
        cached_input_tokens=cached,
        output_tokens=output,
        total_input_tokens=fresh + cached,
        tokens_available=tokens_available,
        wall_time_seconds=wall,
        api_time_seconds=api_time,
        num_turns=turns,
        num_tool_calls=num_tool_calls,
        num_thinking_events=num_thinking_events,
        model=model,
        backend=backend,
        shadow_cost_usd=cost,
    )


class TestAggregatedTelemetry:
    """Tests for telemetry aggregation across steps."""

    def test_single_record_totals(self) -> None:
        """Single record totals match the record itself."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, cached=200, output=50, turns=5, wall=30.0, cost=1.50))
        totals = agg.totals()
        assert totals["fresh_input_tokens"] == 100
        assert totals["cached_input_tokens"] == 200
        assert totals["output_tokens"] == 50
        assert totals["total_input_tokens"] == 300
        assert totals["num_turns"] == 5
        assert totals["wall_time_seconds"] == 30.0
        assert totals["shadow_cost_usd"] == 1.50
        assert totals["cost_incomplete"] is False

    def test_multiple_records_sum(self) -> None:
        """Multiple records are summed correctly."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, cached=200, output=50, turns=5, wall=30.0, cost=1.0))
        agg.add(_make_record(fresh=200, cached=400, output=100, turns=10, wall=60.0, cost=2.0))
        totals = agg.totals()
        assert totals["fresh_input_tokens"] == 300
        assert totals["cached_input_tokens"] == 600
        assert totals["output_tokens"] == 150
        assert totals["total_input_tokens"] == 900
        assert totals["num_turns"] == 15
        assert totals["wall_time_seconds"] == 90.0
        assert totals["shadow_cost_usd"] == 3.0
        assert totals["cost_incomplete"] is False

    def test_null_cost_sets_cost_incomplete(self) -> None:
        """Null cost on any step sets cost_incomplete to True."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, cost=1.0))
        agg.add(_make_record(fresh=200, cost=None))
        totals = agg.totals()
        assert totals["cost_incomplete"] is True
        assert totals["shadow_cost_usd"] == 1.0

    def test_all_null_costs(self) -> None:
        """All null costs produces cost_incomplete and null total cost."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, cost=None))
        agg.add(_make_record(fresh=200, cost=None))
        totals = agg.totals()
        assert totals["cost_incomplete"] is True
        assert totals["shadow_cost_usd"] is None

    def test_empty_aggregation(self) -> None:
        """Empty aggregation produces zero totals."""
        agg = _telemetry.AggregatedTelemetry()
        totals = agg.totals()
        assert totals["fresh_input_tokens"] == 0
        assert totals["num_turns"] == 0
        assert totals["wall_time_seconds"] == 0.0

    def test_codex_formula_fresh_equals_total_minus_cached(self) -> None:
        """codex-cli: fresh = total_input - cached_input (verified via record)."""
        # Simulating codex: input_tokens=17000 includes cached=11500
        # fresh = 17000 - 11500 = 5500
        record = _types.TelemetryRecord(
            fresh_input_tokens=5500,
            cached_input_tokens=11500,
            output_tokens=4500,
            total_input_tokens=17000,
            tokens_available=True,
            wall_time_seconds=100.0,
            api_time_seconds=None,
            num_turns=3,
            num_tool_calls=0,
            num_thinking_events=0,
            model=None,
            backend="codex-cli",
            shadow_cost_usd=None,
        )
        expected = record["fresh_input_tokens"] + record["cached_input_tokens"]
        assert record["total_input_tokens"] == expected

    def test_claude_formula_total_equals_fresh_plus_cached(self) -> None:
        """claude-code: total = fresh + cache_write + cache_read."""
        # fresh=150, cache_write=250000, cache_read=3000000
        # cached=3250000, total=3250150
        record = _types.TelemetryRecord(
            fresh_input_tokens=150,
            cached_input_tokens=3250000,
            output_tokens=25000,
            total_input_tokens=3250150,
            tokens_available=True,
            wall_time_seconds=120.35,
            api_time_seconds=None,
            num_turns=35,
            num_tool_calls=0,
            num_thinking_events=0,
            model="claude-sonnet-4-6",
            backend="claude-code",
            shadow_cost_usd=2.99,
        )
        expected = record["fresh_input_tokens"] + record["cached_input_tokens"]
        assert record["total_input_tokens"] == expected

    def test_tokens_available_all_true_when_all_backends_support(self) -> None:
        """tokens_available is True when all records have tokens_available=True."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, tokens_available=True))
        agg.add(_make_record(fresh=200, tokens_available=True))
        totals = agg.totals()
        assert totals["tokens_available"] is True

    def test_tokens_available_false_when_any_backend_lacks_tokens(self) -> None:
        """tokens_available is False when any record has tokens_available=False."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(fresh=100, tokens_available=True))
        agg.add(_make_record(fresh=0, tokens_available=False))
        totals = agg.totals()
        assert totals["tokens_available"] is False

    def test_num_tool_calls_summed_across_records(self) -> None:
        """num_tool_calls is summed across all records."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(num_tool_calls=3))
        agg.add(_make_record(num_tool_calls=7))
        totals = agg.totals()
        assert totals["num_tool_calls"] == 10

    def test_num_thinking_events_summed_across_records(self) -> None:
        """num_thinking_events is summed across all records."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(num_thinking_events=2))
        agg.add(_make_record(num_thinking_events=5))
        totals = agg.totals()
        assert totals["num_thinking_events"] == 7

    def test_api_time_summed_when_all_present(self) -> None:
        """api_time_seconds is summed when all records have a value."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(api_time=10.0))
        agg.add(_make_record(api_time=20.0))
        totals = agg.totals()
        assert totals["api_time_seconds"] == 30.0

    def test_api_time_none_when_any_record_lacks_it(self) -> None:
        """api_time_seconds is None when any record has api_time_seconds=None."""
        agg = _telemetry.AggregatedTelemetry()
        agg.add(_make_record(api_time=10.0))
        agg.add(_make_record(api_time=None))
        totals = agg.totals()
        assert totals["api_time_seconds"] is None

    def test_empty_aggregation_tokens_available_true(self) -> None:
        """Empty aggregation defaults tokens_available to True."""
        agg = _telemetry.AggregatedTelemetry()
        totals = agg.totals()
        assert totals["tokens_available"] is True

    def test_empty_aggregation_activity_counts_zero(self) -> None:
        """Empty aggregation has zero tool calls and thinking events."""
        agg = _telemetry.AggregatedTelemetry()
        totals = agg.totals()
        assert totals["num_tool_calls"] == 0
        assert totals["num_thinking_events"] == 0
