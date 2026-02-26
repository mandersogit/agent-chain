"""Telemetry normalization and aggregation."""

import agent_chain.types as _types


class AggregatedTelemetry:
    """Aggregated telemetry across multiple steps.

    Tracks per-step records and provides chain-level totals.
    """

    def __init__(self) -> None:
        self._records: list[_types.TelemetryRecord] = []

    def add(self, record: _types.TelemetryRecord) -> None:
        """Add a step's telemetry to the aggregate.

        Args:
            record: Telemetry record from a completed step.
        """
        self._records.append(record)

    def totals(self) -> dict[str, object]:
        """Compute chain-level totals across all added records.

        Returns:
            Dict with summed token counts, wall time, cost, and a
            ``cost_incomplete`` flag if any step lacks cost data.
        """
        fresh = 0
        cached = 0
        output = 0
        total_input = 0
        turns = 0
        wall = 0.0
        cost = 0.0
        has_null_cost = False

        for rec in self._records:
            fresh += rec["fresh_input_tokens"]
            cached += rec["cached_input_tokens"]
            output += rec["output_tokens"]
            total_input += rec["total_input_tokens"]
            turns += rec["num_turns"]
            wall += rec["wall_time_seconds"]
            if rec["shadow_cost_usd"] is not None:
                cost += rec["shadow_cost_usd"]
            else:
                has_null_cost = True

        return {
            "fresh_input_tokens": fresh,
            "cached_input_tokens": cached,
            "output_tokens": output,
            "total_input_tokens": total_input,
            "num_turns": turns,
            "wall_time_seconds": wall,
            "shadow_cost_usd": cost if cost > 0 or not has_null_cost else None,
            "cost_incomplete": has_null_cost,
        }
