#!/usr/bin/env python3
"""校验 JSON/JSONL 判断结果，并生成批量汇总。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RUBRIC = SKILL_DIR / "references" / "rubric.json"
VALID_RESULTS = {"对", "错", "不适用"}


def read_records(path: str | None) -> tuple[list[dict[str, Any]], bool]:
    raw = Path(path).read_text(encoding="utf-8") if path else sys.stdin.read()
    if not raw.strip():
        raise ValueError("请通过 --input 指定文件，或通过标准输入传入 JSON/JSONL。")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        records = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 第 {line_number} 行不是有效 JSON：{exc.msg}") from exc
        if not records:
            raise ValueError("JSONL 中没有有效记录。")
        return records, True

    if isinstance(payload, dict) and isinstance(payload.get("judgments"), list):
        if not payload["judgments"]:
            raise ValueError("judgments 必须是非空数组。")
        return payload["judgments"], True
    if isinstance(payload, dict):
        return [payload], False
    if isinstance(payload, list) and payload:
        return payload, True
    raise ValueError("输入必须是判断对象、非空 JSON 数组、含 judgments 的对象或 JSONL。")


def dimension_index(rubric: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("Rubric 的 dimensions 必须是非空数组。")
    index = {}
    for position, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise ValueError(f"dimensions[{position}] 必须是对象。")
        dimension_id = dimension.get("id")
        if not isinstance(dimension_id, str) or not dimension_id.strip():
            raise ValueError(f"dimensions[{position}].id 必须是非空字符串。")
        if dimension_id in index:
            raise ValueError(f"Rubric 中存在重复维度：{dimension_id}")
        index[dimension_id] = dimension
    return index


def validate_judgment(
    judgment: dict[str, Any],
    dimensions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(judgment, dict):
        raise ValueError("判断结果必须是 JSON 对象。")
    if not isinstance(judgment.get("case_id"), str) or not judgment["case_id"].strip():
        raise ValueError("case_id 必须是非空字符串。")
    dimension_id = judgment.get("dimension_id")
    if dimension_id not in dimensions:
        raise ValueError(
            f"dimension_id 必须是 {sorted(dimensions)} 之一；实际为 {dimension_id}"
        )
    result = judgment.get("result")
    if result not in VALID_RESULTS:
        raise ValueError("result 必须是“对”“错”或“不适用”。")
    evidence = judgment.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item.strip() for item in evidence)
    ):
        raise ValueError("evidence 必须是至少包含一个非空字符串的数组。")
    if not isinstance(judgment.get("reason"), str) or not judgment["reason"].strip():
        raise ValueError("reason 必须是非空字符串。")
    human = judgment.get("human_judgment")
    if human is not None:
        if not isinstance(human, dict) or human.get("result") not in VALID_RESULTS:
            raise ValueError(
                "human_judgment.result 必须是“对”“错”或“不适用”。"
            )
    return dimensions[dimension_id]


def calculate(
    judgment: dict[str, Any],
    rubric: dict[str, Any],
    dimensions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    dimension = validate_judgment(judgment, dimensions)
    result = judgment["result"]
    output = {
        "case_id": judgment["case_id"],
        "rubric_version": rubric.get("rubric_version", ""),
        "dimension": {
            "id": dimension["id"],
            "name": dimension.get("name", dimension["id"]),
        },
        "result": result,
        "is_applicable": result != "不适用",
        "evidence": judgment["evidence"],
        "reason": judgment["reason"],
        "judgment": judgment,
    }
    if "human_judgment" in judgment:
        output["human_judgment"] = judgment["human_judgment"]
    return output


def rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def count_results(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    passed = sum(record["result"] == "对" for record in records)
    failed = sum(record["result"] == "错" for record in records)
    not_applicable = sum(record["result"] == "不适用" for record in records)
    applicable = passed + failed
    return {
        "total": total,
        "applicable": applicable,
        "passed": passed,
        "failed": failed,
        "not_applicable": not_applicable,
        "applicability_rate": rate(applicable, total),
        "pass_rate": rate(passed, applicable),
    }


def human_alignment(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    paired = [
        record
        for record in records
        if isinstance(record.get("human_judgment"), dict)
        and record["human_judgment"].get("result") in VALID_RESULTS
    ]
    if not paired:
        return None

    exact_matches = sum(
        record["result"] == record["human_judgment"]["result"] for record in paired
    )
    binary = [
        record
        for record in paired
        if record["result"] in {"对", "错"}
        and record["human_judgment"]["result"] in {"对", "错"}
    ]
    human_failures = [
        record
        for record in paired
        if record["human_judgment"]["result"] == "错"
    ]
    judge_failures = [
        record
        for record in paired
        if record["result"] == "错"
        and record["human_judgment"]["result"] in {"对", "错"}
    ]
    true_failures = sum(
        record["result"] == "错" and record["human_judgment"]["result"] == "错"
        for record in paired
    )
    false_alarms = sum(
        record["result"] == "错" and record["human_judgment"]["result"] == "对"
        for record in paired
    )
    return {
        "paired": len(paired),
        "exact_agreement_rate": rate(exact_matches, len(paired)),
        "binary_paired": len(binary),
        "error_recall": rate(true_failures, len(human_failures)),
        "false_alarm_rate": rate(false_alarms, len(judge_failures)),
    }


def rollup_result(results: list[str]) -> str:
    if "错" in results:
        return "错"
    if "对" in results:
        return "对"
    return "不适用"


def query_level_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    case_ids = sorted({record["case_id"] for record in records})
    rollups = []
    for case_id in case_ids:
        case_records = [record for record in records if record["case_id"] == case_id]
        rollup: dict[str, Any] = {
            "case_id": case_id,
            "result": rollup_result([record["result"] for record in case_records]),
        }
        if all(isinstance(record.get("human_judgment"), dict) for record in case_records):
            rollup["human_judgment"] = {
                "result": rollup_result(
                    [record["human_judgment"]["result"] for record in case_records]
                )
            }
        rollups.append(rollup)

    output = count_results(rollups)
    alignment = human_alignment(rollups)
    if alignment is not None:
        output["human_alignment"] = alignment
    output["rollup_rule"] = (
        "任一维度为“错”则题目为“错”；否则任一维度为“对”则为“对”；"
        "全部为“不适用”才为“不适用”。"
    )
    return output


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    dimension_ids = sorted({record["dimension"]["id"] for record in records})
    by_dimension = {
        dimension_id: count_results(
            [record for record in records if record["dimension"]["id"] == dimension_id]
        )
        for dimension_id in dimension_ids
    }
    summary = {
        "overall": count_results(records),
        "by_dimension": by_dimension,
        "query_level": query_level_summary(records),
    }
    alignment = human_alignment(records)
    if alignment is not None:
        summary["human_alignment"] = alignment
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 JSON/JSONL 判断结果并生成批量汇总。"
    )
    parser.add_argument("--input", help="JSON 或 JSONL 判断结果路径；不传时读取标准输入。")
    parser.add_argument(
        "--rubric",
        default=str(DEFAULT_RUBRIC),
        help="Rubric 配置文件路径。",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="批量输入时只输出汇总，不返回逐条结果。",
    )
    args = parser.parse_args()
    try:
        judgments, is_collection = read_records(args.input)
        rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
        dimensions = dimension_index(rubric)
        validated = []
        for position, judgment in enumerate(judgments, start=1):
            try:
                validated.append(calculate(judgment, rubric, dimensions))
            except ValueError as exc:
                raise ValueError(f"第 {position} 条判断无效：{exc}") from exc

        if len(validated) == 1 and not is_collection and not args.summary_only:
            output: dict[str, Any] = validated[0]
        else:
            output = {
                "rubric_version": rubric.get("rubric_version", ""),
                "summary": summarize(validated),
            }
            if not args.summary_only:
                output["results"] = validated
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
