#!/usr/bin/env python3
"""Clean A: list_batch → classify_input (Agent fields only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.job_schema import project_classify_job

__version__ = "1.0.0"


def clean_list_batch(payload: dict) -> dict:
    jobs = []
    for item in payload.get("jobs") or []:
        if not isinstance(item, dict):
            continue
        card = project_classify_job(item)
        if not card.get("id"):
            continue
        jobs.append(card)
    return {
        "schema_version": 1,
        "query": payload.get("query") or payload.get("target_position_name") or "",
        "target_position_name": payload.get("target_position_name")
        or payload.get("query")
        or "",
        "catalog_names": list(payload.get("catalog_names") or []),
        "batch_index": payload.get("batch_index") or 1,
        "list_start_page": payload.get("list_start_page"),
        "list_end_page": payload.get("list_end_page"),
        "next_list_start_page": payload.get("next_list_start_page"),
        "city": payload.get("city") or "",
        "jobs": jobs,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"分类前清洗（list_batch → classify_input）v{__version__}"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--input", required=True, help="list_batch_N.json")
    p.add_argument("--output", required=True, help="classify_input_N.json")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    src = Path(args.input)
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"❌ 无法读取 {src}: {exc}")
        sys.exit(1)
    if not isinstance(payload, dict):
        print("❌ 输入必须是 JSON 对象")
        sys.exit(1)
    cleaned = clean_list_batch(payload)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"classify_input 已写: {out}（{len(cleaned['jobs'])} 条）")


if __name__ == "__main__":
    main()
