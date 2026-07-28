#!/usr/bin/env python3
"""Validate repository Skill structure without third-party dependencies."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DIMENSION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
FRONTMATTER_PATTERN = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
RUBRIC_LIST_FIELDS = (
    "trigger_conditions",
    "pass_conditions",
    "fail_conditions",
    "boundary_rules",
)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(skill_md: Path) -> dict[str, str]:
    content = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(content)
    if not match:
        raise ValueError("SKILL.md 缺少有效的 YAML frontmatter。")

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() or ":" not in line:
            raise ValueError("SKILL.md frontmatter 只允许简单的顶层键值。")
        key, value = line.split(":", 1)
        fields[key.strip()] = unquote(value)

    if set(fields) != {"name", "description"}:
        raise ValueError("SKILL.md frontmatter 必须且只能包含 name 和 description。")
    if not fields["description"].strip():
        raise ValueError("SKILL.md description 不能为空。")
    return fields


def quoted_yaml_value(content: str, key: str) -> str | None:
    match = re.search(
        rf'^\s{{2}}{re.escape(key)}:\s*"([^"\r\n]+)"\s*$',
        content,
        re.MULTILINE,
    )
    return match.group(1) if match else None


def validate_openai_yaml(path: Path, skill_name: str) -> None:
    content = path.read_text(encoding="utf-8")
    if not re.search(r"^interface:\s*$", content, re.MULTILINE):
        raise ValueError("agents/openai.yaml 缺少 interface。")

    values = {
        key: quoted_yaml_value(content, key)
        for key in ("display_name", "short_description", "default_prompt")
    }
    missing = [key for key, value in values.items() if value is None]
    if missing:
        raise ValueError(
            "agents/openai.yaml 缺少使用双引号的字段：" + ", ".join(missing)
        )

    short_description = values["short_description"] or ""
    if not 25 <= len(short_description) <= 64:
        raise ValueError("short_description 长度必须为 25–64 个字符。")
    if f"${skill_name}" not in (values["default_prompt"] or ""):
        raise ValueError(f"default_prompt 必须显式包含 ${skill_name}。")


def validate_string_list(value: Any, label: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise ValueError(f"{label} 必须是非空字符串数组。")


def validate_rubric(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "dimensions" not in payload:
        return
    if not isinstance(payload.get("rubric_version"), str) or not payload["rubric_version"]:
        raise ValueError(f"{path.name} 缺少非空 rubric_version。")

    dimensions = payload["dimensions"]
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError(f"{path.name} 的 dimensions 必须是非空数组。")

    ids: list[str] = []
    for position, dimension in enumerate(dimensions):
        label = f"{path.name}.dimensions[{position}]"
        if not isinstance(dimension, dict):
            raise ValueError(f"{label} 必须是对象。")
        dimension_id = dimension.get("id")
        if (
            not isinstance(dimension_id, str)
            or not DIMENSION_ID_PATTERN.fullmatch(dimension_id)
        ):
            raise ValueError(f"{label}.id 必须以小写英文字母开头。")
        if not isinstance(dimension.get("name"), str) or not dimension["name"].strip():
            raise ValueError(f"{label}.name 必须是非空字符串。")
        rubric = dimension.get("rubric")
        if not isinstance(rubric, dict):
            raise ValueError(f"{label}.rubric 必须是对象。")
        for field in RUBRIC_LIST_FIELDS:
            validate_string_list(rubric.get(field), f"{label}.rubric.{field}")
        if (
            not isinstance(rubric.get("judgment_rule"), str)
            or not rubric["judgment_rule"].strip()
        ):
            raise ValueError(f"{label}.rubric.judgment_rule 必须是非空字符串。")
        ids.append(dimension_id)

    if len(ids) != len(set(ids)):
        raise ValueError(f"{path.name} 存在重复的 dimension id。")


def validate_skill(skill_dir: Path) -> dict[str, Any]:
    skill_name = skill_dir.name
    if not NAME_PATTERN.fullmatch(skill_name):
        raise ValueError("Skill 目录名必须使用小写英文、数字和连字符。")

    required_paths = (
        "SKILL.md",
        "agents/openai.yaml",
        "assets",
        "references",
        "scripts/prepare_eval.py",
        "scripts/score_result.py",
    )
    missing = [item for item in required_paths if not (skill_dir / item).exists()]
    if missing:
        raise ValueError("缺少必要资源：" + ", ".join(missing))

    frontmatter = parse_frontmatter(skill_dir / "SKILL.md")
    if frontmatter["name"] != skill_name:
        raise ValueError(
            f"SKILL.md name 为 {frontmatter['name']}，与目录名 {skill_name} 不一致。"
        )
    validate_openai_yaml(skill_dir / "agents" / "openai.yaml", skill_name)

    rubric_files = []
    for path in sorted((skill_dir / "references").glob("*.json")):
        validate_rubric(path)
        rubric_files.append(path.name)
    if not rubric_files:
        raise ValueError("references/ 中至少需要一份 Rubric JSON。")

    return {"name": skill_name, "rubrics": rubric_files}


def main() -> int:
    try:
        skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
        if not skill_dirs:
            raise ValueError("skills/ 中没有 Skill 目录。")
        skills = []
        for skill_dir in skill_dirs:
            try:
                skills.append(validate_skill(skill_dir))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(f"{skill_dir.name}：{exc}") from exc
        print(json.dumps({"success": True, "skills": skills}, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
