#!/usr/bin/env python3
"""Field contracts for list cards, classify input, and details.

Cleaning scripts and scrapers share these whitelists. Do not persist extra keys.
"""

from __future__ import annotations

import re
from typing import Any

_ENCRYPT_JOB_ID_IN_LINK_RE = re.compile(r"/job_detail/([^./]+)\.html", re.IGNORECASE)
_ILLEGAL_DIRNAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# jobs.json / list_batch — enough to open details later
LIST_JOB_FIELDS = (
    "title",
    "boss_name",
    "boss_title",
    "salary",
    "location",
    "tags",
    "encrypt_job_id",
    "job_link",
    "security_id",
    "lid",
)

# classify_input.jobs — Agent only
CLASSIFY_JOB_FIELDS = (
    "id",
    "title",
    "company",
    "boss_title",
    "salary",
    "tags",
)

# details.json after clean B / what export needs plus seen key
DETAIL_FIELDS = (
    "encrypt_job_id",
    "title",
    "company",
    "salary",
    "location",
    "jd",
    "position_name",
    "job_intent_id",
    "job_intent_label",
)


def search_term_dirname(term: str) -> str:
    cleaned = _ILLEGAL_DIRNAME_RE.sub("_", str(term or "").strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "search"


def resolve_encrypt_job_id(job: dict[str, Any] | None) -> str:
    if not isinstance(job, dict):
        return ""
    eid = str(job.get("encrypt_job_id") or job.get("id") or "").strip()
    if eid:
        return eid
    link = str(job.get("job_link") or job.get("link") or "")
    match = _ENCRYPT_JOB_ID_IN_LINK_RE.search(link)
    return match.group(1) if match else ""


def job_dedupe_key(job: dict[str, Any] | None) -> str:
    eid = resolve_encrypt_job_id(job)
    if eid:
        return eid
    return str((job or {}).get("job_link") or "").strip()


def project_list_job(job: dict[str, Any] | None) -> dict[str, str]:
    src = job or {}
    eid = resolve_encrypt_job_id(src)
    link = str(src.get("job_link") or "").strip()
    if not link and eid:
        link = f"https://www.zhipin.com/job_detail/{eid}.html"
    location = str(src.get("location") or "").strip()
    location = re.sub(r"·+", "·", location).strip("· ")
    return {
        "title": str(src.get("title") or "").strip(),
        "boss_name": str(src.get("boss_name") or src.get("company") or "").strip(),
        "boss_title": str(src.get("boss_title") or "").strip(),
        "salary": str(src.get("salary") or "").strip(),
        "location": location,
        "tags": str(src.get("tags") or "").strip(),
        "encrypt_job_id": eid,
        "job_link": link,
        "security_id": str(src.get("security_id") or src.get("securityId") or "").strip(),
        "lid": str(src.get("lid") or "").strip(),
    }


def project_classify_job(job: dict[str, Any] | None) -> dict[str, str]:
    src = job or {}
    eid = resolve_encrypt_job_id(src)
    return {
        "id": eid,
        "title": str(src.get("title") or "").strip(),
        "company": str(
            src.get("company") or src.get("boss_name") or ""
        ).strip(),
        "boss_title": str(src.get("boss_title") or "").strip(),
        "salary": str(src.get("salary") or "").strip(),
        "tags": str(src.get("tags") or "").strip(),
    }


def project_detail(detail: dict[str, Any] | None) -> dict[str, str]:
    src = detail or {}
    out = {}
    for key in DETAIL_FIELDS:
        value = src.get(key)
        if value is None:
            out[key] = ""
        elif isinstance(value, list):
            out[key] = " | ".join(str(x) for x in value if str(x).strip())
        else:
            out[key] = str(value).strip()
    if not out.get("encrypt_job_id"):
        out["encrypt_job_id"] = resolve_encrypt_job_id(src)
    if not out.get("company"):
        out["company"] = str(src.get("boss_name") or "").strip()
    return out
