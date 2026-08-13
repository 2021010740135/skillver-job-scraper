#!/usr/bin/env python3
"""Export BOSS detail JSON rows into Skillver CSV (job_YYYYMMDD.csv).

Main path: fixed catalog mapping + rule-parsed salary/city.
Uses data/skillver/seen_jobs.json (version 2: jobs + by_position indexes)
to select pending_export and skip already-exported jobs.
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
    "招聘品牌名",
    "所在城市",
    "一级编号",
    "一级岗位名称",
    "岗位名称",
    "岗位描述",
    "岗位base地",
    "岗位薪资",
]

DEFAULT_CATALOG = Path("data") / "skillver" / "position_catalog.json"
DEFAULT_EXPORTS_DIR = Path("data") / "skillver" / "exports"
DEFAULT_SEEN = Path("data") / "skillver" / "seen_jobs.json"


def default_output_path(day: datetime | None = None) -> Path:
    """Dated Skillver export path: data/skillver/exports/job_YYYYMMDD.csv."""
    stamp = (day or datetime.now()).strftime("%Y%m%d")
    return DEFAULT_EXPORTS_DIR / f"job_{stamp}.csv"

SALARY_OUT_RE = re.compile(r"^\d+K-\d+K$")
# Accept 40-70K / 40K-70K / 40-70K·20薪 / 2-3K (K may appear on either side).
_SALARY_RANGE_RE = re.compile(
    r"(?P<low>\d+(?:\.\d+)?)\s*[Kk千]?\s*[-~～—]\s*(?P<high>\d+(?:\.\d+)?)\s*[Kk千]"
)

MIN_JD_LEN = 10
# Skillver import is for full-time AI roles; reject internship-like dirty bands.
MIN_SALARY_LOW_K = 10
SEEN_VERSION = 2

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
    return {"version": SEEN_VERSION, "jobs": {}, "by_position": {}}


def empty_position_queues() -> dict[str, list[str]]:
    return {"pending_details": [], "pending_export": []}


def _as_jobs(seen: dict[str, Any]) -> dict[str, Any]:
    jobs = seen.get("jobs")
    if not isinstance(jobs, dict):
        seen["jobs"] = {}
        return seen["jobs"]
    return jobs


def _as_by_position(seen: dict[str, Any]) -> dict[str, Any]:
    by_pos = seen.get("by_position")
    if not isinstance(by_pos, dict):
        seen["by_position"] = {}
        return seen["by_position"]
    return by_pos


def is_catalog_position(position_name: str, catalog_names: set[str] | None) -> bool:
    name = str(position_name or "").strip()
    if not name:
        return False
    if catalog_names is None:
        return True
    return name in catalog_names


def ensure_position_index(
    seen: dict[str, Any],
    position_name: str,
    *,
    catalog_names: set[str] | None = None,
) -> dict[str, list[str]] | None:
    """Ensure by_position[X] queues exist; only for catalog-legal names."""
    name = str(position_name or "").strip()
    if not is_catalog_position(name, catalog_names):
        return None
    by_pos = _as_by_position(seen)
    bucket = by_pos.get(name)
    if not isinstance(bucket, dict):
        bucket = empty_position_queues()
        by_pos[name] = bucket
    else:
        if not isinstance(bucket.get("pending_details"), list):
            bucket["pending_details"] = []
        if not isinstance(bucket.get("pending_export"), list):
            bucket["pending_export"] = []
    return bucket


def _queue_append(queue: list[str], key: str) -> bool:
    """Append key if absent; return True when newly added."""
    if not key or key in queue:
        return False
    queue.append(key)
    return True


def _queue_remove(queue: list[str], key: str) -> bool:
    if not key or key not in queue:
        return False
    while key in queue:
        queue.remove(key)
    return True


def pending_details_for(seen: dict[str, Any], position_name: str) -> list[str]:
    name = str(position_name or "").strip()
    by_pos = _as_by_position(seen)
    bucket = by_pos.get(name)
    if not isinstance(bucket, dict):
        return []
    queue = bucket.get("pending_details")
    if not isinstance(queue, list):
        return []
    return [str(x) for x in queue if x]


def pending_export_for(seen: dict[str, Any], position_name: str) -> list[str]:
    name = str(position_name or "").strip()
    by_pos = _as_by_position(seen)
    bucket = by_pos.get(name)
    if not isinstance(bucket, dict):
        return []
    queue = bucket.get("pending_export")
    if not isinstance(queue, list):
        return []
    return [str(x) for x in queue if x]


def job_in_seen(seen: dict[str, Any], key: str) -> bool:
    if not key:
        return False
    jobs = _as_jobs(seen)
    return isinstance(jobs.get(key), dict)


def rebuild_by_position(
    seen: dict[str, Any],
    *,
    catalog_names: set[str] | None = None,
) -> None:
    """Rebuild pending indexes from jobs (source of truth). No done queues."""
    by_pos: dict[str, dict[str, list[str]]] = {}
    jobs = _as_jobs(seen)
    for key, entry in jobs.items():
        if not key or not isinstance(entry, dict):
            continue
        pos = str(entry.get("position_name") or "").strip()
        if not is_catalog_position(pos, catalog_names):
            continue
        bucket = by_pos.setdefault(pos, empty_position_queues())
        if entry.get("exported"):
            continue
        if entry.get("has_details"):
            _queue_append(bucket["pending_export"], str(key))
        else:
            _queue_append(bucket["pending_details"], str(key))
    seen["by_position"] = by_pos
    seen["version"] = SEEN_VERSION


def migrate_seen_to_v2(
    seen: dict[str, Any],
    *,
    catalog_names: set[str] | None = None,
) -> dict[str, Any]:
    """Normalize any loaded seen payload to version 2 with indexes."""
    if not isinstance(seen, dict):
        return empty_seen()
    jobs = seen.get("jobs")
    if not isinstance(jobs, dict):
        jobs = {}
    normalized = {"version": SEEN_VERSION, "jobs": jobs, "by_position": {}}
    # Preserve richer fields already present; rebuild queues from jobs.
    rebuild_by_position(normalized, catalog_names=catalog_names)
    return normalized


def load_seen(
    path: str | Path,
    *,
    catalog: list[dict[str, Any]] | None = None,
    catalog_names: set[str] | None = None,
) -> dict[str, Any]:
    seen_path = Path(path).expanduser()
    names = catalog_names if catalog_names is not None else catalog_name_set(catalog)
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
    version = int(data.get("version") or 1)
    seen = {
        "version": version,
        "jobs": jobs,
        "by_position": data.get("by_position")
        if isinstance(data.get("by_position"), dict)
        else {},
    }
    if version < SEEN_VERSION or not seen.get("by_position"):
        seen = migrate_seen_to_v2(seen, catalog_names=names or None)
    else:
        # Keep queues but ensure shape; do not invent done.
        rebuild_by_position(seen, catalog_names=names or None)
    return seen


def save_seen(path: str | Path, seen: dict[str, Any]) -> None:
    seen_path = Path(path).expanduser()
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    jobs = seen.get("jobs") if isinstance(seen.get("jobs"), dict) else {}
    by_pos = seen.get("by_position") if isinstance(seen.get("by_position"), dict) else {}
    payload = {
        "version": SEEN_VERSION,
        "jobs": jobs,
        "by_position": by_pos,
    }
    tmp_path = seen_path.with_suffix(seen_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(seen_path)


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


def count_details_for_position(seen: dict[str, Any], position_name: str) -> int:
    name = str(position_name or "").strip()
    jobs = _as_jobs(seen)
    total = 0
    for entry in jobs.values():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("position_name") or "").strip() != name:
            continue
        if entry.get("has_details"):
            total += 1
    return total


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
    enqueue_pending: bool = True,
) -> None:
    """Create/update one seen row and keep by_position queues consistent."""
    if not key:
        return
    jobs = _as_jobs(seen)
    now = _utc_now_iso()
    existing = jobs.get(key) if isinstance(jobs.get(key), dict) else {}
    first_seen = str(existing.get("first_seen_at") or "").strip() or now
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
    }
    seen["version"] = SEEN_VERSION

    # Drop from all queues first, then re-queue by state.
    by_pos = _as_by_position(seen)
    for bucket in by_pos.values():
        if not isinstance(bucket, dict):
            continue
        for qname in ("pending_details", "pending_export"):
            queue = bucket.get(qname)
            if isinstance(queue, list):
                _queue_remove(queue, key)

    if not enqueue_pending or not is_catalog_position(next_pos, catalog_names):
        return
    bucket = ensure_position_index(
        seen, next_pos, catalog_names=catalog_names
    )
    if bucket is None:
        return
    if next_exported:
        return
    if next_has_details:
        _queue_append(bucket["pending_export"], key)
    else:
        _queue_append(bucket["pending_details"], key)


def mark_classified(
    seen: dict[str, Any],
    *,
    key: str,
    job: dict[str, Any] | None = None,
    position_name: str,
    classified_by: str,
    catalog_names: set[str] | None = None,
) -> None:
    """Inventory a newly classified job into jobs + pending_details."""
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
        enqueue_pending=True,
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
        enqueue_pending=True,
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
    """Scraper-side: details saved → leave pending_details, enter pending_export."""
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
        enqueue_pending=True,
    )


def check_seen_index_consistency(
    seen: dict[str, Any],
    *,
    catalog_names: set[str] | None = None,
) -> list[str]:
    """Return human-readable consistency errors (empty if healthy)."""
    errors: list[str] = []
    jobs = _as_jobs(seen)
    by_pos = _as_by_position(seen)
    expected: dict[str, dict[str, list[str]]] = {}
    for key, entry in jobs.items():
        if not isinstance(entry, dict):
            errors.append(f"jobs[{key!r}] is not an object")
            continue
        pos = str(entry.get("position_name") or "").strip()
        if not is_catalog_position(pos, catalog_names):
            continue
        bucket = expected.setdefault(pos, empty_position_queues())
        if entry.get("exported"):
            continue
        if entry.get("has_details"):
            _queue_append(bucket["pending_export"], str(key))
        else:
            _queue_append(bucket["pending_details"], str(key))

    for pos, bucket in by_pos.items():
        if catalog_names is not None and pos not in catalog_names:
            errors.append(f"by_position has non-catalog position {pos!r}")
            continue
        if not isinstance(bucket, dict):
            errors.append(f"by_position[{pos!r}] is not an object")
            continue
        for qname in ("pending_details", "pending_export"):
            queue = bucket.get(qname) or []
            if not isinstance(queue, list):
                errors.append(f"by_position[{pos!r}].{qname} is not a list")
                continue
            if len(queue) != len(set(queue)):
                errors.append(f"by_position[{pos!r}].{qname} has duplicates")
            exp = (expected.get(pos) or empty_position_queues()).get(qname) or []
            if list(queue) != list(exp):
                errors.append(
                    f"by_position[{pos!r}].{qname} mismatch "
                    f"(index={list(queue)} expected={list(exp)})"
                )
    for pos, bucket in expected.items():
        if pos not in by_pos:
            if bucket["pending_details"] or bucket["pending_export"]:
                errors.append(f"missing by_position[{pos!r}] for pending jobs")
    return errors


# 城市前缀表：从无分隔符 location（如「上海青浦区…」）提取城市名。
DEFAULT_CITY_CODES = Path("data") / "city_codes.json"


def _load_city_names() -> tuple[str, ...]:
    try:
        with DEFAULT_CITY_CODES.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(data, dict):
        return ()
    return tuple(sorted((str(k or "").strip() for k in data if k), key=len, reverse=True))


_CITY_NAMES = _load_city_names()


def _match_city_prefix(loc: str) -> str:
    """Longest city name that prefixes loc (e.g. 上海青浦区… → 上海)."""
    for name in _CITY_NAMES:
        if loc.startswith(name):
            return name
    return ""


def city_from_location(location: str, city_fallback: str = "") -> str:
    loc = str(location or "").strip()
    if loc:
        hit = _match_city_prefix(loc)
        if hit:
            return hit
    if "·" in loc:
        parts = [p.strip() for p in loc.split("·") if p.strip()]
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


def row_dedupe_key(row: dict[str, str]) -> tuple[str, str]:
    """Dedupe by brand + position."""
    brand = sanitize_csv_field(row.get("招聘品牌名") or "")
    position = sanitize_csv_field(row.get("岗位名称") or "")
    return (brand, position)


def prefer_row(existing: dict[str, str], candidate: dict[str, str]) -> dict[str, str]:
    """Prefer longer JD, then higher salary low-end, when company+position collide."""
    jd_a = existing.get("岗位描述") or ""
    jd_b = candidate.get("岗位描述") or ""
    if len(jd_b) != len(jd_a):
        return candidate if len(jd_b) > len(jd_a) else existing
    low_a = salary_low_k(existing.get("岗位薪资") or "") or 0
    low_b = salary_low_k(candidate.get("岗位薪资") or "") or 0
    return candidate if low_b > low_a else existing


def dedupe_rows_by_company_position(
    rows: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int]:
    """Keep one row per (招聘品牌名, 岗位名称). Returns (rows, dropped_count)."""
    chosen: dict[tuple[str, str], dict[str, str]] = {}
    order: list[tuple[str, str]] = []
    dropped = 0
    for row in rows:
        key = row_dedupe_key(row)
        if key not in chosen:
            chosen[key] = row
            order.append(key)
            continue
        dropped += 1
        chosen[key] = prefer_row(chosen[key], row)
    return [chosen[key] for key in order], dropped


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
        "招聘品牌名": company,
        "所在城市": city,
        "一级编号": sanitize_csv_field(position["job_intent_id"]),
        "一级岗位名称": sanitize_csv_field(position["job_intent_label"]),
        "岗位名称": sanitize_csv_field(position["position_name"]),
        "岗位描述": jd,
        "岗位base地": sanitize_csv_field(str(detail.get("location") or "").strip()) or city,
        "岗位薪资": salary,
    }
    return row, None


def csv_row_from_dict(
    row: dict[str, str],
    *,
    min_salary_low_k: int = MIN_SALARY_LOW_K,
) -> tuple[dict[str, str] | None, str | None]:
    """Re-validate / sanitize an already-exported Skillver CSV row."""
    brand = sanitize_csv_field(row.get("招聘品牌名") or "")
    if not brand:
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
        "招聘品牌名": brand,
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
    """Sanitize, quality-filter, and dedupe CSV rows. Returns (kept, skipped, dupes)."""
    kept: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        cleaned, reason = csv_row_from_dict(row, min_salary_low_k=min_salary_low_k)
        if cleaned is None:
            skipped.append(
                {
                    "index": index,
                    "reason": reason,
                    "company": row.get("招聘品牌名") or "",
                    "position_name": row.get("岗位名称") or "",
                    "salary": row.get("岗位薪资") or "",
                }
            )
            continue
        kept.append(cleaned)
    deduped, dupes = dedupe_rows_by_company_position(kept)
    return deduped, skipped, dupes


def select_details_for_export(
    details: list[dict[str, Any]],
    seen: dict[str, Any],
    position_name: str,
) -> list[dict[str, Any]]:
    """Prefer pending_export order; fall back to all non-exported details."""
    pending_ids = pending_export_for(seen, position_name)
    by_key: dict[str, dict[str, Any]] = {}
    for detail in details:
        if not isinstance(detail, dict):
            continue
        key = seen_key_for_detail(detail)
        if key and key not in by_key:
            by_key[key] = detail
    if pending_ids:
        selected = [by_key[key] for key in pending_ids if key in by_key]
        return selected
    return [d for d in details if isinstance(d, dict)]


def export_details(
    details: list[dict[str, Any]],
    position: dict[str, str],
    *,
    city_fallback: str = "",
    seen: dict[str, Any] | None = None,
    catalog_names: set[str] | None = None,
    use_pending_export: bool = True,
) -> tuple[list[dict[str, str]], list[dict[str, Any]], list[dict[str, str]]]:
    """Return (rows, skipped, pending_seen_marks).

    pending_seen_marks entries: {key, job_id, position_name} for rows that will
    be marked exported after a successful CSV write.
    """
    rows: list[dict[str, str]] = []
    skipped: list[dict[str, Any]] = []
    pending: list[dict[str, str]] = []
    content_keys: set[tuple[str, str]] = set()
    seen_state = seen if isinstance(seen, dict) else empty_seen()
    work_details = (
        select_details_for_export(
            details, seen_state, position["position_name"]
        )
        if use_pending_export
        else [d for d in details if isinstance(d, dict)]
    )

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

        row, reason = detail_to_row(detail, position, city_fallback=city_fallback)
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
        content_key = row_dedupe_key(row)
        if content_key in content_keys:
            skipped.append(
                {
                    "index": index,
                    "reason": "duplicate_company_position",
                    "job_id": detail.get("job_id") or "",
                    "encrypt_job_id": detail.get("encrypt_job_id") or "",
                    "title": detail.get("title") or "",
                    "company": detail.get("company") or "",
                    "salary": detail.get("salary") or "",
                }
            )
            continue
        content_keys.add(content_key)
        rows.append(row)
        if key:
            pending.append(
                {
                    "key": key,
                    "job_id": str(detail.get("job_id") or "").strip(),
                    "position_name": position["position_name"],
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
    default_out = default_output_path()
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
        "--position-name",
        required=True,
        help="Standard position_name; must exist in catalog",
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help=f"Catalog JSON (default: {DEFAULT_CATALOG})",
    )
    parser.add_argument(
        "--output",
        default="",
        help=f"Output CSV path (default: {default_out})",
    )
    parser.add_argument(
        "--seen",
        default=str(DEFAULT_SEEN),
        help=f"seen_jobs.json path (default: {DEFAULT_SEEN})",
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
    output_path = (
        Path(args.output).expanduser()
        if str(args.output or "").strip()
        else default_output_path()
    )
    try:
        catalog = load_catalog(args.catalog)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load catalog: {exc}") from exc

    position = resolve_position(catalog, args.position_name)

    try:
        details = load_details(args.details)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load details: {exc}") from exc

    catalog_names = catalog_name_set(catalog)
    try:
        seen = load_seen(args.seen, catalog_names=catalog_names)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"error: failed to load seen: {exc}") from exc

    rows, skipped, pending = export_details(
        details,
        position,
        city_fallback=args.city,
        seen=seen,
        catalog_names=catalog_names,
    )

    print(
        "position=%s details=%s exported=%s skipped=%s"
        % (
            position["position_name"],
            len(details),
            len(rows),
            len(skipped),
        )
    )

    report_payload = {
        "position": position,
        "details_count": len(details),
        "exported_count": len(rows),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "seen": str(Path(args.seen).expanduser()),
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
        try:
            save_seen(args.seen, seen)
        except OSError as exc:
            raise SystemExit(f"error: failed to write seen: {exc}") from exc
        print("seen=%s marked=%s" % (Path(args.seen).expanduser(), len(pending)))


if __name__ == "__main__":
    main()
