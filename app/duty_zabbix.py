import html
from datetime import datetime, timedelta


ZABBIX_STATUS_COLORS = {
    "ok": "#7CFC98",
    "accent": "#58a6ff",
    "warning": "#f6d365",
    "error": "#ff5c5c",
    "normal": "#e8eef7",
}


def normalize_zabbix_profile_id(page):
    for key in ("zabbix_id", "zabbix_profile", "zabbix_profile_id", "profile", "profile_id"):
        value = str((page or {}).get(key, "") or "").strip()
        if value:
            return value
    return ""


def dashboard_url(page):
    for key in ("url", "open_url", "zabbix_url", "external_url"):
        value = str((page or {}).get(key, "") or "").strip()
        if value:
            return value
    return ""


def find_problems_page_url(config, product_name="", zabbix_profile=""):
    """Return URL and page config for the preferred enabled problems_page."""
    products = [p for p in (config or {}).get("products", []) if p.get("enabled", True)]
    product_name_norm = str(product_name or "").strip().casefold()
    if product_name_norm:
        preferred = [p for p in products if str(p.get("name", "") or "").strip().casefold() == product_name_norm]
        products = preferred + [p for p in products if p not in preferred]

    profile_norm = str(zabbix_profile or "").strip().casefold()
    candidates = []
    for product_index, product in enumerate(products):
        for page_index, page in enumerate(product.get("dashboards", []) or []):
            if not page.get("enabled", True):
                continue
            if str(page.get("type", "") or "").strip() != "problems_page":
                continue
            name_norm = str(page.get("name", "") or "").strip().casefold()
            page_profile = normalize_zabbix_profile_id(page).casefold()
            url = dashboard_url(page)
            score = 0
            if product_name_norm and str(product.get("name", "") or "").strip().casefold() == product_name_norm:
                score += 100
            if profile_norm and page_profile == profile_norm:
                score += 20
            if name_norm == "проблемы":
                score += 10
            if url:
                score += 1
            candidates.append((score, product_index, page_index, url, page, product))

    if not candidates:
        return "", None, None
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    _score, _product_index, _page_index, url, page, product = candidates[0]
    return url, page, product


def zabbix_status_color(status):
    status_text = str(status or "Ожидает проверки")
    lowered = status_text.casefold()
    if "url не найден" in lowered or "ошиб" in lowered or "нет данных" in lowered:
        return ZABBIX_STATUS_COLORS["error"]
    if "проверено" in lowered or lowered == "ок" or lowered == "ok" or "выполнено" in lowered:
        return ZABBIX_STATUS_COLORS["ok"]
    if "открыто" in lowered:
        return ZABBIX_STATUS_COLORS["accent"]
    if "таймаут" in lowered or "вним" in lowered or "пропущ" in lowered:
        return ZABBIX_STATUS_COLORS["warning"]
    return ZABBIX_STATUS_COLORS["normal"]


def zabbix_status_html(status):
    status_text = str(status or "Ожидает проверки")
    return f'<span style="color:{zabbix_status_color(status_text)}">{html.escape(status_text)}</span>'


def parse_zabbix_problem_time(value, now=None):
    text = str(value or "").strip()
    if not text:
        return None
    now = now or datetime.now()
    formats = (
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m %H:%M:%S",
        "%d.%m %H:%M",
    )
    for fmt in formats:
        if "%Y" not in fmt and len(text) >= 10 and text[2] == "." and text[5] == ".":
            continue
        try:
            if "%Y" not in fmt:
                parsed = datetime.strptime(f"{now.year}.{text[:11]}", f"%Y.{fmt}")
            else:
                parsed = datetime.strptime(text[:19], fmt)
            return parsed
        except ValueError:
            continue
    return None


def problem_search_text(problem):
    return " ".join(
        str((problem or {}).get(key, "") or "")
        for key in ("time", "severity", "host", "problem", "tags", "raw_text")
    ).casefold()


def problem_matches_keywords(problem, keywords=None, exclude_keywords=None):
    text = problem_search_text(problem)
    include = [str(item or "").strip().casefold() for item in (keywords or []) if str(item or "").strip()]
    exclude = [str(item or "").strip().casefold() for item in (exclude_keywords or []) if str(item or "").strip()]
    if any(item in text for item in exclude):
        return False
    if not include:
        return True
    return any(item in text for item in include)


def filter_problems_by_period(problems, days, now=None):
    now = now or datetime.now()
    threshold = now - timedelta(days=int(days))
    result = []
    for problem in problems or []:
        parsed = parse_zabbix_problem_time((problem or {}).get("time"), now=now)
        if parsed is None or parsed >= threshold:
            result.append(problem)
    return result


def normalize_problem_row(cells):
    cells = [str(cell or "").strip() for cell in (cells or [])]
    if not any(cells):
        return None
    if len(cells) >= 5:
        time, severity, host, problem = cells[0], cells[1], cells[2], cells[3]
        tags = "; ".join(cell for cell in cells[4:] if cell)
    elif len(cells) == 4:
        time, severity, host, problem = cells
        tags = ""
    elif len(cells) == 3:
        time, severity, problem = cells
        host = ""
        tags = ""
    else:
        time = ""
        severity = ""
        host = ""
        problem = " | ".join(cells)
        tags = ""
    return {
        "time": time,
        "severity": severity,
        "host": host,
        "problem": problem,
        "tags": tags,
        "raw_text": " | ".join(cells),
    }


def format_zabbix_problems_note_block(problems):
    problems = list(problems or [])
    if not problems:
        return ""
    lines = ["Замеченные проблемы Zabbix:"]
    for index, problem in enumerate(problems, start=1):
        severity = str(problem.get("severity", "") or "").strip() or "без важности"
        host = str(problem.get("host", "") or "").strip() or "без узла"
        text = str(problem.get("problem", "") or problem.get("raw_text", "") or "Проблема без описания").strip()
        lines.append(f"{index}. [{severity}] {host} — {text}")
        if problem.get("time"):
            lines.append(f"   Время: {problem.get('time')}")
        if problem.get("tags"):
            lines.append(f"   Теги: {problem.get('tags')}")
    return "\n".join(lines)
