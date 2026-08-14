#!/usr/bin/env python3
"""Details scrape CLI: apply Agent decisions and open catalog-mapped pages."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.boss_common import (
    DEFAULT_CDP_PORT,
    DEFAULT_CITY_INPUT,
    DEFAULT_SKILLVER_CATALOG,
    DEFAULT_SKILLVER_SEEN,
    DEFAULT_SKILLVER_UNEXPORTED,
    __version__,
    catalog_position_names,
    close_chrome_if_requested,
    default_skillver_output_paths,
    ensure_scrape_login,
    ensure_skill_env,
    load_position_catalog,
    load_skillver_seen,
    require_runtime_dependencies,
    resolve_city,
    resolve_search_query,
    run_skillver_details_from_decisions,
    search_term_dir,
    CityAPIResponseError,
    CityResolutionError,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"Skillver 详情抓取 v{__version__}")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--query", default=None, help="搜索词，对应 data/<query>/")
    p.add_argument("--position-name", default=None, help="--query 的别名")
    p.add_argument("--catalog", default=DEFAULT_SKILLVER_CATALOG)
    p.add_argument("--seen", default=None)
    p.add_argument("--city", default=DEFAULT_CITY_INPUT)
    p.add_argument(
        "--details-from-decisions",
        required=True,
        nargs="+",
        help="一份或多份 classify_decisions_*.json；已映射帖全部开详情",
    )
    p.add_argument("--classify-input", nargs="*", default=None)
    p.add_argument("--jobs", default=None, help="jobs.json（含 job_link / security_id / lid）")
    p.add_argument("--detail-output", default=None)
    p.add_argument("--match-report", default=None)
    p.add_argument("--decision-report", default=None)
    p.add_argument(
        "--min-details",
        type=int,
        default=None,
        help="用户目标条数（只约束列表是否继续翻页；详情会开完全部已映射帖）",
    )
    p.add_argument("--unexported", default=None)
    p.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    p.add_argument("--close-chrome", action="store_true")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        query = resolve_search_query(args.query, args.position_name)
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(2)
    if not ensure_skill_env(reexec_if_needed=True):
        sys.exit(1)
    if not require_runtime_dependencies("requests", "websocket"):
        sys.exit(1)
    try:
        catalog = load_position_catalog(args.catalog)
    except (OSError, ValueError, ImportError) as exc:
        print(f"❌ 无法加载 catalog: {exc}")
        sys.exit(1)
    names = catalog_position_names(catalog)
    binding = {"position_name": query, "job_intent_id": "", "job_intent_label": ""}
    folder = search_term_dir(query)
    seen_path = args.seen or DEFAULT_SKILLVER_SEEN
    try:
        seen = load_skillver_seen(
            seen_path, catalog=catalog, catalog_names=set(names)
        )
    except (OSError, ValueError, ImportError) as exc:
        print(f"❌ 无法加载 seen: {exc}")
        sys.exit(1)
    _, default_detail = default_skillver_output_paths(query)
    detail_output = args.detail_output or default_detail
    jobs_path = args.jobs or os.path.join(folder, "jobs.json")
    if args.min_details is not None:
        print(
            "ℹ️  --min-details 只约束列表是否继续翻页；"
            "详情将开完全部已映射帖"
        )
    try:
        city_name, _ = resolve_city(args.city)
    except (CityResolutionError, CityAPIResponseError, OSError, ValueError) as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    if not ensure_scrape_login(args.cdp_port):
        sys.exit(1)
    classify_input = args.classify_input or None
    match_report = args.match_report or os.path.join(folder, "match_skip.json")
    decision_report = args.decision_report or os.path.join(folder, "decisions.json")
    try:
        run_skillver_details_from_decisions(
            position_binding=binding,
            catalog_names=names,
            skillver_seen=seen,
            skillver_seen_path=seen_path,
            classify_input_path=classify_input,
            decisions_path=args.details_from_decisions,
            detail_output=detail_output,
            cdp_port=args.cdp_port,
            fmt="json",
            match_report_path=match_report,
            decision_report_path=decision_report,
            city_fallback=city_name,
            jobs_path=jobs_path,
            catalog=catalog,
            query=query,
            unexported_path=args.unexported or DEFAULT_SKILLVER_UNEXPORTED,
        )
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    close_chrome_if_requested(args.close_chrome)


if __name__ == "__main__":
    main()
