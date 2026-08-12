#!/usr/bin/env python3
"""Tests for eval_position_route metrics."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_position_route.py"


def load_module():
    spec = importlib.util.spec_from_file_location("eval_position_route", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class EvalPositionRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_fpr_and_precision(self):
        gold = [
            {"id": "a", "gold_reject": True, "gold_position_name": None},
            {"id": "b", "gold_reject": False, "gold_position_name": "Agent工程师"},
            {"id": "c", "gold_reject": True, "gold_position_name": None},
        ]
        pred = {
            "a": {"accept": True, "position_name": "Agent工程师", "score": 80},
            "b": {"accept": True, "position_name": "Agent工程师", "score": 90},
            "c": {"accept": False, "position_name": None, "score": 10},
        }
        m = self.mod.compute_metrics(gold, pred)
        # FP: a only → 1/2
        self.assertEqual(m["false_positives"], 1)
        self.assertEqual(m["gold_reject_count"], 2)
        self.assertAlmostEqual(m["false_positive_rate"], 0.5)
        # Precision: pred accept a,b → tp only b → 1/2
        self.assertEqual(m["pred_accept_count"], 2)
        self.assertEqual(m["true_accept_count"], 1)
        self.assertAlmostEqual(m["precision_at_accept"], 0.5)

    def test_load_pred_min_score(self):
        payload = {
            "results": [
                {"id": "x", "position_name": "Agent工程师", "score": 70},
                {"id": "y", "position_name": "Agent工程师", "score": 71},
            ]
        }
        by = self.mod.load_pred_by_id(payload, min_score=71)
        self.assertFalse(by["x"]["accept"])
        self.assertTrue(by["y"]["accept"])


if __name__ == "__main__":
    unittest.main()
