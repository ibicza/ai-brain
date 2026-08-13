from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compare_evals(
    *,
    left_summary_path: Path,
    right_summary_path: Path,
    output_dir: Path,
    left_label: str = "left",
    right_label: str = "right",
) -> dict[str, Any]:
    left_summary = _read_json(left_summary_path)
    right_summary = _read_json(right_summary_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison = {
        "left_label": left_label,
        "right_label": right_label,
        "left_summary_path": str(left_summary_path),
        "right_summary_path": str(right_summary_path),
        "overall": _compare_metric_slice(
            _slice(left_summary, "overall"),
            _slice(right_summary, "overall"),
        ),
        "by_group": _compare_mapping(
            _mapping(left_summary, "by_group"),
            _mapping(right_summary, "by_group"),
        ),
        "by_task_type": _compare_mapping(
            _mapping(left_summary, "by_task_type"),
            _mapping(right_summary, "by_task_type"),
        ),
    }
    task_rows = [
        {"task_type": task_type, **stats}
        for task_type, stats in comparison["by_task_type"].items()
    ]
    comparison["most_improved_task_types"] = [
        row
        for row in sorted(
            task_rows,
            key=lambda item: (-item["delta_normalized_exact_match"], item["task_type"]),
        )
        if row["delta_normalized_exact_match"] > 0
    ]
    comparison["most_regressed_task_types"] = [
        row
        for row in sorted(
            task_rows,
            key=lambda item: (item["delta_normalized_exact_match"], item["task_type"]),
        )
        if row["delta_normalized_exact_match"] < 0
    ]
    comparison["still_failed_task_types"] = [
        row
        for row in sorted(
            task_rows, key=lambda item: (-item["right_count"], item["task_type"])
        )
        if row["right_count"] >= 20 and row["right_normalized_exact_match"] == 0.0
    ]

    comparison_path = output_dir / "comparison.json"
    markdown_path = output_dir / "comparison.md"
    comparison_path.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_comparison_markdown(comparison), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "comparison_path": str(comparison_path),
        "markdown_path": str(markdown_path),
        "comparison": comparison,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _slice(summary: dict[str, Any], key: str) -> dict[str, Any]:
    value = summary.get(key, {})
    return value if isinstance(value, dict) else {}


def _mapping(summary: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    value = summary.get(key, {})
    if not isinstance(value, dict):
        return {}
    return {
        str(item_key): item_value if isinstance(item_value, dict) else {}
        for item_key, item_value in value.items()
    }


def _compare_mapping(
    left: dict[str, dict[str, Any]],
    right: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {
        key: _compare_metric_slice(left.get(key, {}), right.get(key, {}))
        for key in sorted(set(left) | set(right))
    }


def _compare_metric_slice(
    left: dict[str, Any], right: dict[str, Any]
) -> dict[str, Any]:
    left_normalized = _float_metric(left, "normalized_exact_match")
    right_normalized = _float_metric(right, "normalized_exact_match")
    left_false_answer = _float_metric(left, "false_answer_rate")
    right_false_answer = _float_metric(right, "false_answer_rate")
    return {
        "left_count": _int_metric(left, "count"),
        "right_count": _int_metric(right, "count"),
        "left_normalized_exact_match": left_normalized,
        "right_normalized_exact_match": right_normalized,
        "delta_normalized_exact_match": right_normalized - left_normalized,
        "left_false_answer_rate": left_false_answer,
        "right_false_answer_rate": right_false_answer,
        "delta_false_answer_rate": right_false_answer - left_false_answer,
    }


def _float_metric(stats: dict[str, Any], key: str) -> float:
    try:
        return float(stats.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _int_metric(stats: dict[str, Any], key: str) -> int:
    try:
        return int(stats.get(key, 0))
    except (TypeError, ValueError):
        return 0


def _render_comparison_markdown(comparison: dict[str, Any]) -> str:
    left_label = comparison["left_label"]
    right_label = comparison["right_label"]
    lines = [
        "# Eval Comparison",
        "",
        f"Left: `{left_label}`",
        f"Right: `{right_label}`",
        "",
        "## Overall",
        "",
    ]
    overall = comparison["overall"]
    lines.extend(
        [
            "| Metric | Left | Right | Delta |",
            "|---|---:|---:|---:|",
            _metric_row(
                "Normalized EM",
                overall["left_normalized_exact_match"],
                overall["right_normalized_exact_match"],
                overall["delta_normalized_exact_match"],
            ),
            _metric_row(
                "False Answer Rate",
                overall["left_false_answer_rate"],
                overall["right_false_answer_rate"],
                overall["delta_false_answer_rate"],
            ),
            "",
            "## By Group",
            "",
            "| Group | Left Count | Right Count | Left Norm EM | Right Norm EM | Delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for group, stats in comparison["by_group"].items():
        lines.append(_comparison_row(group, stats))

    _append_task_table(
        lines, "Most Improved Task Types", comparison["most_improved_task_types"]
    )
    _append_task_table(
        lines, "Most Regressed Task Types", comparison["most_regressed_task_types"]
    )
    _append_task_table(
        lines, "Still Failed Task Types", comparison["still_failed_task_types"]
    )
    return "\n".join(lines).rstrip() + "\n"


def _append_task_table(
    lines: list[str], title: str, rows: list[dict[str, Any]]
) -> None:
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            "| Task Type | Left Count | Right Count | Left Norm EM | Right Norm EM | Delta |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(_comparison_row(row["task_type"], row))


def _comparison_row(label: str, stats: dict[str, Any]) -> str:
    return (
        f"| {label} | {stats['left_count']} | {stats['right_count']} | "
        f"{_fmt_rate(stats['left_normalized_exact_match'])} | "
        f"{_fmt_rate(stats['right_normalized_exact_match'])} | "
        f"{_fmt_delta(stats['delta_normalized_exact_match'])} |"
    )


def _metric_row(label: str, left: float, right: float, delta: float) -> str:
    return f"| {label} | {_fmt_rate(left)} | {_fmt_rate(right)} | {_fmt_delta(delta)} |"


def _fmt_rate(value: float) -> str:
    return f"{value:.4f}"


def _fmt_delta(value: float) -> str:
    return f"{value:+.4f}"
