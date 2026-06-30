"""Helpers for automatic Zabbix acknowledgement after external task creation."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ZabbixAckTarget:
    url: str
    host: str = ""
    trigger: str = ""
    already_acknowledged: bool = False


def redmine_ack_comment(number: str = "", url: str = "") -> str:
    number = str(number or "").strip().lstrip("#")
    url = str(url or "").strip()
    if number and url:
        return f"Задача Redmine #{number}: {url}"
    if url:
        return f"Задача Redmine: {url}"
    if number:
        return f"Задача Redmine #{number}"
    return ""


def mm_otrs_ack_comment(number: str = "", url: str = "") -> str:
    number = str(number or "").strip().lstrip("#")
    url = str(url or "").strip()
    if number and url:
        return f"Задача на ММ #{number}: {url}"
    if number:
        return f"Задача на ММ #{number}"
    if url:
        return f"Задача на ММ: {url}"
    return ""


def extract_redmine_reference(text: str, url: str = "") -> dict:
    combined = " ".join([str(text or ""), str(url or "")])
    match = re.search(r"(?:issues/|#)(\d{2,})", combined, re.IGNORECASE)
    issue_url = str(url or "").strip()
    if not issue_url:
        url_match = re.search(r"https?://\S*/issues/\d+", combined, re.IGNORECASE)
        issue_url = url_match.group(0).rstrip('.,;)"\'') if url_match else ""
    return {"number": match.group(1) if match else "", "url": issue_url}


def extract_mm_otrs_reference(text: str, url: str = "") -> dict:
    combined = " ".join([str(text or ""), str(url or "")])
    patterns = (
        r"Ticket#?\s*(\d{6,})",
        r"TicketNumber[=:/\s]+(\d{6,})",
        r"TN[=:/\s]+(\d{6,})",
        r"№\s*(\d{6,})",
        r"#(\d{6,})",
    )
    number = ""
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            number = match.group(1)
            break
    ticket_url = str(url or "").strip()
    if not ticket_url:
        url_match = re.search(r"https?://\S+", combined, re.IGNORECASE)
        ticket_url = url_match.group(0).rstrip('.,;)"\'') if url_match else ""
    return {"number": number, "url": ticket_url}


def comment_already_present(existing_text: str, comment: str) -> bool:
    return bool(comment and str(comment) in str(existing_text or ""))


def needs_acknowledgement(item) -> bool:
    ack_text = str(getattr(item, "ack_text", "") or (item.get("ack_text", "") if isinstance(item, dict) else "")).strip().casefold()
    if ack_text in {"да", "yes"}:
        return False
    if ack_text in {"нет", "no"}:
        return True
    acknowledged = getattr(item, "acknowledged", None) if not isinstance(item, dict) else item.get("acknowledged")
    return acknowledged is False


def deduplicate_ack_targets(items) -> list[ZabbixAckTarget]:
    targets = []
    seen = set()
    for item in items or []:
        get = item.get if isinstance(item, dict) else lambda key, default="": getattr(item, key, default)
        url = str(get("ack_url", "") or get("problem_url", "") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        targets.append(ZabbixAckTarget(
            url=url,
            host=str(get("host", "") or ""),
            trigger=str(get("trigger_name", "") or ""),
            already_acknowledged=not needs_acknowledgement(item),
        ))
    return targets


def plan_zabbix_update(item, task_comment: str) -> dict:
    url = str((item.get("ack_url") if isinstance(item, dict) else getattr(item, "ack_url", "")) or (item.get("problem_url") if isinstance(item, dict) else getattr(item, "problem_url", "")) or "").strip()
    if not task_comment:
        return {"ok": False, "reason": "Не удалось определить номер/ссылку созданной задачи."}
    if not url:
        return {"ok": False, "reason": "Нет URL подтверждения Zabbix для проблемы."}
    return {"ok": True, "url": url, "ack_required": needs_acknowledgement(item), "comment": task_comment}


def zabbix_acknowledgement_js(comment: str, ack_required: bool) -> str:
    """Build robust JS for Zabbix update/acknowledge pages."""
    import json
    return f"""
(function() {{
  const taskComment = {json.dumps(comment, ensure_ascii=False)};
  const ackRequired = {str(bool(ack_required)).lower()};
  function text(el) {{ return String((el && (el.innerText || el.textContent || el.value)) || ''); }}
  function fire(el) {{ ['input','change','blur'].forEach(t => {{ try {{ el.dispatchEvent(new Event(t, {{bubbles:true}})); }} catch(e) {{}} }}); }}
  function click(el) {{ if (!el) return false; try {{ el.scrollIntoView({{block:'center'}}); }} catch(e) {{}} try {{ el.click(); return true; }} catch(e) {{ return false; }} }}
  const allText = text(document.body);
  const duplicate = allText.indexOf(taskComment) >= 0;
  const messageField = document.querySelector('textarea[name*="message" i], textarea[name*="comment" i], textarea[name*="note" i], input[name*="message" i], input[name*="comment" i], input[name*="note" i], textarea');
  let commentAdded = false;
  if (messageField && !duplicate) {{ messageField.focus(); messageField.value = taskComment; fire(messageField); commentAdded = true; }}
  const ackSelectors = [
    'input[type="checkbox"][name*="ack" i]', 'input[type="checkbox"][id*="ack" i]',
    'input[type="checkbox"][name*="acknowledge" i]', 'input[type="checkbox"][value="1"]'
  ];
  let ackTouched = false;
  if (ackRequired) {{
    for (const selector of ackSelectors) {{
      const cb = document.querySelector(selector);
      if (cb && !cb.checked) {{ cb.checked = true; fire(cb); ackTouched = true; break; }}
    }}
    const labels = Array.from(document.querySelectorAll('label, span, button')).filter(el => /Acknowledge|Подтвердить|Да|Yes/i.test(text(el)));
    if (!ackTouched && labels.length) ackTouched = click(labels[0]);
  }}
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a'));
  const submit = buttons.find(el => /Update|Обновить|Acknowledge|Подтвердить|Save|Сохранить/i.test(text(el) || el.value || el.title)) || document.querySelector('button[type="submit"], input[type="submit"]');
  const submitted = (commentAdded || ackTouched) ? click(submit) : false;
  return JSON.stringify({{ok:true, duplicate:duplicate, comment_added:commentAdded, ack_touched:ackTouched, submitted:submitted, has_message_field:!!messageField, has_submit:!!submit}});
}})();
"""
