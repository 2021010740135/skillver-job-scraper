#!/usr/bin/env python3
"""Evaluate position-mapping predictions against the mapping eval set.

Measures how well a predictor maps user phrasings (输入 → 58 standard
positions or reject) relative to gold labels. Two indicators only:

  1. position_accuracy  — pred == gold on evaluable items
  2. false_accept_rate  — gold reject (null) but pred accepted

Prediction JSON shape (same as match_scores):
  {"results": [{"id": "...", "position_name": "Agent工程师"|null, "score": 85}]}

Items with kind == "ambiguous" are excluded from auto evaluation (they go
through human confirmation online).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def load_gold_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("gold 需要 items 数组（同 skillver_position_mapping_v1.json）")
    return items


def load_pred_by_id(payload: dict[str, Any]) -> dict[str, str | None]:
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("pred JSON 需要 results 数组（同 match_scores）")
    out: dict[str, str | None] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        pos = item.get("position_name")
        out[item_id] = str(pos or "").strip() or None
    return out


def compute_metrics(
    gold_items: list[dict[str, Any]],
    pred_by_id: dict[str, str | None],
) -> dict[str, Any]:
    evaluable = 0
    correct = 0
    gold_reject = 0
    false_accept = 0
    details: list[dict[str, Any]] = []

    for g in gold_items:
        if str(g.get("kind") or "") == "ambiguous":
            continue
        evaluable += 1
        item_id = str(g.get("id") or "")
        pred = pred_by_id.get(item_id)  # missing -> None (视为预测拒绝)
        gold = str(g.get("gold_position_name") or "").strip() or None
        if gold is None:
            gold_reject += 1
            if pred is not None:
                false_accept += 1
                details.append(
                    {"id": item_id, "case": "false_accept", "input": g.get("input"), "pred": pred}
                )
        if pred == gold:
            correct += 1
        else:
            details.append(
                {
                    "id": item_id,
                    "case": "mismatch",
                    "input": g.get("input"),
                    "gold": gold,
                    "pred": pred,
                }
            )

    return {
        "evaluable_count": evaluable,
        "correct_count": correct,
        "position_accuracy": (correct / evaluable) if evaluable else None,
        "gold_reject_count": gold_reject,
        "false_accept_count": false_accept,
        "false_accept_rate": (false_accept / gold_reject) if gold_reject else None,
        "details": details,
    }


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f} ({value * 100:.1f}%)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, help="mapping eval set JSON")
    parser.add_argument("--pred", required=True, help="prediction JSON (results[])")
    args = parser.parse_args(argv)

    gold = read_json(args.gold)
    pred = read_json(args.pred)
    gold_items = load_gold_items(gold)
    pred_by_id = load_pred_by_id(pred)

    m = compute_metrics(gold_items, pred_by_id)

    print(f"gold: {args.gold}")
    print(f"pred: {args.pred}")
    print(f"n_gold: {len(gold_items)} (可评测 {m['evaluable_count']})")
    print("--- primary metrics ---")
    print(f"position_accuracy:  {_fmt_rate(m['position_accuracy'])}"
          f" ({m['correct_count']}/{m['evaluable_count']})")
    print(f"false_accept_rate:  {_fmt_rate(m['false_accept_rate'])}"
          f" ({m['false_accept_count']}/{m['gold_reject_count']})")
    for d in m["details"]:
        print(
            f"  [{d['case']}] {d['id']} | {str(d.get('input') or '')[:28]}"
            f" | gold={d.get('gold')} pred={d.get('pred')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
