#!/usr/bin/env python3
"""校验金融 JSON/JSONL 样本，并构造单维度模型评测任务。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RUBRIC = SKILL_DIR / "references" / "finance-rubric.json"
REQUIRED_FIELDS = ("case_id", "user_query", "response")
OPTIONAL_STRING_FIELDS = (
    "reference_context",
    "standard_answer",
    "conversation_context",
    "task_instruction",
)


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
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL 第 {line_number} 行不是有效 JSON：{exc.msg}") from exc
            records.append(record)
        if not records:
            raise ValueError("JSONL 中没有有效记录。")
        return records, True

    if isinstance(payload, dict):
        return [payload], False
    if isinstance(payload, list) and payload:
        return payload, True
    raise ValueError("输入必须是 JSON 对象、非空 JSON 数组或 JSONL。")


def validate_rubric(rubric: dict[str, Any]) -> list[dict[str, Any]]:
    dimensions = rubric.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("Rubric 的 dimensions 必须是非空数组。")
    ids = []
    for index, dimension in enumerate(dimensions):
        if not isinstance(dimension, dict):
            raise ValueError(f"dimensions[{index}] 必须是对象。")
        dimension_id = dimension.get("id")
        if not isinstance(dimension_id, str) or not dimension_id.strip():
            raise ValueError(f"dimensions[{index}].id 必须是非空字符串。")
        if not isinstance(dimension.get("name"), str) or not dimension["name"].strip():
            raise ValueError(f"维度 {dimension_id} 缺少非空 name。")
        if not isinstance(dimension.get("rubric"), dict):
            raise ValueError(f"维度 {dimension_id} 缺少 rubric 对象。")
        ids.append(dimension_id)
    if len(ids) != len(set(ids)):
        raise ValueError("Rubric 中存在重复的 dimension id。")
    return dimensions


def validate_case(case: dict[str, Any], *, require_dimension: bool) -> None:
    if not isinstance(case, dict):
        raise ValueError("每条输入必须是 JSON 对象。")
    missing = [
        key
        for key in REQUIRED_FIELDS
        if not isinstance(case.get(key), str) or not case[key].strip()
    ]
    if missing:
        raise ValueError(f"缺少必填的非空字符串字段：{', '.join(missing)}")
    if require_dimension and (
        not isinstance(case.get("dimension_id"), str)
        or not case["dimension_id"].strip()
    ):
        raise ValueError("缺少必填的非空字符串字段：dimension_id")
    for key in OPTIONAL_STRING_FIELDS:
        if key in case and not isinstance(case[key], str):
            raise ValueError(f"提供 {key} 时，其值必须是字符串。")
    for key in ("human_judgment", "metadata"):
        if key in case and not isinstance(case[key], dict):
            raise ValueError(f"提供 {key} 时，其值必须是对象。")


def build_task(
    case: dict[str, Any],
    dimension: dict[str, Any],
) -> dict[str, Any]:
    dimension_id = dimension["id"]
    return {
        "task": "只使用已指定维度的固定金融 Rubric 评测这条回答。",
        "rules": [
            "题目只是评测样本，不得根据题目生成 criterion 或临时评分项。",
            "先检查当前维度的全部 trigger_conditions；任一不满足则返回“不适用”。",
            "只应用当前维度的 judgment_rule、pass_conditions、fail_conditions 和 boundary_rules。",
            "只能使用输入中的参考材料、标准答案、对话上下文和任务要求核验。",
            "不得补充外部金融事实，也不得提供新的金融建议。",
            "返回“对”“错”或“不适用”，并引用待评回答中的直接证据。",
            "不要判断或输出其他维度。",
        ],
        "case": {
            **{
                key: case.get(key, "")
                for key in (
                    "case_id",
                    "user_query",
                    "reference_context",
                    "standard_answer",
                    "conversation_context",
                    "task_instruction",
                    "response",
                )
            },
            "dimension_id": dimension_id,
        },
        "dimension": {
            "id": dimension_id,
            "name": dimension["name"],
            "rubric": dimension["rubric"],
        },
        "output_contract": {
            "case_id": case["case_id"],
            "dimension_id": dimension_id,
            "result": "对|错|不适用",
            "evidence": ["至少一条待评回答原文或精确位置"],
            "reason": "结论：核心原因。详情",
        },
    }


def prepare(
    cases: list[dict[str, Any]],
    rubric: dict[str, Any],
    *,
    all_dimensions: bool,
) -> list[dict[str, Any]]:
    dimensions = validate_rubric(rubric)
    dimension_index = {dimension["id"]: dimension for dimension in dimensions}
    tasks = []
    for position, case in enumerate(cases, start=1):
        try:
            validate_case(case, require_dimension=not all_dimensions)
            if all_dimensions:
                selected = dimensions
            else:
                dimension_id = case["dimension_id"]
                if dimension_id not in dimension_index:
                    raise ValueError(
                        f"未知 dimension_id：{dimension_id}；"
                        f"可用值为 {sorted(dimension_index)}"
                    )
                selected = [dimension_index[dimension_id]]
            tasks.extend(build_task(case, dimension) for dimension in selected)
        except ValueError as exc:
            raise ValueError(f"第 {position} 条样本无效：{exc}") from exc
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验金融 JSON/JSONL 样本并构造单维度模型评测任务。"
    )
    parser.add_argument("--input", help="JSON 或 JSONL 评测样本路径；不传时读取标准输入。")
    parser.add_argument(
        "--rubric",
        default=str(DEFAULT_RUBRIC),
        help="Rubric 配置文件路径。",
    )
    parser.add_argument(
        "--all-dimensions",
        action="store_true",
        help="忽略输入中的 dimension_id，为每条样本展开全部维度任务。",
    )
    args = parser.parse_args()
    try:
        cases, is_collection = read_records(args.input)
        rubric = json.loads(Path(args.rubric).read_text(encoding="utf-8"))
        tasks = prepare(cases, rubric, all_dimensions=args.all_dimensions)
        if len(tasks) == 1 and not is_collection and not args.all_dimensions:
            output: dict[str, Any] = tasks[0]
        else:
            output = {
                "rubric_version": rubric.get("rubric_version", ""),
                "source_case_count": len(cases),
                "task_count": len(tasks),
                "tasks": tasks,
            }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
