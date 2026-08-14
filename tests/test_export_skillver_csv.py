#!/usr/bin/env python3
"""Unit tests for scripts/export_skillver_csv.py (no network)."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import export_skillver_csv as ex

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "data" / "position_catalog.json"


class SalaryParseTests(unittest.TestCase):
    def test_range_variants(self):
        self.assertEqual(ex.parse_salary_skillver("40-70K"), "40K-70K")
        self.assertEqual(ex.parse_salary_skillver("40-70K·20薪"), "40K-70K")
        self.assertEqual(ex.parse_salary_skillver("40K-70K"), "40K-70K")
        self.assertEqual(ex.parse_salary_skillver("2-3K"), "2K-3K")
        self.assertEqual(ex.parse_salary_skillver("20-28K·13薪"), "20K-28K")

    def test_negotiable_and_invalid(self):
        self.assertIsNone(ex.parse_salary_skillver("面议"))
        self.assertIsNone(ex.parse_salary_skillver(""))
        self.assertIsNone(ex.parse_salary_skillver("70-40K"))
        self.assertIsNone(ex.parse_salary_skillver("200-300元/天"))


class CatalogResolveTests(unittest.TestCase):
    def test_resolve_known_position(self):
        catalog = ex.load_catalog(CATALOG_PATH)
        pos = ex.resolve_position(catalog, "预训练算法研究员/工程师")
        self.assertEqual(pos["job_intent_id"], "J02")
        self.assertEqual(pos["job_intent_label"], "AI 大模型工程师")
        self.assertEqual(pos["position_name"], "预训练算法研究员/工程师")

    def test_unknown_position_exits(self):
        catalog = ex.load_catalog(CATALOG_PATH)
        with self.assertRaises(SystemExit) as ctx:
            ex.resolve_position(catalog, "不存在的岗位")
        self.assertIn("unknown", str(ctx.exception))


class RowMappingTests(unittest.TestCase):
    def setUp(self):
        self.position = {
            "position_name": "预训练算法研究员/工程师",
            "job_intent_id": "J02",
            "job_intent_label": "AI 大模型工程师",
        }

    def test_valid_detail_columns(self):
        detail = {
            "company": "示例科技",
            "location": "上海·徐汇区·漕河泾",
            "salary": "40-70K·20薪",
            "jd": "负责大模型预训练与数据配方，推动训练效率与效果提升。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(reason)
        self.assertEqual(list(row.keys()), ex.CSV_HEADERS)
        self.assertEqual(row["企业名称"], "示例科技")
        self.assertEqual(row["招聘品牌名"], "示例科技")
        self.assertEqual(row["所在城市"], "上海")
        self.assertEqual(row["一级编号"], "J02")
        self.assertEqual(row["一级岗位名称"], "AI 大模型工程师")
        self.assertEqual(row["岗位名称"], "预训练算法研究员/工程师")
        self.assertNotIn("\n", row["岗位描述"])
        self.assertEqual(row["岗位base地"], "上海")
        self.assertEqual(row["岗位薪资"], "40K-70K")
        self.assertRegex(row["岗位薪资"], r"^\d+K-\d+K$")

    def test_empty_company_skipped(self):
        detail = {
            "company": "  ",
            "location": "上海",
            "salary": "40-70K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(row)
        self.assertEqual(reason, "empty_company")

    def test_negotiable_salary_skipped(self):
        detail = {
            "company": "示例科技",
            "location": "上海",
            "salary": "面议",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(row)
        self.assertEqual(reason, "salary_unparsed")

    def test_city_fallback(self):
        detail = {
            "company": "示例科技",
            "location": "",
            "salary": "40K-70K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position, city_fallback="北京")
        self.assertIsNone(reason)
        self.assertEqual(row["所在城市"], "北京")
        self.assertEqual(row["岗位base地"], "北京")

    def test_location_without_city_cli_fallback_exports(self):
        """Detail location alone is enough; export --city is optional fallback."""
        detail = {
            "company": "示例科技",
            "location": "上海·浦东新区",
            "salary": "40K-70K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(reason)
        self.assertEqual(row["所在城市"], "上海")
        self.assertEqual(row["岗位base地"], "上海")

    def test_empty_location_without_fallback_skipped(self):
        detail = {
            "company": "示例科技",
            "location": "",
            "salary": "40K-70K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(row)
        self.assertEqual(reason, "empty_city")

    def test_jd_strips_ascii_comma_and_quotes(self):
        detail = {
            "company": "酷哇科技",
            "location": "上海",
            "salary": "40-70K",
            "jd": '"设计并实现端到端系统,解决自动驾驶问题"',
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(reason)
        self.assertNotIn(",", row["岗位描述"])
        self.assertNotIn('"', row["岗位描述"])
        self.assertIn("，", row["岗位描述"])

    def test_salary_too_low_skipped(self):
        detail = {
            "company": "远景能源",
            "location": "上海",
            "salary": "2-3K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(row)
        self.assertEqual(reason, "salary_too_low")

    def test_mislabeled_hr_skipped(self):
        detail = {
            "company": "长松之道（长松咨询）",
            "location": "上海",
            "salary": "10-15K",
            "title": "人力资源经理",
            "jd": "人力资源/管理专业 适应长期出差 国内咨询机构岗位说明足够长。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(row)
        self.assertEqual(reason, "mislabeled_hr_sales")

    def test_write_csv_does_not_quote_jd(self):
        rows = [
            {
                "企业名称": "酷哇科技",
                "招聘品牌名": "酷哇科技",
                "所在城市": "上海",
                "一级编号": "J01",
                "一级岗位名称": "AI 算法工程师",
                "岗位名称": "机器学习工程师",
                "岗位描述": "设计系统，解决规划问题",
                "岗位base地": "上海",
                "岗位薪资": "40K-70K",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.csv"
            ex.write_csv(out, rows)
            text = out.read_text(encoding="utf-8-sig")
            self.assertNotIn('"', text)

    def test_default_output_path_dated(self):
        path = ex.default_output_path("Agent工程师")
        self.assertTrue(path.name.startswith("job_"))
        self.assertTrue(path.name.endswith(".csv"))
        self.assertEqual(len(path.stem), len("job_YYYYMMDD"))
        self.assertEqual(path.parent.name, "Agent工程师")

    def test_cleanup_keeps_same_company_standard_position(self):
        rows = [
            {
                "企业名称": "得物App",
                "招聘品牌名": "得物App",
                "所在城市": "上海",
                "一级编号": "J01",
                "一级岗位名称": "AI 算法工程师",
                "岗位名称": "机器学习工程师",
                "岗位描述": "短描述足够长了啊啊啊",
                "岗位base地": "上海",
                "岗位薪资": "40K-70K",
            },
            {
                "企业名称": "得物App",
                "招聘品牌名": "得物App",
                "所在城市": "上海",
                "一级编号": "J01",
                "一级岗位名称": "AI 算法工程师",
                "岗位名称": "机器学习工程师",
                "岗位描述": "更长的岗位描述用于优先保留这一条内容啊啊啊啊啊",
                "岗位base地": "上海",
                "岗位薪资": "40K-70K",
            },
        ]
        cleaned, skipped, dupes = ex.cleanup_csv_rows(rows)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(dupes, 0)
        self.assertEqual(skipped, [])


class SeenHelpersTests(unittest.TestCase):
    def test_default_seen_path_is_global(self):
        self.assertEqual(ex.default_seen_path(), ex.DEFAULT_SEEN_PATH)
        self.assertEqual(ex.default_seen_path("阶跃星辰"), ex.DEFAULT_SEEN_PATH)
        self.assertEqual(ex.DEFAULT_SEEN_PATH, Path("data") / "seen_jobs.json")

    def test_listed_is_not_classified(self):
        seen = ex.empty_seen()
        ex.mark_listed(
            seen,
            key="enc-1",
            job={"title": "ML", "boss_name": "A"},
            query="阶跃星辰",
        )
        self.assertTrue(ex.job_in_seen(seen, "enc-1"))
        self.assertFalse(ex.is_classified(seen, "enc-1"))
        self.assertEqual(seen["jobs"]["enc-1"]["query"], "阶跃星辰")

    def test_mark_and_is_exported(self):
        seen = ex.empty_seen()
        self.assertFalse(ex.is_exported(seen, "enc-1"))
        ex.mark_exported(
            seen,
            key="enc-1",
            job_id="jid-1",
            position_name="预训练算法研究员/工程师",
            exported_at="2026-08-08T00:00:00+00:00",
        )
        self.assertTrue(ex.is_exported(seen, "enc-1"))
        entry = seen["jobs"]["enc-1"]
        self.assertEqual(entry["job_id"], "jid-1")
        self.assertTrue(entry["has_details"])
        self.assertTrue(entry["exported"])
        self.assertEqual(entry["exported_at"], "2026-08-08T00:00:00+00:00")


class CliExportTests(unittest.TestCase):
    def test_cli_writes_csv(self):
        details = [
            {
                "company": "示例科技",
                "location": "上海·浦东新区",
                "salary": "40-70K·20薪",
                "jd": "负责预训练算法研究与大规模分布式训练优化工作。",
                "job_id": "abc",
                "encrypt_job_id": "enc-abc",
                "title": "预训练工程师",
            },
            {
                "company": "",
                "location": "上海",
                "salary": "40-70K",
                "jd": "空公司应被跳过的足够长描述文本。",
            },
            {
                "company": "面议公司",
                "location": "上海",
                "salary": "面议",
                "jd": "面议薪资应被跳过的足够长描述文本。",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            details_path = tmp_path / "details.json"
            out_path = tmp_path / "job_20260810.csv"
            report_path = tmp_path / "report.json"
            seen_path = tmp_path / "seen_jobs.json"
            details_path.write_text(
                json.dumps(details, ensure_ascii=False), encoding="utf-8"
            )
            ex.main(
                [
                    "--details",
                    str(details_path),
                    "--position-name",
                    "预训练算法研究员/工程师",
                    "--catalog",
                    str(CATALOG_PATH),
                    "--output",
                    str(out_path),
                    "--seen",
                    str(seen_path),
                    "--unexported",
                    str(tmp_path / "unexported.json"),
                    "--report",
                    str(report_path),
                ]
            )
            self.assertTrue(out_path.is_file())
            with out_path.open(encoding="utf-8-sig", newline="") as f:
                reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0]["企业名称"], "示例科技")
            self.assertEqual(reader[0]["招聘品牌名"], "示例科技")
            self.assertEqual(reader[0]["岗位薪资"], "40K-70K")
            self.assertEqual(reader[0]["岗位名称"], "预训练算法研究员/工程师")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["exported_count"], 1)
            self.assertEqual(report["skipped_count"], 2)
            seen = json.loads(seen_path.read_text(encoding="utf-8"))
            self.assertTrue(seen["jobs"]["enc-abc"]["exported"])

    def test_second_export_skips_already_exported(self):
        details = [
            {
                "company": "示例科技",
                "location": "上海·浦东新区",
                "salary": "40-70K·20薪",
                "jd": "负责预训练算法研究与大规模分布式训练优化工作。",
                "job_id": "abc",
                "encrypt_job_id": "enc-dup-1",
                "title": "预训练工程师",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            details_path = tmp_path / "details.json"
            out_path = tmp_path / "job_20260810.csv"
            seen_path = tmp_path / "seen_jobs.json"
            report1 = tmp_path / "report1.json"
            report2 = tmp_path / "report2.json"
            details_path.write_text(
                json.dumps(details, ensure_ascii=False), encoding="utf-8"
            )
            common = [
                "--details",
                str(details_path),
                "--position-name",
                "预训练算法研究员/工程师",
                "--catalog",
                str(CATALOG_PATH),
                "--output",
                str(out_path),
                "--seen",
                str(seen_path),
                "--unexported",
                str(tmp_path / "unexported.json"),
            ]
            ex.main(common + ["--report", str(report1)])
            ex.main(common + ["--append", "--report", str(report2)])

            with out_path.open(encoding="utf-8-sig", newline="") as f:
                reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)

            r1 = json.loads(report1.read_text(encoding="utf-8"))
            r2 = json.loads(report2.read_text(encoding="utf-8"))
            self.assertEqual(r1["exported_count"], 1)
            self.assertEqual(r2["exported_count"], 0)
            self.assertEqual(r2["skipped_count"], 1)
            self.assertEqual(r2["skipped"][0]["reason"], "already_exported")

            seen = json.loads(seen_path.read_text(encoding="utf-8"))
            self.assertTrue(seen["jobs"]["enc-dup-1"]["exported"])

    def test_dry_run_does_not_update_seen(self):
        details = [
            {
                "company": "示例科技",
                "location": "上海",
                "salary": "40-70K",
                "jd": "负责预训练算法研究与大规模分布式训练优化工作。",
                "job_id": "abc",
                "encrypt_job_id": "enc-dry",
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            details_path = tmp_path / "details.json"
            out_path = tmp_path / "job_20260810.csv"
            seen_path = tmp_path / "seen_jobs.json"
            details_path.write_text(
                json.dumps(details, ensure_ascii=False), encoding="utf-8"
            )
            ex.main(
                [
                    "--details",
                    str(details_path),
                    "--position-name",
                    "预训练算法研究员/工程师",
                    "--catalog",
                    str(CATALOG_PATH),
                    "--output",
                    str(out_path),
                    "--seen",
                    str(seen_path),
                    "--unexported",
                    str(tmp_path / "unexported.json"),
                    "--dry-run",
                ]
            )
            self.assertFalse(out_path.exists())
            self.assertFalse(seen_path.exists())

    def test_export_uses_per_row_catalog_position(self):
        catalog = [
            {
                "position_name": "机器学习工程师",
                "job_intent_id": "J01",
                "job_intent_label": "AI 算法工程师",
            },
            {
                "position_name": "CV算法工程师",
                "job_intent_id": "J03",
                "job_intent_label": "AI 视觉工程师",
            },
        ]
        details = [
            {
                "company": "甲科技",
                "location": "上海",
                "salary": "40-70K",
                "jd": "负责机器学习模型训练与上线的足够长描述。",
                "encrypt_job_id": "a1",
                "position_name": "机器学习工程师",
            },
            {
                "company": "乙科技",
                "location": "上海",
                "salary": "40-70K",
                "jd": "负责计算机视觉算法研发的足够长描述文本。",
                "encrypt_job_id": "b1",
                "position_name": "CV算法工程师",
            },
        ]
        rows, skipped, pending = ex.export_details(
            details, None, catalog=catalog, seen=ex.empty_seen()
        )
        self.assertEqual(skipped, [])
        self.assertEqual([row["岗位名称"] for row in rows], ["机器学习工程师", "CV算法工程师"])
        self.assertEqual([row["一级编号"] for row in rows], ["J01", "J03"])
        self.assertEqual({item["position_name"] for item in pending}, {
            "机器学习工程师",
            "CV算法工程师",
        })

    def test_export_keeps_same_catalog_position_different_jobs(self):
        catalog = [
            {
                "position_name": "AI平台工程师",
                "job_intent_id": "J06",
                "job_intent_label": "AI 基础设施 / MLOps",
            },
        ]
        details = [
            {
                "company": "上海阶跃星辰智能科技",
                "location": "上海",
                "salary": "30-60K",
                "jd": "负责大模型相关业务的服务端研发工作足够长。",
                "encrypt_job_id": "a1",
                "position_name": "AI平台工程师",
            },
            {
                "company": "上海阶跃星辰智能科技",
                "location": "上海",
                "salary": "50-80K",
                "jd": "infra 团队招聘推理与平台方向的足够长描述。",
                "encrypt_job_id": "b1",
                "position_name": "AI平台工程师",
            },
        ]
        rows, skipped, pending = ex.export_details(
            details, None, catalog=catalog, seen=ex.empty_seen()
        )
        self.assertEqual(skipped, [])
        self.assertEqual(len(rows), 2)
        self.assertEqual({item["key"] for item in pending}, {"a1", "b1"})

    def test_cli_unknown_position_name_is_query_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            details_path = Path(tmp) / "details.json"
            details_path.write_text("[]", encoding="utf-8")
            out_path = Path(tmp) / "out.csv"
            ex.main(
                [
                    "--details",
                    str(details_path),
                    "--query",
                    "完全不存在",
                    "--catalog",
                    str(CATALOG_PATH),
                    "--output",
                    str(out_path),
                    "--seen",
                    str(Path(tmp) / "seen.json"),
                    "--unexported",
                    str(Path(tmp) / "unexported.json"),
                ]
            )
            self.assertTrue(out_path.is_file())


class UnexportedDetailsTests(unittest.TestCase):
    def test_add_and_remove_unexported(self):
        store = ex.empty_unexported()
        ex.add_unexported(
            store,
            key="a1",
            query="阶跃星辰",
            details_path="data/阶跃星辰/details.json",
            position_name="机器学习工程师",
        )
        self.assertIn("a1", store["jobs"])
        ex.remove_unexported(store, ["a1"])
        self.assertNotIn("a1", store["jobs"])

    def test_export_cli_merges_unexported_and_clears(self):
        catalog = [
            {
                "position_name": "机器学习工程师",
                "job_intent_id": "J01",
                "job_intent_label": "AI 算法工程师",
            },
        ]
        detail = {
            "company": "甲科技",
            "location": "上海",
            "salary": "40-70K",
            "jd": "负责机器学习模型训练与上线的足够长描述。",
            "encrypt_job_id": "left1",
            "position_name": "机器学习工程师",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leftover_path = root / "old_details.json"
            leftover_path.write_text(
                json.dumps([detail], ensure_ascii=False), encoding="utf-8"
            )
            unexported = ex.empty_unexported()
            ex.add_unexported(
                unexported,
                key="left1",
                query="阶跃星辰",
                details_path=str(leftover_path),
                position_name="机器学习工程师",
            )
            unexported_path = root / "unexported.json"
            ex.save_unexported(unexported_path, unexported)
            empty_details = root / "details.json"
            empty_details.write_text("[]", encoding="utf-8")
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(catalog, ensure_ascii=False), encoding="utf-8"
            )
            out_path = root / "out.csv"
            seen_path = root / "seen.json"
            ex.main([
                "--details", str(empty_details),
                "--query", "阶跃星辰",
                "--catalog", str(catalog_path),
                "--output", str(out_path),
                "--seen", str(seen_path),
                "--unexported", str(unexported_path),
            ])
            self.assertTrue(out_path.is_file())
            leftover = ex.load_unexported(unexported_path)
            self.assertNotIn("left1", leftover["jobs"])
            seen = ex.load_seen(seen_path)
            self.assertTrue(ex.is_exported(seen, "left1"))


if __name__ == "__main__":
    unittest.main()
