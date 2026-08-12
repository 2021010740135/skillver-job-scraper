#!/usr/bin/env python3
"""YATN company-job scrape: list → Agent score (>70) → details → CSV.

Does not replace the Skillver standard-position path in boss_cdp_raw.py.
See references/company-job-match.md and data/yatn/companies.csv.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

__version__ = "2.6.0"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPANIES = ROOT / "data" / "yatn" / "companies.csv"
DEFAULT_CATALOG = ROOT / "data" / "skillver" / "position_catalog.json"
DEFAULT_JOBS_DIR = ROOT / "data" / "yatn" / "jobs"
DEFAULT_DETAILS_DIR = ROOT / "data" / "yatn" / "details"
DEFAULT_EXPORTS_DIR = ROOT / "data" / "yatn" / "exports"

CSV_HEADERS = [
    "公司全称",
    "招聘品牌名",
    "优先级",
    "城市标签",
    "企业类型",
    "主要方向",
    "职位名称",
    "岗位薪资",
    "工作地点",
    "标准岗",
    "匹配分",
    "岗位描述",
    "职位链接",
    "encrypt_job_id",
    "来源",
]

_DAILY_SALARY_RE = re.compile(
    r"(元\s*/\s*天|元/日|/天|/日|\bday\b|日薪)",
    re.IGNORECASE,
)


def _load_boss_module():
    path = Path(__file__).resolve().parent / "boss_cdp_raw.py"
    spec = importlib.util.spec_from_file_location("boss_cdp_raw", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def load_companies(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"city", "brand_name", "legal_name", "priority"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError(
                f"companies CSV missing columns {sorted(required)}: {path}"
            )
        for raw in reader:
            brand = str(raw.get("brand_name") or "").strip()
            legal = str(raw.get("legal_name") or "").strip() or brand
            if not brand:
                continue
            aliases = [
                a.strip()
                for a in str(raw.get("aliases") or "").split("|")
                if a.strip()
            ]
            rows.append(
                {
                    "city": str(raw.get("city") or "").strip(),
                    "brand_name": brand,
                    "legal_name": legal,
                    "aliases": aliases,
                    "company_type": str(raw.get("company_type") or "").strip(),
                    "focus": str(raw.get("focus") or "").strip(),
                    "funding_stage": str(raw.get("funding_stage") or "").strip(),
                    "priority": str(raw.get("priority") or "").strip().upper(),
                }
            )
    return rows


def filter_companies(
    companies: list[dict[str, str]],
    *,
    priorities: set[str] | None = None,
    brands: set[str] | None = None,
) -> list[dict[str, str]]:
    out = []
    for c in companies:
        if priorities and c["priority"] not in priorities:
            continue
        if brands and c["brand_name"] not in brands and c["legal_name"] not in brands:
            continue
        out.append(c)
    return out


def company_search_keywords(company: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for key in (company.get("legal_name"), company.get("brand_name")):
        text = str(key or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            ordered.append(text)
    for alias in company.get("aliases") or []:
        text = str(alias or "").strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            ordered.append(text)
    return ordered


def is_daily_salary(salary: str) -> bool:
    text = str(salary or "").strip()
    if not text:
        return False
    return bool(_DAILY_SALARY_RE.search(text))


def _norm_name(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def job_matches_company(job: dict[str, Any], company: dict[str, Any]) -> bool:
    """Keep list cards whose brand/company text hits legal/brand/alias."""
    blob = _norm_name(
        " ".join(
            str(job.get(k) or "")
            for k in ("boss_name", "company", "brand_name", "title")
        )
    )
    if not blob:
        return False
    candidates = company_search_keywords(company)
    for name in candidates:
        token = _norm_name(name)
        if token and token in blob:
            return True
    return False


def load_catalog_names(path: str | Path = DEFAULT_CATALOG) -> list[str]:
    with Path(path).open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("catalog must be a JSON list")
    names = []
    for item in data:
        if isinstance(item, dict):
            name = str(item.get("position_name") or "").strip()
            if name:
                names.append(name)
    return names


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_json(path: str | Path) -> Any:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def merge_jobs_by_encrypt_id(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boss = _load_boss_module()
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for job in jobs:
        eid = boss.resolve_encrypt_job_id(job)
        if not eid:
            key = str(job.get("job_link") or job.get("title") or id(job))
            eid = f"nolink:{key}"
        if eid not in merged:
            merged[eid] = dict(job)
            merged[eid]["encrypt_job_id"] = boss.resolve_encrypt_job_id(job)
            order.append(eid)
        else:
            # Prefer longer salary / richer tags
            old = merged[eid]
            if len(str(job.get("salary") or "")) > len(str(old.get("salary") or "")):
                old["salary"] = job.get("salary")
            if len(str(job.get("tags") or "")) > len(str(old.get("tags") or "")):
                old["tags"] = job.get("tags")
    return [merged[k] for k in order]


def scrape_company(
    company: dict[str, Any],
    *,
    pages: int = 2,
    cdp_port: int = 9222,
    scrape_list_fn=None,
) -> list[dict[str, Any]]:
    boss = _load_boss_module()
    scrape_list_fn = scrape_list_fn or boss.scrape_list
    city = company.get("city") or "上海"
    collected: list[dict[str, Any]] = []
    for keyword in company_search_keywords(company):
        print(f"\n>>> [{company['brand_name']}] 搜索关键词: {keyword} @ {city}")
        list_data = scrape_list_fn(
            keyword,
            city,
            pages,
            {},
            None,
            cdp_port=cdp_port,
            fmt="json",
            allow_dom_fallback=False,
        )
        for job in list_data.get("jobs") or []:
            if not isinstance(job, dict):
                continue
            if is_daily_salary(str(job.get("salary") or "")):
                continue
            if not job_matches_company(job, company):
                continue
            item = dict(job)
            item["yatn_legal_name"] = company["legal_name"]
            item["yatn_brand_name"] = company["brand_name"]
            item["yatn_priority"] = company["priority"]
            item["yatn_city"] = company["city"]
            item["yatn_company_type"] = company.get("company_type") or ""
            item["yatn_focus"] = company.get("focus") or ""
            item["search_keyword"] = keyword
            collected.append(item)
    return merge_jobs_by_encrypt_id(collected)


def scrape_companies(
    companies: list[dict[str, Any]],
    *,
    pages: int = 2,
    cdp_port: int = 9222,
    jobs_output: str | Path,
    scrape_list_fn=None,
) -> list[dict[str, Any]]:
    boss = _load_boss_module()
    if not boss.ensure_scrape_login(cdp_port):
        raise SystemExit(1)
    all_jobs: list[dict[str, Any]] = []
    for company in companies:
        jobs = scrape_company(
            company,
            pages=pages,
            cdp_port=cdp_port,
            scrape_list_fn=scrape_list_fn,
        )
        print(f"=== {company['brand_name']}: 保留 {len(jobs)} 条（去重+过滤后）")
        all_jobs.extend(jobs)
    all_jobs = merge_jobs_by_encrypt_id(all_jobs)
    write_json(jobs_output, {"scraped_at": datetime.now().isoformat(), "jobs": all_jobs})
    print(f"列表已写: {jobs_output} ({len(all_jobs)} 条)")
    return all_jobs


def fetch_details_for_jobs(
    jobs: list[dict[str, Any]],
    *,
    detail_output: str | Path,
    cdp_port: int = 9222,
    max_details: int | None = None,
    scrape_details_fn=None,
) -> list[dict[str, Any]]:
    boss = _load_boss_module()
    scrape_details_fn = scrape_details_fn or boss.scrape_details
    # Attach yatn fields onto detail records after scrape
    meta_by_eid = {}
    for job in jobs:
        eid = boss.resolve_encrypt_job_id(job)
        if eid:
            meta_by_eid[eid] = {
                k: job.get(k)
                for k in (
                    "yatn_legal_name",
                    "yatn_brand_name",
                    "yatn_priority",
                    "yatn_city",
                    "yatn_company_type",
                    "yatn_focus",
                    "position_name",
                    "match_score",
                )
                if job.get(k) is not None and job.get(k) != ""
            }

    details = scrape_details_fn(
        {"jobs": jobs},
        max_details=max_details,
        output_path=str(detail_output),
        cdp_port=cdp_port,
        fmt="json",
        skip_headhunter_filter=False,
    )
    enriched = []
    for detail in details or []:
        if not isinstance(detail, dict):
            continue
        if is_daily_salary(str(detail.get("salary") or "")):
            continue
        eid = boss.resolve_encrypt_job_id(detail)
        meta = meta_by_eid.get(eid) or {}
        row = dict(detail)
        row.update({k: v for k, v in meta.items() if v})
        enriched.append(row)
    write_json(detail_output, enriched)
    print(f"详情已写: {detail_output} ({len(enriched)} 条)")
    return enriched


def _job_tags_for_match(job: dict[str, Any]) -> str:
    tags = job.get("tags_list") or job.get("tags") or job.get("job_labels") or ""
    if isinstance(tags, list):
        return "|".join(str(t) for t in tags if t)
    skills = job.get("skill_tags") or job.get("skills") or ""
    if isinstance(skills, list):
        skills_s = "|".join(str(t) for t in skills if t)
    else:
        skills_s = str(skills or "").strip()
    tags_s = str(tags or "").strip()
    if tags_s and skills_s and skills_s not in tags_s:
        return f"{tags_s}|{skills_s}"
    return tags_s or skills_s


def jobs_to_match_input(
    jobs: list[dict[str, Any]],
    *,
    catalog_names: list[str],
    batch_id: str,
) -> dict[str, Any]:
    """Build Agent match input from list cards (no JD required)."""
    boss = _load_boss_module()
    out: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        eid = boss.resolve_encrypt_job_id(job)
        if not eid:
            continue
        if is_daily_salary(str(job.get("salary") or "")):
            continue
        out.append(
            {
                "id": eid,
                "legal_name": job.get("yatn_legal_name")
                or job.get("company")
                or "",
                "brand_name": job.get("yatn_brand_name")
                or job.get("boss_name")
                or "",
                "title": job.get("title") or "",
                "salary": job.get("salary") or "",
                "location": job.get("location") or "",
                "tags": _job_tags_for_match(job),
                "boss_title": job.get("boss_title") or "",
            }
        )
    return {
        "schema_version": 1,
        "batch_id": batch_id,
        "catalog_names": list(catalog_names),
        "jobs": out,
    }


def details_to_match_input(
    details: list[dict[str, Any]],
    *,
    catalog_names: list[str],
    batch_id: str,
) -> dict[str, Any]:
    """Deprecated path: prefer jobs_to_match_input on list cards."""
    return jobs_to_match_input(
        details, catalog_names=catalog_names, batch_id=batch_id
    )


def validate_match_scores(
    payload: dict[str, Any],
    *,
    expected_ids: list[str],
    catalog_names: list[str],
) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["匹配结果必须是 JSON 对象"]
    if payload.get("schema_version") != 1:
        errors.append("schema_version 必须为 1")
    results = payload.get("results")
    if not isinstance(results, list):
        errors.append("results 必须为数组")
        return errors
    catalog_set = set(catalog_names)
    seen: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            errors.append("results 项必须是对象")
            continue
        eid = str(item.get("id") or "").strip()
        if not eid:
            errors.append("存在空 id")
            continue
        if eid in seen:
            errors.append(f"重复 id: {eid}")
        seen.add(eid)
        pos = item.get("position_name")
        if pos is not None:
            pos_s = str(pos).strip()
            if pos_s not in catalog_set:
                errors.append(f"非法 position_name: {pos_s!r}")
        try:
            score = int(item.get("score"))
        except (TypeError, ValueError):
            errors.append(f"id={eid} score 必须是整数")
            continue
        if score < 0 or score > 100:
            errors.append(f"id={eid} score 越界: {score}")
    expected = set(expected_ids)
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        if missing:
            errors.append(f"缺少 id: {missing[:5]}")
        if extra:
            errors.append(f"多余 id: {extra[:5]}")
    return errors


def apply_match_scores(
    details: list[dict[str, Any]],
    scores_payload: dict[str, Any],
    *,
    min_score: int = 71,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (accepted, skipped). min_score default 71 means score > 70."""
    boss = _load_boss_module()
    by_id = {
        str(item.get("id") or "").strip(): item
        for item in (scores_payload.get("results") or [])
        if isinstance(item, dict)
    }
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for detail in details:
        eid = boss.resolve_encrypt_job_id(detail)
        dec = by_id.get(eid) or {}
        try:
            score = int(dec.get("score"))
        except (TypeError, ValueError):
            score = -1
        pos = dec.get("position_name")
        pos_s = str(pos).strip() if pos is not None else ""
        row = dict(detail)
        row["match_score"] = score
        row["position_name"] = pos_s
        if score >= min_score and pos_s:
            accepted.append(row)
        else:
            row["skip_reason"] = (
                "low_score_or_null_position"
                if score >= 0
                else "missing_score"
            )
            skipped.append(row)
    return accepted, skipped


def detail_to_export_row(detail: dict[str, Any]) -> dict[str, str]:
    jd = str(detail.get("jd") or "")
    jd = re.sub(r"\s+", " ", jd).replace(",", "，").strip()
    tags = detail.get("skill_tags") or []
    if isinstance(tags, list) and tags and not detail.get("tags_list"):
        pass
    return {
        "公司全称": str(detail.get("yatn_legal_name") or detail.get("company") or ""),
        "招聘品牌名": str(detail.get("yatn_brand_name") or ""),
        "优先级": str(detail.get("yatn_priority") or ""),
        "城市标签": str(detail.get("yatn_city") or ""),
        "企业类型": str(detail.get("yatn_company_type") or ""),
        "主要方向": str(detail.get("yatn_focus") or ""),
        "职位名称": str(detail.get("title") or ""),
        "岗位薪资": str(detail.get("salary") or ""),
        "工作地点": str(detail.get("location") or ""),
        "标准岗": str(detail.get("position_name") or ""),
        "匹配分": str(detail.get("match_score") if detail.get("match_score") is not None else ""),
        "岗位描述": jd,
        "职位链接": str(detail.get("job_link") or detail.get("link") or ""),
        "encrypt_job_id": str(detail.get("encrypt_job_id") or ""),
        "来源": "boss",
    }


def export_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()
        for detail in rows:
            writer.writerow(detail_to_export_row(detail))
    print(f"CSV 已写: {path} ({len(rows)} 行)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"YATN 按企业采集 BOSS 在招岗 v{__version__}",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--companies",
        default=str(DEFAULT_COMPANIES),
        help=f"企业表 CSV（默认 {DEFAULT_COMPANIES}）",
    )
    p.add_argument(
        "--priority",
        default="S,A",
        help="要跑的优先级，逗号分隔（默认 S,A）",
    )
    p.add_argument(
        "--brand",
        action="append",
        default=None,
        help="只跑指定品牌（可重复）；默认全表过滤后的企业",
    )
    p.add_argument("--pages", type=int, default=2, help="每个关键词搜索页数（默认 2）")
    p.add_argument("--cdp-port", type=int, default=9222)
    p.add_argument(
        "--jobs-output",
        default="",
        help="列表 JSON 输出路径",
    )
    p.add_argument(
        "--details-output",
        default="",
        help="详情 JSON 输出路径",
    )
    p.add_argument(
        "--scrape-list",
        action="store_true",
        help="抓取列表（按企业多关键词）",
    )
    p.add_argument(
        "--scrape-details",
        action="store_true",
        help="对列表/录取 JSON 开详情（应先 --apply-scores；传录取文件作 --jobs-output）",
    )
    p.add_argument(
        "--write-match-input",
        action="store_true",
        help="从列表 JSON（--jobs-output）写 Agent 匹配输入（无 JD）",
    )
    p.add_argument(
        "--match-input",
        default="",
        help="match_input JSON 路径",
    )
    p.add_argument(
        "--apply-scores",
        default="",
        metavar="PATH",
        help="应用 Agent match_scores JSON，从列表筛出录取岗（再开详情）",
    )
    p.add_argument(
        "--accepted-output",
        default="",
        help="score>70 的录取列表 JSON（供 --scrape-details）",
    )
    p.add_argument(
        "--export-csv",
        default="",
        help="从 accepted 详情（或 --details-output）导出 CSV",
    )
    p.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help="标准岗 catalog",
    )
    p.add_argument(
        "--batch-id",
        default="",
        help="匹配批次 id（默认日期_时间）",
    )
    p.add_argument(
        "--min-score",
        type=int,
        default=71,
        help="录取阈值（默认 71，即 score>70）",
    )
    return p


def _default_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stamp = _default_stamp()
    jobs_output = Path(args.jobs_output) if args.jobs_output else (
        DEFAULT_JOBS_DIR / f"company_jobs_{stamp}.json"
    )
    details_output = Path(args.details_output) if args.details_output else (
        DEFAULT_DETAILS_DIR / f"company_details_{stamp}.json"
    )
    match_input_path = Path(args.match_input) if args.match_input else (
        DEFAULT_EXPORTS_DIR / f"match_input_{stamp}.json"
    )
    accepted_output = Path(args.accepted_output) if args.accepted_output else (
        DEFAULT_DETAILS_DIR / f"company_accepted_{stamp}.json"
    )

    priorities = {
        p.strip().upper()
        for p in str(args.priority or "").split(",")
        if p.strip()
    }
    brands = set(args.brand) if args.brand else None

    ran = False
    companies = filter_companies(
        load_companies(args.companies),
        priorities=priorities or None,
        brands=brands,
    )
    if args.scrape_list:
        ran = True
        if not companies:
            raise SystemExit("没有可抓取的企业（检查 --priority / --brand）")
        print(f"将抓取 {len(companies)} 家企业: {[c['brand_name'] for c in companies]}")
        scrape_companies(
            companies,
            pages=max(1, int(args.pages)),
            cdp_port=args.cdp_port,
            jobs_output=jobs_output,
        )

    if args.scrape_details:
        ran = True
        payload = read_json(jobs_output)
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list) or not jobs:
            raise SystemExit(f"列表为空，无法开详情: {jobs_output}")
        fetch_details_for_jobs(
            jobs,
            detail_output=details_output,
            cdp_port=args.cdp_port,
        )

    if args.write_match_input:
        ran = True
        payload = read_json(jobs_output)
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            raise SystemExit(f"列表 JSON 无效: {jobs_output}")
        batch_id = args.batch_id or stamp
        catalog_names = load_catalog_names(args.catalog)
        match_input = jobs_to_match_input(
            jobs,
            catalog_names=catalog_names,
            batch_id=batch_id,
        )
        write_json(match_input_path, match_input)
        print(
            f"匹配输入已写: {match_input_path} "
            f"({len(match_input['jobs'])} 条)；"
            f"请按 references/company-job-match.md 写出 scores"
        )

    if args.apply_scores:
        ran = True
        payload = read_json(jobs_output)
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(jobs, list):
            raise SystemExit(f"列表 JSON 无效，无法应用分数: {jobs_output}")
        scores = read_json(args.apply_scores)
        catalog_names = load_catalog_names(args.catalog)
        boss = _load_boss_module()
        if match_input_path.is_file():
            match_payload = read_json(match_input_path)
            expected_ids = [
                str(j.get("id") or "").strip()
                for j in (match_payload.get("jobs") or [])
                if isinstance(j, dict) and str(j.get("id") or "").strip()
            ]
        else:
            expected_ids = [
                boss.resolve_encrypt_job_id(d)
                for d in jobs
                if isinstance(d, dict) and boss.resolve_encrypt_job_id(d)
            ]
        errors = validate_match_scores(
            scores,
            expected_ids=expected_ids,
            catalog_names=catalog_names,
        )
        if errors:
            raise SystemExit("匹配结果不合契约: " + "; ".join(errors))
        accepted, skipped = apply_match_scores(
            jobs,
            scores,
            min_score=int(args.min_score),
        )
        write_json(accepted_output, {"jobs": accepted})
        skip_path = DEFAULT_EXPORTS_DIR / f"match_skip_{stamp}.json"
        write_json(skip_path, {"skipped_count": len(skipped), "skipped": skipped})
        print(
            f"录取 {len(accepted)} / 跳过 {len(skipped)}；"
            f"accepted → {accepted_output}（再对其 --scrape-details）"
        )

    if args.export_csv:
        ran = True
        src = details_output
        if accepted_output.is_file() and not details_output.is_file():
            # Prefer details with JD; fall back only if details missing
            src = accepted_output
        payload = read_json(src)
        if isinstance(payload, dict) and isinstance(payload.get("jobs"), list):
            rows = payload["jobs"]
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = []
        export_csv(rows, args.export_csv)

    if not ran:
        build_parser().print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    main()
