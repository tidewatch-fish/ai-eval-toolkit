#!/usr/bin/env python3
"""使用同一份 Gold Set 验证通用版和金融版 Rubric Skill。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


EXAMPLE_DIR = Path(__file__).resolve().parent
MATERIALS_DIR = EXAMPLE_DIR.parent
SKILLS_DIR = (
    MATERIALS_DIR / "skills"
    if (MATERIALS_DIR / "skills").is_dir()
    else MATERIALS_DIR
)
CASES = EXAMPLE_DIR / "shared-finance-cases.jsonl"
JUDGMENTS = EXAMPLE_DIR / "shared-finance-judgments.jsonl"
FLOWS = {
    "generic": SKILLS_DIR / "generic-rubric-judge-template",
    "finance": SKILLS_DIR / "finance-rubric-judge",
}
EXPECTED_OVERALL = {
    "total": 7,
    "applicable": 6,
    "passed": 3,
    "failed": 3,
    "not_applicable": 1,
    "applicability_rate": 0.8571,
    "pass_rate": 0.5,
}
EXPECTED_QUERY_LEVEL = {
    "total": 3,
    "applicable": 2,
    "passed": 1,
    "failed": 1,
    "not_applicable": 1,
    "applicability_rate": 0.6667,
    "pass_rate": 0.5,
}
EXPECTED_BY_DIMENSION = {
    "accuracy": {"total": 3, "passed": 1, "failed": 1, "not_applicable": 1},
    "completeness": {"total": 2, "passed": 1, "failed": 1, "not_applicable": 0},
    "helpfulness": {"total": 2, "passed": 1, "failed": 1, "not_applicable": 0},
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{path.name} 第 {line_number} 行不是有效 JSON。") from exc
    return records


def run_json(command: list[str], *, stdin: dict[str, Any] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        command,
        input=json.dumps(stdin, ensure_ascii=False) if stdin is not None else None,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"命令执行失败：{' '.join(command)}\n{completed.stdout}\n{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"命令未返回有效 JSON：{' '.join(command)}") from exc


def assert_subset(actual: dict[str, Any], expected: dict[str, Any], label: str) -> None:
    mismatches = {
        key: {"expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    }
    if mismatches:
        raise AssertionError(f"{label} 不符合预期：{json.dumps(mismatches, ensure_ascii=False)}")


def validate_dataset(
    cases: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
) -> None:
    case_keys = {(item["case_id"], item["dimension_id"]) for item in cases}
    judgment_keys = {(item["case_id"], item["dimension_id"]) for item in judgments}
    if len(case_keys) != len(cases):
        raise AssertionError("样本中存在重复的 case_id + dimension_id。")
    if case_keys != judgment_keys:
        raise AssertionError("样本与判断结果的 case_id + dimension_id 不一致。")
    if any(item["result"] != item["human_judgment"]["result"] for item in judgments):
        raise AssertionError("示例 Judge 结果应与 Gold Set 人工标签完全一致。")


def validate_na_miss_counts_as_missed_error(
    flow_name: str,
    score_script: Path,
) -> float:
    judgments = [
        {
            "case_id": "missed-by-not-applicable",
            "dimension_id": "accuracy",
            "result": "不适用",
            "evidence": ["待评回答原文"],
            "reason": "不适用：Judge 未完成有效判断。",
            "human_judgment": {
                "result": "错",
                "reason": "人工确认回答存在错误。",
            },
        },
        {
            "case_id": "caught-error",
            "dimension_id": "accuracy",
            "result": "错",
            "evidence": ["待评回答原文"],
            "reason": "错：Judge 抓住了错误。",
            "human_judgment": {
                "result": "错",
                "reason": "人工确认回答存在错误。",
            },
        },
    ]
    scored = run_json(
        [sys.executable, str(score_script), "--summary-only"],
        stdin=judgments,
    )
    alignment = scored["summary"]["human_alignment"]
    if alignment.get("error_recall") != 0.5:
        raise AssertionError(
            f"{flow_name} 未将 Judge 的“不适用”计为人工错误样本的漏判："
            f"{json.dumps(alignment, ensure_ascii=False)}"
        )
    return alignment["error_recall"]


def validate_flow(
    flow_name: str,
    skill_dir: Path,
    all_dimension_source: dict[str, Any],
) -> dict[str, Any]:
    prepare_script = skill_dir / "scripts" / "prepare_eval.py"
    score_script = skill_dir / "scripts" / "score_result.py"

    prepared = run_json(
        [sys.executable, str(prepare_script), "--input", str(CASES)]
    )
    if prepared.get("source_case_count") != 7 or prepared.get("task_count") != 7:
        raise AssertionError(f"{flow_name} 的 JSONL 任务准备数量不正确。")
    if any("human_judgment" in task.get("case", {}) for task in prepared.get("tasks", [])):
        raise AssertionError(f"{flow_name} 的任务准备过程泄漏了人工标签。")

    expanded = run_json(
        [sys.executable, str(prepare_script), "--all-dimensions"],
        stdin=all_dimension_source,
    )
    expanded_ids = {
        task["case"]["dimension_id"] for task in expanded.get("tasks", [])
    }
    if expanded.get("task_count") != 3 or expanded_ids != {
        "accuracy",
        "completeness",
        "helpfulness",
    }:
        raise AssertionError(f"{flow_name} 的三维任务展开不正确。")

    scored = run_json(
        [
            sys.executable,
            str(score_script),
            "--input",
            str(JUDGMENTS),
            "--summary-only",
        ]
    )
    summary = scored["summary"]
    assert_subset(summary["overall"], EXPECTED_OVERALL, f"{flow_name}.overall")
    assert_subset(
        summary["query_level"],
        EXPECTED_QUERY_LEVEL,
        f"{flow_name}.query_level",
    )
    for dimension_id, expected in EXPECTED_BY_DIMENSION.items():
        assert_subset(
            summary["by_dimension"][dimension_id],
            expected,
            f"{flow_name}.by_dimension.{dimension_id}",
        )
    alignment = summary["human_alignment"]
    assert_subset(
        alignment,
        {
            "paired": 7,
            "exact_agreement_rate": 1.0,
            "binary_paired": 6,
            "error_recall": 1.0,
            "false_alarm_rate": 0.0,
        },
        f"{flow_name}.human_alignment",
    )
    na_miss_error_recall = validate_na_miss_counts_as_missed_error(
        flow_name,
        score_script,
    )

    return {
        "rubric_version": scored["rubric_version"],
        "prepared_tasks": prepared["task_count"],
        "expanded_dimensions": sorted(expanded_ids),
        "overall": summary["overall"],
        "query_level": summary["query_level"],
        "human_alignment": alignment,
        "na_miss_error_recall": na_miss_error_recall,
    }


def main() -> int:
    try:
        cases = read_jsonl(CASES)
        judgments = read_jsonl(JUDGMENTS)
        validate_dataset(cases, judgments)

        all_dimension_source = dict(cases[0])
        all_dimension_source.pop("dimension_id", None)
        all_dimension_source.pop("human_judgment", None)

        flows = {
            name: validate_flow(name, skill_dir, all_dimension_source)
            for name, skill_dir in FLOWS.items()
        }
        print(
            json.dumps(
                {
                    "success": True,
                    "dataset": {
                        "judgment_rows": len(judgments),
                        "underlying_cases": len({item["case_id"] for item in cases}),
                    },
                    "flows": flows,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, KeyError, TypeError, AssertionError) as exc:
        print(
            json.dumps(
                {"success": False, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
