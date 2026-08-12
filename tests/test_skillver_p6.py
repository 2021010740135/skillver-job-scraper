#!/usr/bin/env python3
"""Skillver tests: seen v2, Agent decisions, list-only / details modes (mocked)."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "boss_cdp_raw.py"
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("boss_cdp_raw", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


from scripts import export_skillver_csv as ex


CATALOG = [
    "机器学习工程师",
    "AI产品经理(平台/商业)",
    "CV算法工程师",
    "预训练算法研究员/工程师",
]


class SeenV2Tests(unittest.TestCase):
    def test_migrate_v1_to_v2_queues(self):
        v1 = {
            "version": 1,
            "jobs": {
                "a": {
                    "job_id": "1",
                    "position_name": "机器学习工程师",
                    "has_details": False,
                    "exported": False,
                    "first_seen_at": "2026-01-01T00:00:00+00:00",
                    "exported_at": None,
                },
                "b": {
                    "job_id": "2",
                    "position_name": "机器学习工程师",
                    "has_details": True,
                    "exported": False,
                    "first_seen_at": "2026-01-01T00:00:00+00:00",
                    "exported_at": None,
                },
            },
        }
        names = {"机器学习工程师"}
        v2 = ex.migrate_seen_to_v2(v1, catalog_names=names)
        self.assertEqual(v2["version"], 2)
        self.assertEqual(
            v2["by_position"]["机器学习工程师"]["pending_details"], ["a"]
        )
        self.assertEqual(
            v2["by_position"]["机器学习工程师"]["pending_export"], ["b"]
        )


class MultiSelectFilterTests(unittest.TestCase):
    def test_normalize_filter_codes_variants(self):
        module = load_module()
        self.assertEqual(module.normalize_filter_codes("101,102"), ["101", "102"])

    def test_cli_list_only_passes_multi_filters(self):
        module = load_module()
        captured = {}

        def fake_list_only(**kwargs):
            captured["filters"] = kwargs["filters"]
            return {
                "list_data": {"keyword": "x", "city": "上海", "total": 0, "jobs": []},
                "classify_input_path": "x.json",
                "classify_input": {},
                "candidates": [],
            }

        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI 算法工程师",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(sys, "argv", [
                "boss_cdp_raw.py",
                "--position-name", "机器学习工程师",
                "--city", "上海",
                "--list-only",
                "--experience", "101,102",
                "--scale", "305",
                "--scale", "306",
                "--catalog", str(REPO_ROOT / "data" / "skillver" / "position_catalog.json"),
                "--seen", str(root / "seen.json"),
                "--output", str(root / "jobs.json"),
            ]), \
                    mock.patch.object(module, "require_runtime_dependencies",
                                      return_value=True), \
                    mock.patch.object(module, "resolve_city",
                                      return_value=("上海", "101020100")), \
                    mock.patch.object(module, "ensure_scrape_login",
                                      return_value=True), \
                    mock.patch.object(module, "resolve_standard_position",
                                      return_value=position), \
                    mock.patch.object(module, "load_position_catalog",
                                      return_value=[position]), \
                    mock.patch.object(module, "load_skillver_seen",
                                      return_value=ex.empty_seen()), \
                    mock.patch.object(module, "skillver_seen_detail_ids",
                                      return_value=set()), \
                    mock.patch.object(module, "load_seen_encrypt_job_ids",
                                      return_value=set()), \
                    mock.patch.object(
                        module, "run_skillver_list_only_batch",
                        side_effect=fake_list_only,
                    ), \
                    redirect_stdout(io.StringIO()):
                module.main()
        self.assertEqual(captured["filters"]["experience"], ["101", "102"])
        self.assertEqual(captured["filters"]["scale"], ["305", "306"])


class AgentClassifyTests(unittest.TestCase):
    def _job(self, eid, title, **extra):
        job = {
            "encrypt_job_id": eid,
            "title": title,
            "tags": "Python",
            "boss_name": "真实科技有限公司",
            "boss_title": "HR",
            "company_industry": "互联网",
            "job_link": f"https://www.zhipin.com/job_detail/{eid}.html",
        }
        job.update(extra)
        return job

    def test_clamp_min_details(self):
        module = load_module()
        self.assertEqual(module.clamp_skillver_min_details(None), (5, False))
        self.assertEqual(module.clamp_skillver_min_details(5), (5, False))
        self.assertEqual(module.clamp_skillver_min_details(50), (50, False))
        self.assertEqual(module.clamp_skillver_min_details(80), (50, True))

    def test_headhunter_filtered_before_agent(self):
        module = load_module()
        result = module.classify_list_jobs_from_agent(
            [self._job(
                "h1",
                "机器学习工程师",
                boss_name="某某猎头",
                boss_title="高级猎头顾问",
                company_industry="人力资源服务",
            )],
            "机器学习工程师",
            CATALOG,
            decisions_by_id={"h1": "机器学习工程师"},
        )
        self.assertEqual(result["decisions"][0]["final_route"], "none")
        self.assertTrue(
            result["decisions"][0]["skip_reason"].startswith("rule_non_entity")
        )

    def test_agent_routes_current_other_none(self):
        module = load_module()
        seen = ex.empty_seen()
        jobs = [
            self._job("c1", "机器学习工程师"),
            self._job("o1", "视觉算法"),
            self._job("n1", "运营"),
        ]
        result = module.classify_list_jobs_from_agent(
            jobs,
            "机器学习工程师",
            CATALOG,
            decisions_by_id={
                "c1": "机器学习工程师",
                "o1": "CV算法工程师",
                "n1": None,
            },
            seen=seen,
        )
        module.route_and_inventory_classifications(
            seen, result, "机器学习工程师", CATALOG
        )
        self.assertEqual(len(result["current"]), 1)
        self.assertEqual(result["other"][0][1], "CV算法工程师")
        self.assertIn("o1", seen["by_position"]["CV算法工程师"]["pending_details"])
        self.assertIn("c1", seen["by_position"]["机器学习工程师"]["pending_details"])

    def test_load_agent_decisions_validates_contract(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "dec.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "results": [
                    {"id": "a", "position_name": "机器学习工程师"},
                    {"id": "b", "position_name": None},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            mapping, errors = module.load_agent_decisions(
                str(path),
                target_position_name="机器学习工程师",
                catalog_names=CATALOG,
                expected_ids=["a", "b"],
            )
            self.assertEqual(errors, [])
            self.assertEqual(mapping["a"], "机器学习工程师")
            self.assertIsNone(mapping["b"])

            path.write_text(json.dumps({
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "results": [{"id": "a", "position_name": "瞎编岗"}],
            }, ensure_ascii=False), encoding="utf-8")
            mapping, errors = module.load_agent_decisions(
                str(path),
                target_position_name="机器学习工程师",
                catalog_names=CATALOG,
                expected_ids=["a"],
            )
            self.assertTrue(errors)
            self.assertEqual(mapping, {})


class SplitModePipelineTests(unittest.TestCase):
    def test_list_only_writes_classify_input(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        job = {
            "encrypt_job_id": "e1",
            "title": "机器学习工程师",
            "boss_name": "真实科技",
            "boss_title": "HR",
            "company_industry": "互联网",
            "job_link": "https://www.zhipin.com/job_detail/e1.html",
            "salary": "30-50K",
            "tags": "Python",
            "job_id": "jid1",
        }

        def fake_scrape_list(*args, **kwargs):
            on_page = kwargs.get("on_page")
            if on_page:
                on_page(1, [job], [job])
            return {"keyword": "机器学习工程师", "city": "上海", "jobs": [job]}

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            out = run = module.run_skillver_list_only_batch(
                position_binding=position,
                catalog_names=CATALOG,
                skillver_seen=ex.empty_seen(),
                search_keyword="机器学习工程师",
                city="上海",
                filters={},
                max_pages=8,
                page_batch_size=2,
                list_start_page=1,
                list_output=str(root / "jobs.json"),
                classify_input_path=str(root / "classify_input.json"),
                batch_index=1,
                cdp_port=9222,
                fmt="json",
                allow_dom_fallback=False,
                scrape_list_fn=fake_scrape_list,
            )
            payload = json.loads(
                pathlib.Path(out["classify_input_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(len(payload["jobs"]), 1)
            self.assertEqual(payload["jobs"][0]["id"], "e1")
            self.assertEqual(payload["jobs"][0]["location"], "上海")
            self.assertEqual(payload["city"], "上海")

    def test_details_from_decisions_scrapes_current_only(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        scraped = []

        def fake_details(data, **kwargs):
            scraped.extend(
                module.resolve_encrypt_job_id(j) for j in data.get("jobs") or []
            )
            return list(data.get("jobs") or [])

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            classify_input = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "batch_index": 1,
                "catalog_names": CATALOG,
                "jobs": [
                    {
                        "id": "c1",
                        "title": "机器学习工程师",
                        "company": "A",
                        "job_link": "https://www.zhipin.com/job_detail/c1.html",
                    },
                    {
                        "id": "o1",
                        "title": "CV",
                        "company": "B",
                        "job_link": "https://www.zhipin.com/job_detail/o1.html",
                    },
                ],
            }
            decisions = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "results": [
                    {"id": "c1", "position_name": "机器学习工程师"},
                    {"id": "o1", "position_name": "CV算法工程师"},
                ],
            }
            cin = root / "in.json"
            dec = root / "dec.json"
            cin.write_text(json.dumps(classify_input, ensure_ascii=False), encoding="utf-8")
            dec.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
            seen = ex.empty_seen()
            module.run_skillver_details_from_decisions(
                position_binding=position,
                catalog_names=CATALOG,
                skillver_seen=seen,
                skillver_seen_path=str(root / "seen.json"),
                classify_input_path=str(cin),
                decisions_path=str(dec),
                detail_output=str(root / "details.json"),
                cdp_port=9222,
                fmt="json",
                scrape_details_fn=fake_details,
            )
            self.assertEqual(scraped, ["c1"])
            self.assertIn("o1", seen["by_position"]["CV算法工程师"]["pending_details"])

    def test_details_from_decisions_writes_match_skip_report_without_nameerror(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }

        def fake_details(data, **kwargs):
            out = []
            for job in data.get("jobs") or []:
                out.append({
                    "encrypt_job_id": module.resolve_encrypt_job_id(job),
                    "company": job.get("boss_name") or "",
                    "location": job.get("location") or "",
                    "salary": job.get("salary") or "40-70K",
                    "jd": "负责机器学习模型训练与上线，覆盖特征、训练与评估全流程。" * 3,
                    "title": job.get("title") or "",
                    "job_link": job.get("job_link") or "",
                })
            path = kwargs.get("output_path")
            if path:
                pathlib.Path(path).write_text(
                    json.dumps(out, ensure_ascii=False), encoding="utf-8"
                )
            return out

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            classify_input = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "batch_index": 1,
                "city": "上海",
                "catalog_names": CATALOG,
                "jobs": [
                    {
                        "id": "c1",
                        "title": "机器学习工程师",
                        "company": "A",
                        "location": "上海·浦东新区",
                        "salary": "40-70K",
                        "job_link": "https://www.zhipin.com/job_detail/c1.html",
                    },
                    {
                        "id": "n1",
                        "title": "运营专员",
                        "company": "B",
                        "location": "上海",
                        "job_link": "https://www.zhipin.com/job_detail/n1.html",
                    },
                ],
            }
            decisions = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "results": [
                    {"id": "c1", "position_name": "机器学习工程师"},
                    {"id": "n1", "position_name": None},
                ],
            }
            cin = root / "in.json"
            dec = root / "dec.json"
            match_report = root / "match_skip.json"
            cin.write_text(json.dumps(classify_input, ensure_ascii=False), encoding="utf-8")
            dec.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
            seen = ex.empty_seen()
            result = module.run_skillver_details_from_decisions(
                position_binding=position,
                catalog_names=CATALOG,
                skillver_seen=seen,
                skillver_seen_path=str(root / "seen.json"),
                classify_input_path=str(cin),
                decisions_path=str(dec),
                detail_output=str(root / "details.json"),
                cdp_port=9222,
                fmt="json",
                match_report_path=str(match_report),
                scrape_details_fn=fake_details,
            )
            self.assertTrue(match_report.is_file())
            payload = json.loads(match_report.read_text(encoding="utf-8"))
            self.assertEqual(payload["skipped_count"], 1)
            self.assertEqual(result["details"][0]["location"], "上海·浦东新区")

    def test_details_from_decisions_preserves_location_into_scrape(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        seen_locations = []

        def fake_details(data, **kwargs):
            for job in data.get("jobs") or []:
                seen_locations.append(job.get("location") or "")
            return []

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            classify_input = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "batch_index": 1,
                "catalog_names": CATALOG,
                "jobs": [
                    {
                        "id": "c1",
                        "title": "机器学习工程师",
                        "company": "A",
                        "location": "上海·徐汇区",
                        "job_link": "https://www.zhipin.com/job_detail/c1.html",
                    },
                ],
            }
            decisions = {
                "schema_version": 1,
                "target_position_name": "机器学习工程师",
                "results": [
                    {"id": "c1", "position_name": "机器学习工程师"},
                ],
            }
            cin = root / "in.json"
            dec = root / "dec.json"
            cin.write_text(json.dumps(classify_input, ensure_ascii=False), encoding="utf-8")
            dec.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
            module.run_skillver_details_from_decisions(
                position_binding=position,
                catalog_names=CATALOG,
                skillver_seen=ex.empty_seen(),
                skillver_seen_path=str(root / "seen.json"),
                classify_input_path=str(cin),
                decisions_path=str(dec),
                detail_output=str(root / "details.json"),
                cdp_port=9222,
                fmt="json",
                city_fallback="北京",
                scrape_details_fn=fake_details,
            )
            self.assertEqual(seen_locations, ["上海·徐汇区"])

    def test_drain_inventory_opens_pending(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        seen = ex.empty_seen()
        ex.mark_classified(
            seen,
            key="p1",
            job={
                "title": "ML",
                "boss_name": "A",
                "job_link": "https://www.zhipin.com/job_detail/p1.html",
            },
            position_name="机器学习工程师",
            classified_by="agent",
            catalog_names=set(CATALOG),
        )
        scraped = []

        def fake_details(data, **kwargs):
            scraped.extend(
                module.resolve_encrypt_job_id(j) for j in data.get("jobs") or []
            )
            for j in data.get("jobs") or []:
                eid = module.resolve_encrypt_job_id(j)
                module.mark_skillver_seen_scraped(
                    kwargs["skillver_seen"],
                    key=eid,
                    job_id=eid,
                    position_name="机器学习工程师",
                    catalog_names=set(CATALOG),
                )
            return list(data.get("jobs") or [])

        with tempfile.TemporaryDirectory() as tmp:
            module.run_skillver_drain_inventory(
                position_binding=position,
                catalog_names=CATALOG,
                skillver_seen=seen,
                skillver_seen_path=str(pathlib.Path(tmp) / "seen.json"),
                detail_output=str(pathlib.Path(tmp) / "d.json"),
                cdp_port=9222,
                fmt="json",
                scrape_details_fn=fake_details,
            )
        self.assertEqual(scraped, ["p1"])

    def test_main_requires_split_mode(self):
        module = load_module()
        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(sys, "argv", [
                "boss_cdp_raw.py",
                "--position-name", "机器学习工程师",
                "--city", "上海",
                "--catalog", str(REPO_ROOT / "data" / "skillver" / "position_catalog.json"),
                "--seen", str(root / "seen.json"),
            ]), \
                    mock.patch.object(module, "require_runtime_dependencies",
                                      return_value=True), \
                    mock.patch.object(module, "resolve_standard_position",
                                      return_value=position), \
                    mock.patch.object(module, "load_position_catalog",
                                      return_value=[position]), \
                    mock.patch.object(module, "load_skillver_seen",
                                      return_value=ex.empty_seen()), \
                    redirect_stdout(io.StringIO()) as out:
                with self.assertRaises(SystemExit) as cm:
                    module.main()
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("分步模式", out.getvalue())

    def test_main_clamps_min_details_over_50(self):
        module = load_module()
        captured = {}

        def fake_drain(**kwargs):
            captured["called"] = True
            return {
                "details": [],
                "details_new_this_run": 0,
                "inventory_pending_snapshot": 0,
                "inventory_attempts": [],
                "details_count": 0,
            }

        position = {
            "position_name": "机器学习工程师",
            "job_intent_id": "J01",
            "job_intent_label": "AI",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with mock.patch.object(sys, "argv", [
                "boss_cdp_raw.py",
                "--position-name", "机器学习工程师",
                "--drain-inventory",
                "--min-details", "80",
                "--catalog", str(REPO_ROOT / "data" / "skillver" / "position_catalog.json"),
                "--seen", str(root / "seen.json"),
                "--detail-output", str(root / "d.json"),
            ]), \
                    mock.patch.object(module, "require_runtime_dependencies",
                                      return_value=True), \
                    mock.patch.object(module, "ensure_scrape_login",
                                      return_value=True), \
                    mock.patch.object(module, "resolve_standard_position",
                                      return_value=position), \
                    mock.patch.object(module, "load_position_catalog",
                                      return_value=[position]), \
                    mock.patch.object(module, "load_skillver_seen",
                                      return_value=ex.empty_seen()), \
                    mock.patch.object(module, "skillver_seen_detail_ids",
                                      return_value=set()), \
                    mock.patch.object(module, "load_seen_encrypt_job_ids",
                                      return_value=set()), \
                    mock.patch.object(
                        module, "run_skillver_drain_inventory",
                        side_effect=fake_drain,
                    ), \
                    redirect_stdout(io.StringIO()) as out:
                module.main()
        self.assertTrue(captured.get("called"))
        self.assertIn("超过上限", out.getvalue())
        self.assertIn("50", out.getvalue())


class ExportPendingTests(unittest.TestCase):
    def test_export_success_removes_pending_export(self):
        seen = ex.empty_seen()
        names = {"预训练算法研究员/工程师"}
        ex.mark_classified(
            seen, key="enc-abc",
            job={"title": "t", "boss_name": "示例科技",
                 "job_link": "http://x", "salary": "40-70K", "location": "上海"},
            position_name="预训练算法研究员/工程师",
            classified_by="agent", catalog_names=names,
        )
        ex.mark_scraped(
            seen, key="enc-abc", job_id="abc",
            position_name="预训练算法研究员/工程师", catalog_names=names,
        )
        details = [{
            "company": "示例科技",
            "location": "上海",
            "salary": "40-70K",
            "jd": "负责预训练算法研究与大规模分布式训练优化工作。",
            "job_id": "abc",
            "encrypt_job_id": "enc-abc",
        }]
        position = {
            "position_name": "预训练算法研究员/工程师",
            "job_intent_id": "J02",
            "job_intent_label": "AI 大模型工程师",
        }
        rows, skipped, pending = ex.export_details(
            details, position, seen=seen, catalog_names=names
        )
        self.assertEqual(len(rows), 1)
        ex.apply_exported_marks(seen, pending, catalog_names=names)
        self.assertEqual(
            seen["by_position"]["预训练算法研究员/工程师"]["pending_export"], []
        )


if __name__ == "__main__":
    unittest.main()
