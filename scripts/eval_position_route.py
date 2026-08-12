#!/usr/bin/env python3
"""Compare position-route predictions against data/eval gold labels.

Primary metrics only:
  - false_positive_rate (误放率)
  - precision_at_accept
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_gold_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("gold JSON 需要 items 数组")
    return [i for i in items if isinstance(i, dict) and str(i.get("id") or "").strip()]


def load_pred_by_id(
    payload: dict[str, Any],
    *,
    min_score: int,
) -> dict[str, dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("pred JSON 需要 results 数组（同 match_scores）")
    out: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("id") or "").strip()
        if not eid:
            continue
        pos = item.get("position_name")
        pos_s = str(pos).strip() if pos is not None else ""
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            score = -1
        accept = bool(pos_s) and score >= min_score
        out[eid] = {
            "position_name": pos_s if accept else None,
            "score": score,
            "accept": accept,
        }
    return out


def compute_metrics(
    gold_items: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing = [str(g["id"]) for g in gold_items if str(g["id"]) not in pred_by_id]
    gold_reject = 0
    fp = 0
    pred_accept = 0
    tp_accept = 0

    for g in gold_items:
        eid = str(g["id"])
        pred = pred_by_id.get(eid)
        if pred is None:
            continue
        is_gold_reject = bool(g.get("gold_reject"))
        if g.get("gold_position_name") is None:
            is_gold_reject = True
        if is_gold_reject:
            gold_reject += 1
            if pred["accept"]:
                fp += 1
        if pred["accept"]:
            pred_accept += 1
            if not is_gold_reject:
                tp_accept += 1

    fpr = (fp / gold_reject) if gold_reject else None
    precision = (tp_accept / pred_accept) if pred_accept else None
    return {
        "n_gold": len(gold_items),
        "n_pred_matched": len(gold_items) - len(missing),
        "missing_pred_ids": missing[:20],
        "missing_pred_count": len(missing),
        "gold_reject_count": gold_reject,
        "false_positives": fp,
        "false_positive_rate": fpr,
        "pred_accept_count": pred_accept,
        "true_accept_count": tp_accept,
        "precision_at_accept": precision,
        "draft_label_count": sum(
            1 for g in gold_items if g.get("label_status") == "draft"
        ),
        "human_label_count": sum(
            1 for g in gold_items if g.get("label_status") == "human"
        ),
    }


def _fmt_rate(v: float | None) -> str:
    if v is None:
        return "n/a"
    return f"{v:.4f} ({v * 100:.1f}%)"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="标准岗分流评测：FPR + Precision@accept")
    p.add_argument(
        "--gold",
        default="data/eval/skillver_position_route_v1.json",
        help="金标评测集",
    )
    p.add_argument(
        "--pred",
        required=True,
        help="预测 match_scores JSON",
    )
    p.add_argument(
        "--min-score",
        type=int,
        default=71,
        help="预测录取阈值（默认 71，即 score>70）",
    )
    p.add_argument(
        "--require-human",
        action="store_true",
        help="仅统计 label_status=human 的条目",
    )
    args = p.parse_args(argv)

    gold = read_json(args.gold)
    items = load_gold_items(gold)
    if args.require_human:
        items = [i for i in items if i.get("label_status") == "human"]
        if not items:
            print("没有 label_status=human 的条目", file=sys.stderr)
            return 2

    pred = load_pred_by_id(read_json(args.pred), min_score=int(args.min_score))
    metrics = compute_metrics(items, pred)

    print(f"gold: {args.gold}")
    print(f"pred: {args.pred}")
    print(f"min_score: {args.min_score}")
    print(f"n_gold: {metrics['n_gold']} (human={metrics['human_label_count']}, draft={metrics['draft_label_count']})")
    if metrics["missing_pred_count"]:
        print(f"warning: missing pred for {metrics['missing_pred_count']} ids")
    print("--- primary metrics ---")
    print(
        f"false_positive_rate: {_fmt_rate(metrics['false_positive_rate'])} "
        f"({metrics['false_positives']}/{metrics['gold_reject_count']})"
    )
    print(
        f"precision_at_accept: {_fmt_rate(metrics['precision_at_accept'])} "
        f"({metrics['true_accept_count']}/{metrics['pred_accept_count']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
