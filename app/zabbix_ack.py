"""Helpers for copying existing Redmine/MM task comments in Zabbix acknowledgements."""

from __future__ import annotations

import re

_TASK_ACK_COMMENT_RE = re.compile(
    r"(?m)^\s*(Задача\s+(?:Redmine|на\s+ММ)\s+#\d+:\s+https?://\S+)\s*$"
)


def extract_task_ack_comments(text: str) -> list[str]:
    """Return unique strict task acknowledgement comments from Zabbix text.

    Only full comments with a supported Russian prefix, task number and URL are
    accepted. URL-only and number-only fragments are intentionally ignored.
    """
    result: list[str] = []
    seen: set[str] = set()
    for match in _TASK_ACK_COMMENT_RE.finditer(str(text or "")):
        comment = " ".join(match.group(1).strip().split())
        if comment in seen:
            continue
        seen.add(comment)
        result.append(comment)
    return result


def has_exact_task_ack_comment(text: str, comment: str) -> bool:
    """Return True when the same exact supported comment already exists."""
    target = " ".join(str(comment or "").strip().split())
    if not target:
        return False
    return target in extract_task_ack_comments(text)
