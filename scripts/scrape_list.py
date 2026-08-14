#!/usr/bin/env python3
"""List scrape CLI: search pages → jobs.json + list_batch_N.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.boss_common import (
    DEFAULT_CDP_PORT,
    DEFAULT_CITY_INPUT,
    DEFAULT_SKILLVER_CATALOG,
    DEFAULT_SKILLVER_PAGE_BATCH_SIZE,
    DEFAULT_SKILLVER_SEEN,
    __version__,
    add_filter_arguments,
    catalog_position_names,
    close_chrome_if_requested,
    default_list_batch_path,
    default_skillver_output_paths,
    ensure_scrape_login,
    ensure_skill_env,
    filters_from_args,
    load_position_catalog,
    load_skillver_seen,
    require_runtime_dependencies,
    resolve_city,
    resolve_search_query,
    run_skillver_list_only_batch,
    CityResolutionError,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=f"Skillver 列表抓取 v{__version__}")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--query", default=None, help="搜索框关键词，任意文本")
    p.add_argument("--position-name", default=None, help="--query 的别名")
    p.add_argument("--catalog", default=DEFAULT_SKILLVER_CATALOG)
    p.add_argument("--seen", default=None)
    p.add_argument("--city", default=DEFAULT_CITY_INPUT)
    p.add_argument(
        "--pages",
        type=int,
        default=None,
        help="本调用最多抓到第几页；默认只抓 --list-start-page 起的 --page-batch-size 页，不设翻页上限",
    )
    p.add_argument("--page-batch-size", type=int, default=DEFAULT_SKILLVER_PAGE_BATCH_SIZE)
    p.add_argument("--list-start-page", type=int, default=1)
    p.add_argument("--batch-index", type=int, default=1)
    p.add_argument("--output", default=None, help="jobs.json")
    p.add_argument("--list-batch", default=None, help="本批 list_batch_N.json")
    p.add_argument("--cdp-port", type=int, default=DEFAULT_CDP_PORT)
    p.add_argument("--allow-dom-fallback", action="store_true")
    p.add_argument("--close-chrome", action="store_true")
    add_filter_arguments(p)
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
    seen_path = args.seen or DEFAULT_SKILLVER_SEEN
    try:
        seen = load_skillver_seen(
            seen_path, catalog=catalog, catalog_names=set(names)
        )
    except (OSError, ValueError, ImportError) as exc:
        print(f"❌ 无法加载 seen: {exc}")
        sys.exit(1)
    try:
        resolve_city(args.city)
    except CityResolutionError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    list_output = args.output or default_skillver_output_paths(query)[0]
    list_batch = args.list_batch or default_list_batch_path(query, args.batch_index)
    if not ensure_scrape_login(args.cdp_port):
        sys.exit(1)
    try:
        filters = filters_from_args(args)
    except ValueError as exc:
        print(f"❌ {exc}")
        sys.exit(1)
    run_skillver_list_only_batch(
        position_binding=binding,
        catalog_names=names,
        skillver_seen=seen,
        search_keyword=query,
        query=query,
        skillver_seen_path=seen_path,
        city=args.city,
        filters=filters,
        max_pages=args.pages,
        page_batch_size=args.page_batch_size,
        list_start_page=args.list_start_page,
        list_output=list_output,
        list_batch_path=list_batch,
        batch_index=args.batch_index,
        cdp_port=args.cdp_port,
        fmt="json",
        allow_dom_fallback=args.allow_dom_fallback,
    )
    close_chrome_if_requested(args.close_chrome)


if __name__ == "__main__":
    main()
