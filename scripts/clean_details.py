#!/usr/bin/env python3
"""Clean B: details.json → export-ready fields only."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.job_schema import project_detail

__version__ = "2.18.0"


def _load_details(raw):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and isinstance(raw.get("jobs"), list):
        return raw["jobs"]
    raise ValueError("详情 JSON 须为数组，或含 jobs 数组的对象")


def clean_details(rows: list) -> list[dict]:
    out = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        row = project_detail(item)
        eid = row.get("encrypt_job_id") or ""
        if not eid or eid in seen:
            continue
        seen.add(eid)
        out.append(row)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"详情后清洗（只保留导出字段）v{__version__}"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--input", required=True, help="details.json")
    p.add_argument("--output", default=None, help="默认覆盖 --input")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    src = Path(args.input)
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
        rows = _load_details(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"❌ 无法读取 {src}: {exc}")
        sys.exit(1)
    cleaned = clean_details(rows)
    out = Path(args.output or args.input)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"详情已清洗: {out}（{len(cleaned)} 条）")


if __name__ == "__main__":
    main()
