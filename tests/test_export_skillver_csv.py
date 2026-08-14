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
CATALOG_PATH = REPO_ROOT / "data" / "skillver" / "position_catalog.json"


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
        self.assertEqual(row["招聘品牌名"], "示例科技")
        self.assertEqual(row["所在城市"], "上海")
        self.assertEqual(row["一级编号"], "J02")
        self.assertEqual(row["一级岗位名称"], "AI 大模型工程师")
        self.assertEqual(row["岗位名称"], "预训练算法研究员/工程师")
        self.assertNotIn("\n", row["岗位描述"])
        self.assertEqual(row["岗位base地"], "上海·徐汇区·漕河泾")
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
        self.assertEqual(row["岗位base地"], "上海·浦东新区")

    def test_location_with_embedded_middle_dot_extracts_city(self):
        """Address like 上海浦东新区…T5(模力·栈)T5 yields 上海, not the pre-dot prefix."""
        detail = {
            "company": "小鹏汽车",
            "location": "上海浦东新区张江科学之门T5(模力·栈)T5（小鹏汽车）",
            "salary": "40K-70K",
            "jd": "这是一段足够长的岗位描述用于通过长度检查。",
        }
        row, reason = ex.detail_to_row(detail, self.position)
        self.assertIsNone(reason)
        self.assertEqual(row["所在城市"], "上海")
        self.assertEqual(
            row["岗位base地"], "上海浦东新区张江科学之门T5(模力·栈)T5（小鹏汽车）"
        )

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
        path = ex.default_output_path()
        self.assertTrue(path.name.startswith("job_"))
        self.assertTrue(path.name.endswith(".csv"))
        self.assertEqual(len(path.stem), len("job_YYYYMMDD"))

    def test_cleanup_dedupes_company_position(self):
        rows = [
            {
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
        self.assertEqual(len(cleaned), 1)
        self.assertEqual(dupes, 1)
        self.assertEqual(skipped, [])
        self.assertIn("更长的岗位描述", cleaned[0]["岗位描述"])


class SeenHelpersTests(unittest.TestCase):
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
                    "--report",
                    str(report_path),
                ]
            )
            self.assertTrue(out_path.is_file())
            with out_path.open(encoding="utf-8-sig", newline="") as f:
                reader = list(csv.DictReader(f))
            self.assertEqual(len(reader), 1)
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
                    "--dry-run",
                ]
            )
            self.assertFalse(out_path.exists())
            self.assertFalse(seen_path.exists())

    def test_cli_unknown_position(self):
        with tempfile.TemporaryDirectory() as tmp:
            details_path = Path(tmp) / "details.json"
            details_path.write_text("[]", encoding="utf-8")
            with self.assertRaises(SystemExit) as ctx:
                ex.main(
                    [
                        "--details",
                        str(details_path),
                        "--position-name",
                        "完全不存在",
                        "--catalog",
                        str(CATALOG_PATH),
                        "--output",
                        str(Path(tmp) / "out.csv"),
                        "--seen",
                        str(Path(tmp) / "seen.json"),
                    ]
                )
            self.assertIn("unknown", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
