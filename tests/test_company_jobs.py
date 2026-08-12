#!/usr/bin/env python3
"""Unit tests for YATN company-job scrape helpers (no Chrome)."""

from __future__ import annotations

import csv
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "scrape_company_jobs.py"


def load_module():
    spec = importlib.util.spec_from_file_location("scrape_company_jobs", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class CompanyJobsHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_load_companies_and_keywords(self):
        path = ROOT / "data" / "yatn" / "companies.csv"
        companies = self.mod.load_companies(path)
        self.assertGreaterEqual(len(companies), 40)
        deepseek = next(c for c in companies if c["brand_name"] == "DeepSeek")
        keys = self.mod.company_search_keywords(deepseek)
        self.assertIn("深度求索", keys)
        self.assertIn("DeepSeek", keys)
        filtered = self.mod.filter_companies(companies, priorities={"S"})
        self.assertTrue(all(c["priority"] == "S" for c in filtered))
        self.assertLess(len(filtered), len(companies))

    def test_daily_salary(self):
        self.assertTrue(self.mod.is_daily_salary("200-300元/天"))
        self.assertTrue(self.mod.is_daily_salary("150元/日"))
        self.assertFalse(self.mod.is_daily_salary("40-70K"))
        self.assertFalse(self.mod.is_daily_salary("30-50K·15薪"))

    def test_job_matches_company(self):
        company = {
            "brand_name": "MiniMax",
            "legal_name": "MiniMax",
            "aliases": ["稀宇科技"],
        }
        self.assertTrue(
            self.mod.job_matches_company(
                {"boss_name": "稀宇科技", "title": "算法工程师"}, company
            )
        )
        self.assertFalse(
            self.mod.job_matches_company(
                {"boss_name": "其他公司", "title": "Java"}, company
            )
        )

    def test_apply_scores_threshold(self):
        details = [
            {
                "encrypt_job_id": "a1",
                "job_link": "https://www.zhipin.com/job_detail/a1.html",
                "title": "Agent工程师",
                "company": "X",
                "yatn_legal_name": "X有限公司",
                "salary": "40-70K",
                "jd": "x" * 130,
            },
            {
                "encrypt_job_id": "b2",
                "job_link": "https://www.zhipin.com/job_detail/b2.html",
                "title": "行政",
                "company": "X",
                "yatn_legal_name": "X有限公司",
                "salary": "10-20K",
                "jd": "y" * 130,
            },
        ]
        scores = {
            "schema_version": 1,
            "results": [
                {"id": "a1", "position_name": "Agent工程师", "score": 85},
                {"id": "b2", "position_name": None, "score": 20},
            ],
        }
        catalog = ["Agent工程师", "机器学习工程师"]
        errors = self.mod.validate_match_scores(
            scores, expected_ids=["a1", "b2"], catalog_names=catalog
        )
        self.assertEqual(errors, [])
        accepted, skipped = self.mod.apply_match_scores(details, scores)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["encrypt_job_id"], "a1")
        self.assertEqual(len(skipped), 1)
        # score>70：70 分不录取，71 分录取
        borderline = {
            "schema_version": 1,
            "results": [
                {"id": "a1", "position_name": "Agent工程师", "score": 70},
                {"id": "b2", "position_name": "Agent工程师", "score": 71},
            ],
        }
        acc2, skip2 = self.mod.apply_match_scores(details, borderline)
        self.assertEqual([r["encrypt_job_id"] for r in acc2], ["b2"])
        self.assertEqual(len(skip2), 1)

    def test_export_csv_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "out.csv"
            self.mod.export_csv(
                [
                    {
                        "yatn_legal_name": "深度求索",
                        "yatn_brand_name": "DeepSeek",
                        "yatn_priority": "S",
                        "yatn_city": "杭州",
                        "title": "推理工程师",
                        "salary": "40-70K",
                        "location": "杭州",
                        "position_name": "推理优化工程师(算法层)",
                        "match_score": 88,
                        "jd": "负责推理,优化",
                        "job_link": "https://example.com/j",
                        "encrypt_job_id": "abc",
                    }
                ],
                path,
            )
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["公司全称"], "深度求索")
            self.assertEqual(rows[0]["匹配分"], "88")
            self.assertIn("，", rows[0]["岗位描述"])

    def test_jobs_to_match_input_skips_daily_no_jd(self):
        jobs = [
            {
                "encrypt_job_id": "ok1",
                "job_link": "https://www.zhipin.com/job_detail/ok1.html",
                "title": "ML",
                "salary": "40-70K",
                "yatn_legal_name": "A",
                "yatn_brand_name": "A",
                "tags": "Python",
                "boss_title": "TL",
            },
            {
                "encrypt_job_id": "day1",
                "job_link": "https://www.zhipin.com/job_detail/day1.html",
                "title": "实习",
                "salary": "200元/天",
                "yatn_legal_name": "A",
            },
        ]
        payload = self.mod.jobs_to_match_input(
            jobs, catalog_names=["机器学习工程师"], batch_id="t1"
        )
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual([j["id"] for j in payload["jobs"]], ["ok1"])
        self.assertEqual(payload["jobs"][0]["boss_title"], "TL")
        self.assertNotIn("jd", payload["jobs"][0])


if __name__ == "__main__":
    unittest.main()
