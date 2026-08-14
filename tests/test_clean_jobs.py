#!/usr/bin/env python3
"""Clean A/B: drop extra fields, never drop intern/daily-salary cards."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.clean_classify_input import clean_list_batch, main as clean_a_main
from scripts.clean_details import clean_details, main as clean_b_main
from scripts.job_schema import CLASSIFY_JOB_FIELDS, DETAIL_FIELDS


INTERN_LIST = {
    "encrypt_job_id": "intern-1",
    "title": "机器学习实习生",
    "boss_name": "示例科技",
    "boss_title": "HR",
    "salary": "200元/天",
    "location": "上海",
    "tags": "实习 | 本科",
    "job_link": "https://www.zhipin.com/job_detail/intern-1.html",
    "security_id": "sec",
    "lid": "lid",
    "welfare": "五险一金",
    "brand_id": "drop-me",
}


class CleanClassifyInputTests(unittest.TestCase):
    def test_keeps_intern_and_daily_salary_cards(self):
        payload = {
            "schema_version": 1,
            "target_position_name": "机器学习工程师",
            "catalog_names": ["机器学习工程师"],
            "batch_index": 1,
            "city": "上海",
            "jobs": [INTERN_LIST, {"title": "无 id 应丢"}],
        }
        cleaned = clean_list_batch(payload)
        self.assertEqual(len(cleaned["jobs"]), 1)
        job = cleaned["jobs"][0]
        self.assertEqual(job["id"], "intern-1")
        self.assertEqual(job["title"], "机器学习实习生")
        self.assertEqual(job["salary"], "200元/天")
        self.assertEqual(job["company"], "示例科技")
        self.assertEqual(set(job), set(CLASSIFY_JOB_FIELDS))
        self.assertNotIn("location", job)
        self.assertNotIn("job_link", job)
        self.assertNotIn("security_id", job)
        self.assertNotIn("lid", job)
        self.assertNotIn("welfare", job)

    def test_cli_writes_classify_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            src = root / "list_batch_1.json"
            dst = root / "classify_input_1.json"
            src.write_text(
                json.dumps({"target_position_name": "岗", "jobs": [INTERN_LIST]}),
                encoding="utf-8",
            )
            clean_a_main(["--input", str(src), "--output", str(dst)])
            out = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(out["jobs"][0]["id"], "intern-1")
            self.assertEqual(set(out["jobs"][0]), set(CLASSIFY_JOB_FIELDS))


class CleanDetailsTests(unittest.TestCase):
    def test_keeps_intern_detail_and_drops_extra_keys(self):
        rows = [{
            "encrypt_job_id": "intern-1",
            "title": "机器学习实习生",
            "company": "示例科技",
            "salary": "200元/天",
            "location": "上海",
            "jd": "实习岗位职责与要求至少十字以上。",
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
            "job_link": "https://www.zhipin.com/job_detail/intern-1.html",
            "salary_source": "api",
            "boss_active_status": "今日活跃",
        }]
        cleaned = clean_details(rows)
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(cleaned[0]["salary"], "200元/天")
        self.assertEqual(set(cleaned[0]), set(DETAIL_FIELDS))
        self.assertNotIn("job_link", cleaned[0])
        self.assertNotIn("salary_source", cleaned[0])

    def test_cli_overwrites_input_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "details.json"
            path.write_text(
                json.dumps([{
                    "encrypt_job_id": "e1",
                    "title": "t",
                    "boss_name": "c",
                    "salary": "30-50K",
                    "location": "上海",
                    "jd": "职责正文足够长。",
                    "extra": 1,
                }]),
                encoding="utf-8",
            )
            clean_b_main(["--input", str(path)])
            out = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(out[0]["company"], "c")
            self.assertEqual(set(out[0]), set(DETAIL_FIELDS))
            self.assertNotIn("extra", out[0])


if __name__ == "__main__":
    unittest.main()
