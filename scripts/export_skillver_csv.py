#!/usr/bin/env python3
"""Export BOSS detail JSON rows into Skillver CSV (job_YYYYMMDD.csv).

Main path: fixed catalog mapping + rule-parsed salary/city.
Uses data/seen_jobs.json (jobs keyed by encrypt_job_id) to skip
already-crawled / already-exported jobs. Unexported details live in
data/unexported_details.json until CSV write succeeds.
Does not call LLM.
Shared seen helpers are used by the scraper (P4–P6).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CSV_HEADERS = [
    "企业名称",
    "招聘品牌名",
    "所在城市",
    "一级编号",
    "一级岗位名称",
    "岗位名称",
    "岗位描述",
    "岗位base地",
    "岗位薪资",
]

DEFAULT_DATA_DIR = Path("data")
DEFAULT_CATALOG = DEFAULT_DATA_DIR / "position_catalog.json"
DEFAULT_SEEN_PATH = DEFAULT_DATA_DIR / "seen_jobs.json"
DEFAULT_UNEXPORTED_PATH = DEFAULT_DATA_DIR / "unexported_details.json"
_ILLEGAL_DIRNAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def search_term_dirname(term: str) -> str:
    cleaned = _ILLEGAL_DIRNAME_RE.sub("_", str(term or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "search"


def search_term_dir(term: str, *, data_dir: Path | None = None) -> Path:
    root = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    return root / search_term_dirname(term)


def default_seen_path(position_name: str | None = None) -> Path:
    del position_name
    return DEFAULT_SEEN_PATH


def default_unexported_path() -> Path:
    return DEFAULT_UNEXPORTED_PATH


def default_output_path(
    position_name: str | None = None, day: datetime | None = None
) -> Path:
    """Dated Skillver export path: data/<搜索词>/job_YYYYMMDD.csv."""
    stamp = (day or datetime.now()).strftime("%Y%m%d")
    folder = search_term_dir(position_name) if position_name else DEFAULT_DATA_DIR
    return folder / f"job_{stamp}.csv"


SALARY_OUT_RE = re.compile(r"^\d+K-\d+K$")
# Accept 40-70K / 40K-70K / 40-70K·20薪 / 2-3K (K may appear on either side).
_SALARY_RANGE_RE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[Kk千]?\s*[-~～—]\s*(?P<high>\d+(?:\.\d+)?)\s*[Kk千]"
)

MIN_JD_LEN = 10
# Skillver import is for full-time AI roles; reject internship-like dirty bands.
MIN_SALARY_LOW_K = 10
SEEN_VERSION = 3
UNEXPORTED_VERSION = 1

# Title / early-JD signals for obvious HR / sales mislabels (keep AI-in-HR-scene jobs).
_TITLE_MISLABEL_RE = re.compile(
    r"(?:\bHR\b|人力资源|招聘专员|招聘经理|猎头|招商销售|电话销售|销售代表|销售经理|销售顾问)",
    re.IGNORECASE,
)
_JD_MISLABEL_RE = re.compile(
    r"(人力资源\s*/\s*管理专业|招商销售|电话销售|销售专员|销售代表)",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    catalog_path = Path(path).expanduser()
    with catalog_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"catalog must be a JSON list: {catalog_path}")
    return data


def catalog_positions_by_name(
    catalog: list[dict[str, Any]] | None,
) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item in catalog or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("position_name") or "").strip()
        job_intent_id = str(item.get("job_intent_id") or "").strip()
        job_intent_label = str(item.get("job_intent_label") or "").strip()
        if name and job_intent_id and job_intent_label:
            out[name] = {
                "position_name": name,
                "job_intent_id": job_intent_id,
                "job_intent_label": job_intent_label,
            }
    return out


def catalog_name_set(catalog: list[dict[str, Any]] | None) -> set[str]:
    names: set[str] = set()
    for item in catalog or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("position_name") or "").strip()
        if name:
            names.add(name)
    return names


def resolve_position(
    catalog: list[dict[str, Any]], position_name: str
) -> dict[str, str]:
    name = str(position_name or "").strip()
    if not name:
        raise SystemExit("error: --position-name is required")
    for item in catalog:
        if str(item.get("position_name") or "").strip() == name:
            job_intent_id = str(item.get("job_intent_id") or "").strip()
            job_intent_label = str(item.get("job_intent_label") or "").strip()
            if not job_intent_id or not job_intent_label:
                raise SystemExit(
                    f"error: catalog entry for {name!r} missing "
                    "job_intent_id / job_intent_label"
                )
            return {
                "position_name": name,
                "job_intent_id": job_intent_id,
                "job_intent_label": job_intent_label,
            }
    raise SystemExit(f"error: unknown --position-name {name!r} (not in catalog)")


def load_details(paths: list[str | Path]) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for raw in paths:
        path = Path(raw).expanduser()
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            details.extend(item for item in payload if isinstance(item, dict))
            continue
        if isinstance(payload, dict):
            nested = payload.get("details")
            if isinstance(nested, list):
                details.extend(item for item in nested if isinstance(item, dict))
                continue
        raise ValueError(f"unsupported details JSON shape: {path}")
    return details


def empty_seen() -> dict[str, Any]:
    return {"version": SEEN_VERSION, "jobs": {}}


def _as_jobs(seen: dict[str, Any]) -> dict[str, Any]:
    jobs = seen.get("jobs")
    if not isinstance(jobs, dict):
        seen["jobs"] = {}
        return seen["jobs"]
    return jobs


def count_details_all(seen: dict[str, Any]) -> int:
    total = 0
    for entry in _as_jobs(seen).values():
        if isinstance(entry, dict) and entry.get("has_details"):
            total += 1
    return total


def is_classified(seen: dict[str, Any], key: str) -> bool:
    if not key:
        return False
    entry = _as_jobs(seen).get(key)
    if not isinstance(entry, dict):
        return False
    if str(entry.get("classified_at") or "").strip():
        return True
    return bool(str(entry.get("classified_by") or "").strip())


def job_in_seen(seen: dict[str, Any], key: str) -> bool:
    if not key:
        return False
    jobs = _as_jobs(seen)
    return isinstance(jobs.get(key), dict)


def load_seen(
    path: str | Path,
    *,
    catalog: list[dict[str, Any]] | None = None,
    catalog_names: set[str] | None = None,
) -> dict[str, Any]:
    del catalog, catalog_names
    seen_path = Path(path).expanduser()
    if not seen_path.is_file():
        return empty_seen()
    with seen_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"seen file must be a JSON object: {seen_path}")
    jobs = data.get("jobs")
    if jobs is None:
        jobs = {}
    if not isinstance(jobs, dict):
        raise ValueError(f"seen.jobs must be an object: {seen_path}")
    return {"version": SEEN_VERSION, "jobs": jobs}


def save_seen(path: str | Path, seen: dict[str, Any]) -> None:
    seen_path = Path(path).expanduser()
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    jobs = seen.get("jobs") if isinstance(seen.get("jobs"), dict) else {}
    payload = {
        "version": SEEN_VERSION,
        "jobs": jobs,
    }
    tmp_path = seen_path.with_suffix(seen_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(seen_path)


def empty_unexported() -> dict[str, Any]:
    return {"version": UNEXPORTED_VERSION, "jobs": {}}


def load_unexported(path: str | Path | None = None) -> dict[str, Any]:
    unexported_path = (
        Path(path).expanduser() if path else default_unexported_path()
    )
    if not unexported_path.is_file():
        return empty_unexported()
    with unexported_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"unexported file must be a JSON object: {unexported_path}")
    jobs = data.get("jobs")
    if jobs is None:
        jobs = {}
    if not isinstance(jobs, dict):
        raise ValueError(f"unexported.jobs must be an object: {unexported_path}")
    return {"version": UNEXPORTED_VERSION, "jobs": jobs}


def save_unexported(path: str | Path, store: dict[str, Any]) -> None:
    unexported_path = Path(path).expanduser()
    unexported_path.parent.mkdir(parents=True, exist_ok=True)
    jobs = store.get("jobs") if isinstance(store.get("jobs"), dict) else {}
    payload = {"version": UNEXPORTED_VERSION, "jobs": jobs}
    tmp_path = unexported_path.with_suffix(unexported_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(unexported_path)


def add_unexported(
    store: dict[str, Any],
    *,
    key: str,
    query: str = "",
    details_path: str = "",
    position_name: str = "",
) -> None:
    """Remember a scraped detail until CSV export succeeds."""
    if not key:
        return
    jobs = store.get("jobs")
    if not isinstance(jobs, dict):
        store["jobs"] = {}
        jobs = store["jobs"]
    existing = jobs.get(key) if isinstance(jobs.get(key), dict) else {}
    jobs[key] = {
        "encrypt_job_id": str(key),
        "query": str(query or existing.get("query") or "").strip(),
        "details_path": str(
            details_path or existing.get("details_path") or ""
        ).strip(),
        "position_name": str(
            position_name or existing.get("position_name") or ""
        ).strip(),
        "added_at": str(existing.get("added_at") or "").strip() or _utc_now_iso(),
    }
    store["version"] = UNEXPORTED_VERSION


def remove_unexported(store: dict[str, Any], keys: list[str] | tuple[str, ...]) -> None:
    jobs = store.get("jobs")
    if not isinstance(jobs, dict):
        return
    for key in keys:
        jobs.pop(str(key or "").strip(), None)


def details_from_unexported(
    store: dict[str, Any],
    *,
    query: str = "",
) -> list[dict[str, Any]]:
    """Load detail payloads for ids still waiting for CSV."""
    wanted = str(query or "").strip()
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for key, meta in (store.get("jobs") or {}).items():
        if not isinstance(meta, dict):
            continue
        if wanted and str(meta.get("query") or "").strip() != wanted:
            continue
        path = str(meta.get("details_path") or "").strip()
        if not path or not Path(path).expanduser().is_file():
            continue
        try:
            loaded = load_details([path])
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        for detail in loaded:
            detail_key = seen_key_for_detail(detail)
            if detail_key != str(key) or detail_key in seen_keys:
                continue
            seen_keys.add(detail_key)
            out.append(detail)
            break
    return out


def merge_detail_lists(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe details by encrypt_job_id, first occurrence wins."""
    out: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for group in groups:
        for detail in group or []:
            if not isinstance(detail, dict):
                continue
            key = seen_key_for_detail(detail)
            if key and key in seen_keys:
                continue
            if key:
                seen_keys.add(key)
            out.append(detail)
    return out


def seen_key_for_detail(detail: dict[str, Any]) -> str:
    """Primary key: encrypt_job_id; fall back to job_id if needed."""
    key = str(detail.get("encrypt_job_id") or "").strip()
    if key:
        return key
    return str(detail.get("job_id") or "").strip()


def is_exported(seen: dict[str, Any], key: str) -> bool:
    if not key:
        return False
    jobs = _as_jobs(seen)
    entry = jobs.get(key)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("exported"))


def has_details_in_seen(seen: dict[str, Any], key: str) -> bool:
    if not key:
        return False
    jobs = _as_jobs(seen)
    entry = jobs.get(key)
    if not isinstance(entry, dict):
        return False
    return bool(entry.get("has_details"))


def detail_ids_in_seen(seen: dict[str, Any]) -> set[str]:
    """Return encrypt_job_id keys that already have details scraped."""
    jobs = _as_jobs(seen)
    return {
        str(key)
        for key, entry in jobs.items()
        if key and isinstance(entry, dict) and entry.get("has_details")
    }


def upsert_seen_entry(
    seen: dict[str, Any],
    *,
    key: str,
    job_id: str = "",
    position_name: str = "",
    title: str = "",
    company: str = "",
    job_link: str = "",
    salary: str = "",
    location: str = "",
    classified_at: str | None = None,
    classified_by: str = "",
    has_details: bool | None = None,
    exported: bool | None = None,
    exported_at: str | None = None,
    details_at: str | None = None,
    catalog_names: set[str] | None = None,
    query: str = "",
) -> None:
    """Create/update one seen row. Id presence is the only index."""
    del catalog_names
    if not key:
        return
    jobs = _as_jobs(seen)
    now = _utc_now_iso()
    existing = jobs.get(key) if isinstance(jobs.get(key), dict) else {}
    first_seen = str(existing.get("first_seen_at") or "").strip() or now
    next_query = str(query or existing.get("query") or "").strip()
    next_pos = str(position_name or existing.get("position_name") or "").strip()
    next_exported = (
        bool(exported)
        if exported is not None
        else bool(existing.get("exported"))
    )
    next_has_details = (
        bool(has_details)
        if has_details is not None
        else bool(existing.get("has_details"))
    )
    next_exported_at = existing.get("exported_at")
    if exported is True:
        next_exported_at = exported_at or now
    elif exported is False and exported is not None:
        next_exported_at = None
    next_details_at = existing.get("details_at")
    if details_at is not None:
        next_details_at = details_at
    elif has_details is True and not next_details_at:
        next_details_at = now
    next_classified_at = (
        classified_at
        if classified_at is not None
        else existing.get("classified_at")
    )
    next_classified_by = str(
        classified_by or existing.get("classified_by") or ""
    ).strip()

    jobs[key] = {
        "encrypt_job_id": str(key),
        "job_id": str(job_id or existing.get("job_id") or "").strip(),
        "position_name": next_pos,
        "title": str(title or existing.get("title") or "").strip(),
        "company": str(company or existing.get("company") or "").strip(),
        "job_link": str(job_link or existing.get("job_link") or "").strip(),
        "salary": str(salary or existing.get("salary") or "").strip(),
        "location": str(location or existing.get("location") or "").strip(),
        "classified_at": next_classified_at,
        "classified_by": next_classified_by,
        "has_details": next_has_details,
        "exported": next_exported,
        "first_seen_at": first_seen,
        "details_at": next_details_at,
        "exported_at": next_exported_at,
        "query": next_query,
    }
    seen["version"] = SEEN_VERSION
    seen.pop("by_position", None)


def mark_listed(
    seen: dict[str, Any],
    *,
    key: str,
    job: dict[str, Any] | None = None,
    query: str = "",
    catalog_names: set[str] | None = None,
) -> None:
    """Remember a list card so later searches skip it. Not classified yet."""
    job = job or {}
    upsert_seen_entry(
        seen,
        key=key,
        job_id=str(job.get("job_id") or "").strip(),
        position_name="",
        title=str(job.get("title") or "").strip(),
        company=str(
            job.get("boss_name") or job.get("company") or ""
        ).strip(),
        job_link=str(job.get("job_link") or job.get("link") or "").strip(),
        salary=str(job.get("salary") or "").strip(),
        location=str(job.get("location") or "").strip(),
        query=query,
        catalog_names=catalog_names,
    )


def mark_classified(
    seen: dict[str, Any],
    *,
    key: str,
    job: dict[str, Any] | None = None,
    position_name: str,
    classified_by: str,
    catalog_names: set[str] | None = None,
    query: str = "",
) -> None:
    """Remember classification so the same id is not asked again."""
    job = job or {}
    upsert_seen_entry(
        seen,
        key=key,
        job_id=str(job.get("job_id") or "").strip(),
        position_name=position_name,
        title=str(job.get("title") or "").strip(),
        company=str(
            job.get("boss_name") or job.get("company") or ""
        ).strip(),
        job_link=str(job.get("job_link") or job.get("link") or "").strip(),
        salary=str(job.get("salary") or "").strip(),
        location=str(job.get("location") or "").strip(),
        classified_at=_utc_now_iso(),
        classified_by=classified_by,
        has_details=False,
        exported=False,
        catalog_names=catalog_names,
        query=query,
    )


def mark_exported(
    seen: dict[str, Any],
    *,
    key: str,
    job_id: str,
    position_name: str,
    exported_at: str | None = None,
    catalog_names: set[str] | None = None,
) -> None:
    upsert_seen_entry(
        seen,
        key=key,
        job_id=job_id,
        position_name=position_name,
        has_details=True,
        exported=True,
        exported_at=exported_at,
        catalog_names=catalog_names,
    )


def mark_scraped(
    seen: dict[str, Any],
    *,
    key: str,
    job_id: str,
    position_name: str,
    catalog_names: set[str] | None = None,
    details_at: str | None = None,
) -> None:
    """Scraper-side: details saved so the same id is not opened again."""
    jobs = _as_jobs(seen)
    existing = jobs.get(key) if isinstance(jobs.get(key), dict) else {}
    already_exported = bool(existing.get("exported"))
    upsert_seen_entry(
        seen,
        key=key,
        job_id=job_id,
        position_name=position_name,
        has_details=True,
        exported=already_exported,
        exported_at=existing.get("exported_at") if already_exported else None,
        details_at=details_at or _utc_now_iso(),
        catalog_names=catalog_names,
    )


def city_from_location(location: str, city_fallback: str = "") -> str:
    parts = [p.strip() for p in str(location or "").split("·") if p.strip()]
    if parts:
        return parts[0]
    return str(city_fallback or "").strip()


def normalize_jd(jd: str) -> str:
    """Collapse whitespace and make JD Skillver-safe (no ASCII commas / quotes).

    Skillver's importer splits on commas then re-joins; RFC4180 quotes around
    comma-containing JDs are left as literal characters. Replace ASCII commas
    with full-width ones and strip quotes so the CSV writer need not quote JD.
    """
    text = str(jd or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip('`"\'“”‘’')
    text = text.replace(",", "，")
    text = text.replace('"', "").replace("'", "")
    return text.strip()


def sanitize_csv_field(value: str) -> str:
    """Strip characters that force quoting or break Skillver's comma split."""
    text = str(value or "").replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(",", "，")
    text = text.replace('"', "").replace("'", "")
    return text


def parse_salary_skillver(salary: str) -> str | None:
    """Normalize BOSS salary to Skillver `^\\d+K-\\d+K$`, or None to skip."""
    text = str(salary or "").strip()
    if not text or "面议" in text:
        return None
    match = _SALARY_RANGE_RE.search(text)
    if not match:
        return None
    try:
        low = float(match.group("low"))
        high = float(match.group("high"))
    except ValueError:
        return None
    if high < low:
        return None
    low_i = int(round(low))
    high_i = int(round(high))
    if low_i <= 0 or high_i <= 0:
        return None
    out = f"{low_i}K-{high_i}K"
    if not SALARY_OUT_RE.fullmatch(out):
        return None
    return out


def salary_low_k(salary: str) -> int | None:
    text = str(salary or "").strip()
    if not SALARY_OUT_RE.fullmatch(text):
        return None
    try:
        return int(text.split("K-", 1)[0])
    except ValueError:
        return None


def is_obvious_mislabeled(*, title: str = "", jd: str = "") -> bool:
    """Heuristic reject for clear HR / sales postings wrongly mapped to AI roles."""
    title_text = str(title or "").strip()
    if title_text and _TITLE_MISLABEL_RE.search(title_text):
        return True
    head = str(jd or "")[:160]
    if _JD_MISLABEL_RE.search(head):
        return True
    # Pure HR consulting / sales-company intros without AI eng signals.
    if "人力资源" in head and not any(
        token in head for token in ("算法", "大模型", "LLM", "AIGC", "Agent")
    ):
        return True
    if re.search(r"AI\s*SAAS\s*销售|销售公司", head, re.IGNORECASE) and not any(
        token in head for token in ("算法", "大模型", "LLM", "Agent工程师")
    ):
        return True
    return False


def detail_to_row(
    detail: dict[str, Any],
    position: dict[str, str],
    *,
    city_fallback: str = "",
    min_salary_low_k: int = MIN_SALARY_LOW_K,
) -> tuple[dict[str, str] | None, str | None]:
    """Map one detail dict to CSV row fields, or (None, skip_reason)."""
    company = sanitize_csv_field(str(detail.get("company") or "").strip())
    if not company:
        return None, "empty_company"

    city = sanitize_csv_field(
        city_from_location(str(detail.get("location") or ""), city_fallback)
    )
    if not city:
        return None, "empty_city"

    jd = normalize_jd(str(detail.get("jd") or ""))
    if len(jd) < MIN_JD_LEN:
        return None, "jd_too_short"

    if is_obvious_mislabeled(
        title=str(detail.get("title") or ""),
        jd=jd,
    ):
        return None, "mislabeled_hr_sales"

    salary = parse_salary_skillver(str(detail.get("salary") or ""))
    if salary is None:
        return None, "salary_unparsed"

    low = salary_low_k(salary)
    if low is not None and low < int(min_salary_low_k):
        return None, "salary_too_low"

    row = {
        "企业名称": company,
        "招聘品牌名": company,
        "所在城市": city,
        "一级编号": sanitize_csv_field(position["job_intent_id"]),
        "一级岗位名称": sanitize_csv_field(position["job_intent_label"]),
        "岗位名称": sanitize_csv_field(position["position_name"]),
        "岗位描述": jd,
        "岗位base地": city,
        "岗位薪资": salary,
    }
    return row, None


def csv_row_from_dict(
    row: dict[str, str],
    *,
    min_salary_low_k: int = MIN_SALARY_LOW_K,
) -> tuple[dict[str, str] | None, str | None]:
    """Re-validate / sanitize an already-exported Skillver CSV row."""
    brand = sanitize_csv_field(
        row.get("招聘品牌名") or row.get("企业名称") or ""
    )
    company = sanitize_csv_field(row.get("企业名称") or "") or brand
    if not company:
        return None, "empty_company"
    city = sanitize_csv_field(row.get("所在城市") or "")
    base = sanitize_csv_field(row.get("岗位base地") or "") or city
    if not city:
        return None, "empty_city"
    jd = normalize_jd(row.get("岗位描述") or "")
    if len(jd) < MIN_JD_LEN:
        return None, "jd_too_short"
    if is_obvious_mislabeled(jd=jd):
        return None, "mislabeled_hr_sales"
    salary = parse_salary_skillver(row.get("岗位薪资") or "")
    if salary is None:
        return None, "salary_unparsed"
    low = salary_low_k(salary)
    if low is not None and low < int(min_salary_low_k):
        return None, "salary_too_low"
    intent_id = sanitize_csv_field(row.get("一级编号") or "")
    intent_label = sanitize_csv_field(row.get("一级岗位名称") or "")
    position_name = sanitize_csv_field(row.get("岗位名称") or "")
    if not intent_id or not intent_label or not position_name:
        return None, "missing_position_fields"
    return {
        "企业名称": company,
        "招聘品牌名": brand or company,
        "所在城市": city,
        "一级编号": intent_id,
        "一级岗位名称": intent_label,
        "岗位名称": position_name,
        "岗位描述": jd,
        "岗位base地": base,
        "岗位薪资": salary,
    }, None


def cleanup_csv_rows(
    rows: list[dict[str, str]],
    *,
    min_salary_low_k: int = MIN_SALARY_LOW_K,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], int]:
    """Sanitize and quality-filter CSV rows. Returns (kept, skipped, dupes=0)."""
    kept: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        cleaned, reason = csv_row_from_dict(row, min_salary_low_k=min_salary_low_k)
        if cleaned is None:
            skipped.append(
                {
                    "index": index,
                    "reason": reason,
                    "company": row.get("企业名称") or "",
                    "position_name": row.get("岗位名称") or "",
                    "salary": row.get("岗位薪资") or "",
                }
            )
            continue
        kept.append(cleaned)
    return kept, skipped, 0


def export_details(
    details: list[dict[str, Any]],
    position: dict[str, str] | None = None,
    *,
    catalog: list[dict[str, Any]] | None = None,
    city_fallback: str = "",
    seen: dict[str, Any] | None = None,
    catalog_names: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    """Return (rows, skipped, export_marks).

    export_marks entries: {key, job_id, position_name} for rows that will
    be marked exported after a successful CSV write.
    Each row uses that detail's mapped catalog position.
    """
    del catalog_names
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    seen_state = seen if isinstance(seen, dict) else empty_seen()
    positions = catalog_positions_by_name(catalog)
    if position and position.get("position_name"):
        positions.setdefault(str(position["position_name"]), position)
    fallback_name = str((position or {}).get("position_name") or "").strip()
    work_details = [d for d in details if isinstance(d, dict)]

    for index, detail in enumerate(work_details):
        key = seen_key_for_detail(detail)
        if key and is_exported(seen_state, key):
            skipped.append(
                {
                    "index": index,
                    "reason": "already_exported",
                    "job_id": detail.get("job_id") or "",
                    "encrypt_job_id": detail.get("encrypt_job_id") or "",
                    "title": detail.get("title") or "",
                    "company": detail.get("company") or "",
                    "salary": detail.get("salary") or "",
                }
            )
            continue

        seen_pos = ""
        if key:
            entry = _as_jobs(seen_state).get(key)
            if isinstance(entry, dict):
                seen_pos = str(entry.get("position_name") or "").strip()
        pos_name = str(detail.get("position_name") or seen_pos or fallback_name).strip()
        row_position = positions.get(pos_name)
        if row_position is None:
            skipped.append(
                {
                    "index": index,
                    "reason": "unknown_position",
                    "job_id": detail.get("job_id") or detail.get("encrypt_job_id") or "",
                    "encrypt_job_id": detail.get("encrypt_job_id") or "",
                    "title": detail.get("title") or "",
                    "company": detail.get("company") or "",
                    "salary": detail.get("salary") or "",
                }
            )
            continue

        row, reason = detail_to_row(detail, row_position, city_fallback=city_fallback)
        if row is None:
            skipped.append(
                {
                    "index": index,
                    "reason": reason,
                    "job_id": detail.get("job_id") or detail.get("encrypt_job_id") or "",
                    "encrypt_job_id": detail.get("encrypt_job_id") or "",
                    "title": detail.get("title") or "",
                    "company": detail.get("company") or "",
                    "salary": detail.get("salary") or "",
                }
            )
            continue
        rows.append(row)
        if key:
            pending.append(
                {
                    "key": key,
                    "job_id": str(detail.get("job_id") or "").strip(),
                    "position_name": row_position["position_name"],
                }
            )
    return rows, skipped, pending


def apply_exported_marks(
    seen: dict[str, Any],
    pending: list[dict[str, str]],
    *,
    catalog_names: set[str] | None = None,
) -> None:
    now = _utc_now_iso()
    for item in pending:
        mark_exported(
            seen,
            key=item.get("key") or "",
            job_id=item.get("job_id") or "",
            position_name=item.get("position_name") or "",
            exported_at=now,
            catalog_names=catalog_names,
        )


def write_csv(
    path: str | Path,
    rows: list[dict[str, str]],
    *,
    append: bool = False,
) -> None:
    """Write Skillver CSV. Fields are pre-sanitized so JD need not be quoted."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    write_header = True
    mode = "w"
    if append and out.is_file() and out.stat().st_size > 0:
        mode = "a"
        write_header = False
    safe_rows: list[dict[str, str]] = []
    for row in rows:
        safe = {key: sanitize_csv_field(row.get(key) or "") for key in CSV_HEADERS}
        # JD already normalized; re-apply to keep commas/quotes out.
        safe["岗位描述"] = normalize_jd(row.get("岗位描述") or "")
        safe_rows.append(safe)
    with out.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_HEADERS,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        if write_header:
            writer.writeheader()
        for row in safe_rows:
            writer.writerow(row)


def write_report(path: str | Path, payload: dict[str, Any]) -> None:
    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export BOSS detail JSON to Skillver job_YYYYMMDD.csv "
            "(fixed catalog mapping; skips seen.exported==true)"
        )
    )
    parser.add_argument(
        "--details",
        nargs="+",
        required=True,
        help="One or more detail JSON files (list of job objects)",
    )
    parser.add_argument(
        "--query",
        default="",
        help="Search term used for default output folder (data/<query>/)",
    )
    parser.add_argument(
        "--position-name",
        default="",
        help="Optional catalog fallback / output-folder alias; no longer required",
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help=f"Catalog JSON (default: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV path (default: data/<搜索词>/job_YYYYMMDD.csv)",
    )
    parser.add_argument(
        "--seen",
        default="",
        help="seen_jobs.json path (default: data/seen_jobs.json)",
    )
    parser.add_argument(
        "--unexported",
        default="",
        help="unexported_details.json path (default: data/unexported_details.json)",
    )
    parser.add_argument(
        "--city",
        default="",
        help="Fallback city / base when location is empty",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append rows to existing CSV (skip header if file non-empty)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write CSV or update seen; print counts only",
    )
    parser.add_argument(
        "--report",
        default="",
        help="Optional JSON report path (written rows + skipped reasons)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    query = str(args.query or "").strip() or str(args.position_name or "").strip()
    output_path = (
        Path(args.output).expanduser()
        if str(args.output or "").strip()
        else default_output_path(query or None)
    )
    seen_path = (
        Path(args.seen).expanduser()
        if str(args.seen or "").strip()
        else default_seen_path()
    )
    unexported_path = (
        Path(args.unexported).expanduser()
        if str(args.unexported or "").strip()
        else default_unexported_path()
    )
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load catalog: {exc}") from exc

    position = None
    requested = str(args.position_name or "").strip()
    if requested:
        try:
            position = resolve_position(catalog, requested)
        except SystemExit:
            position = None

    try:
        details = load_details(args.details)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load details: {exc}") from exc

    catalog_names = catalog_name_set(catalog)
    try:
        seen = load_seen(seen_path, catalog_names=catalog_names)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load seen: {exc}") from exc
    try:
        unexported = load_unexported(unexported_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load unexported: {exc}") from exc
    leftover = details_from_unexported(unexported, query=query)
    if leftover:
        details = merge_detail_lists(details, leftover)

    rows, skipped, pending = export_details(
        details,
        position,
        catalog=catalog,
        city_fallback=args.city,
        seen=seen,
        catalog_names=catalog_names,
    )

    print(
        "query=%s details=%s exported=%s skipped=%s"
        % (
            query or "-",
            len(details),
            len(rows),
            len(skipped),
        )
    )

    report_payload = {
        "query": query,
        "position": position,
        "details_count": len(details),
        "exported_count": len(rows),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "seen": str(seen_path),
        "output": None if args.dry_run else str(output_path),
        "dry_run": bool(args.dry_run),
    }

    if args.report:
        try:
            write_report(args.report, report_payload)
        except OSError as exc:
            raise SystemExit(f"error: failed to write report: {exc}") from exc
        print("report=%s" % Path(args.report).expanduser())

    if args.dry_run:
        return

    try:
        write_csv(output_path, rows, append=bool(args.append))
    except OSError as exc:
        raise SystemExit(f"error: failed to write csv: {exc}") from exc
    print("output=%s" % output_path)

    if pending:
        apply_exported_marks(seen, pending, catalog_names=catalog_names)
        remove_unexported(unexported, [item["key"] for item in pending])
        try:
            save_seen(seen_path, seen)
        except OSError as exc:
            raise SystemExit(f"error: failed to write seen: {exc}") from exc
        try:
            save_unexported(unexported_path, unexported)
        except OSError as exc:
            raise SystemExit(f"error: failed to write unexported: {exc}") from exc
        print("seen=%s marked=%s" % (seen_path, len(pending)))
        print("unexported=%s remaining=%s" % (unexported_path, len(unexported.get("jobs") or {})))


if __name__ == "__main__":
    main()
