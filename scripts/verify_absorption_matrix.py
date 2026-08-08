#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "docs" / "architecture" / "absorption-source-lock.json"
MATRIX_PATH = ROOT / "docs" / "architecture" / "yaojingang-absorption-matrix.md"

EXPECTED_REPOSITORIES = {
    "GEOFlow",
    "geo-citation-lab",
    "yao-open-prompts",
    "yao-geo-skills",
    "yao-meta-skill",
    "GEORank",
    "TokEMS",
    "yao-open-skills",
    "TokHub",
    "yao-open-tools",
    "haidian",
    "yaojingang.github.io",
    "yaojingang",
}

EXPECTED_GEO_SKILLS = {
    "yao-geoflow-cli",
    "yao-geo-tracking",
    "yao-geo-effect-monitor",
    "yao-deepseek-crawler",
    "yao-doubao-crawler",
    "yao-chatgpt-crawler",
    "yao-geo-panorama-audit",
    "yao-geo-page-audit",
    "yao-geo-page-blueprint",
    "yao-geo-title-optimizer",
    "yao-geo-explainer-builder",
    "yao-geo-knowledge-base-builder",
    "yao-geo-intent-miner",
    "yao-geo-execution-roadmap",
    "yao-geo-brand-graph",
    "yao-geo-comparison-builder",
    "yao-geo-content-refiner",
    "yao-geo-article-friendly",
    "yao-geo-ranking-article-builder",
    "yao-geoflow-template",
    "yao-geoflow-design",
}

EXPECTED_COLUMNS = [
    "来源仓库",
    "能力名称",
    "业务价值",
    "代码位置",
    "输入输出",
    "依赖条件",
    "许可证",
    "AIRank 当前能力",
    "差距",
    "吸收方式",
    "目标模块",
    "优先级",
    "状态",
    "验收方法",
]

DECISIONS = {"absorb", "adapt", "reference_only", "reject"}
STATUSES = {"ready", "partial", "planned", "blocked", "disabled", "rejected"}
PRIORITIES = {"P0", "P1", "P2", "P3"}


def table_cells(line: str) -> list[str]:
    return [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]


def validate() -> dict[str, object]:
    errors: list[str] = []
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    matrix = MATRIX_PATH.read_text(encoding="utf-8")

    repositories = lock.get("repositories", [])
    repository_names = {item.get("name") for item in repositories}
    if repository_names != EXPECTED_REPOSITORIES:
        errors.append(
            "source lock repository coverage mismatch: "
            f"missing={sorted(EXPECTED_REPOSITORIES - repository_names)} "
            f"unexpected={sorted(repository_names - EXPECTED_REPOSITORIES)}"
        )

    for item in repositories:
        name = item.get("name", "<unknown>")
        if item.get("decision") not in DECISIONS:
            errors.append(f"{name}: invalid source decision")
        if not str(item.get("url", "")).startswith("https://github.com/yaojingang/"):
            errors.append(f"{name}: source URL is not pinned to the expected GitHub owner")
        if not item.get("license"):
            errors.append(f"{name}: missing license boundary")
        commit = item.get("commit")
        if item.get("decision") == "reject":
            if commit is not None:
                errors.append(f"{name}: rejected metadata-only source should not carry a cloned commit")
        elif not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            errors.append(f"{name}: missing immutable 40-character commit")

    headers = [table_cells(line) for line in matrix.splitlines() if line.startswith("| 来源仓库 ")]
    if not headers or any(header != EXPECTED_COLUMNS for header in headers):
        errors.append("matrix does not expose the required 14-column contract")

    rows: list[list[str]] = []
    for line in matrix.splitlines():
        if not line.startswith("|"):
            continue
        cells = table_cells(line)
        if not cells or cells[0] in {"来源仓库", "---"}:
            continue
        if len(cells) != len(EXPECTED_COLUMNS):
            errors.append(f"matrix row has {len(cells)} columns instead of 14: {line[:120]}")
            continue
        rows.append(cells)

    matrix_repositories = {row[0] for row in rows}
    missing_matrix_repositories = EXPECTED_REPOSITORIES - matrix_repositories
    if missing_matrix_repositories:
        errors.append(f"repositories missing from matrix: {sorted(missing_matrix_repositories)}")

    for row in rows:
        source, capability, *_middle, decision, _target, priority, status, acceptance = row
        if source not in EXPECTED_REPOSITORIES:
            errors.append(f"unknown matrix source: {source}")
        if decision not in DECISIONS:
            errors.append(f"{source}/{capability}: invalid decision {decision}")
        if priority not in PRIORITIES:
            errors.append(f"{source}/{capability}: invalid priority {priority}")
        if status not in STATUSES:
            errors.append(f"{source}/{capability}: invalid status {status}")
        if not acceptance:
            errors.append(f"{source}/{capability}: acceptance method is empty")

    missing_skills = {skill for skill in EXPECTED_GEO_SKILLS if f"`{skill}`" not in matrix}
    if missing_skills:
        errors.append(f"yao-geo-skills coverage missing: {sorted(missing_skills)}")

    result = {
        "status": "pass" if not errors else "fail",
        "source_count": len(repositories),
        "matrix_row_count": len(rows),
        "geo_skill_count": len(EXPECTED_GEO_SKILLS) - len(missing_skills),
        "decisions": sorted({row[9] for row in rows}),
        "errors": errors,
    }
    return result


def main() -> int:
    result = validate()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
