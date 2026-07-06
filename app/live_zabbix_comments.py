"""Helpers for Live Zabbix task comment normalization."""

from __future__ import annotations

import re


def normalize_zabbix_task_comment_candidate(value: str, allow_plain_number: bool = True) -> list[str]:
    """Return normalized task comments found in a Zabbix action message candidate."""
    source = re.sub(r"\s+", " ", str(value or "")).strip()
    if not source:
        return []

    found: list[str] = []

    redmine = re.search(r"Задача\s+Redmine\s+#(\d+)\s*:\s*(https?://\S+)", source, re.IGNORECASE)
    if redmine:
        found.append(f"Задача Redmine #{redmine.group(1)}: {redmine.group(2)}")

    raw_redmine_url = re.search(r"https?://[^\s<>\"']*redmine[^\s<>\"']*/issues/(\d+)(?:[/?#][^\s<>\"']*)?", source, re.IGNORECASE)
    if raw_redmine_url:
        return [source]

    mm_hash_url = re.search(r"Задача\s+на\s+ММ\s+#(\d+)\s*:\s*(https?://\S+)", source, re.IGNORECASE)
    if mm_hash_url:
        found.append(f"Задача на ММ #{mm_hash_url.group(1)}: {mm_hash_url.group(2)}")

    mm_hash = re.search(r"Задача\s+на\s+ММ\s+#(\d{5,})\b", source, re.IGNORECASE)
    if mm_hash and not mm_hash_url:
        found.append(f"Задача на ММ: {mm_hash.group(1)}")

    label_number = re.search(r"(?:Задача\s+на\s+ММ|Задача\s+ММ|ММ|OTRS)\s*:\s*(\d{5,})\b", source, re.IGNORECASE)
    if label_number:
        found.append(f"Задача на ММ: {label_number.group(1)}")

    if allow_plain_number and not re.search(r"https?://", source, re.IGNORECASE) and len(source) <= 40:
        plain = re.search(r"^\s*(?:№|#)?\s*(\d{5,})\s*$", source)
        if plain:
            found.append(f"Задача на ММ: {plain.group(1)}")

    return found
