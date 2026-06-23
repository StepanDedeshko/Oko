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


def zabbix_problems_collect_js(max_pages=10, max_problems=500, page_delay_ms=900):
    return rf"""
    (function() {{
        const MAX_PAGES = {int(max_pages)};
        const MAX_PROBLEMS = {int(max_problems)};
        const PAGE_DELAY_MS = {int(page_delay_ms)};
        const TARGET_TBODY_SELECTOR = '#t6a3a4bcc6c78d563014208 > tbody';
        function clean(text) {{ return String(text || '').replace(/\s+/g, ' ').trim(); }}
        function cellText(td) {{
            const bits = [td.innerText, td.textContent, td.getAttribute('title'), td.getAttribute('aria-label')]
                .map(clean).filter(Boolean);
            return bits[0] || '';
        }}
        function rowObjectFromCells(cells, raw) {{
            const values = cells.map(cellText).filter(Boolean);
            if (!values.length && raw) {{
                return {{time: '', severity: '', host: '', problem: raw, tags: '', raw_text: raw, cells: [raw]}};
            }}
            return {{cells: values, rawText: raw, raw_text: raw}};
        }}
        function tbodyCandidates() {{
            const result = [];
            const exact = document.querySelector(TARGET_TBODY_SELECTOR);
            if (exact) {{ result.push(exact); }}
            for (const selector of ['#problem_form table tbody', '#problem_form tbody']) {{
                for (const node of Array.from(document.querySelectorAll(selector))) {{
                    if (node && !result.includes(node)) {{ result.push(node); }}
                }}
            }}
            for (const node of Array.from(document.querySelectorAll('table tbody'))) {{
                if (node && !result.includes(node)) {{ result.push(node); }}
            }}
            return result;
        }}
        function collectCurrentPage() {{
            const rows = [];
            for (const tbody of tbodyCandidates()) {{
                for (const tr of Array.from(tbody.querySelectorAll('tr'))) {{
                    const cells = Array.from(tr.querySelectorAll('td'));
                    const raw = clean(tr.innerText || tr.textContent || '');
                    if (!cells.length && !raw) {{ continue; }}
                    const object = rowObjectFromCells(cells, raw);
                    if ((object.cells && object.cells.length) || object.problem || object.raw_text || object.rawText) {{
                        rows.push(object);
                    }}
                    if (rows.length >= MAX_PROBLEMS) {{ return rows; }}
                }}
                if (rows.length) {{ return rows; }}
            }}
            for (const node of Array.from(document.querySelectorAll('[class*=problem], [class*=trigger], [data-eventid], [data-triggerid]'))) {{
                const raw = clean(node.innerText || node.textContent || node.getAttribute('title') || node.getAttribute('aria-label') || '');
                if (raw) {{ rows.push({{time: '', severity: '', host: '', problem: raw, tags: '', raw_text: raw, cells: [raw]}}); }}
                if (rows.length >= MAX_PROBLEMS) {{ break; }}
            }}
            return rows;
        }}
        function nextPageButton() {{
            const nav = document.querySelector('#problem_form > div.table-paging > nav') || document.querySelector('#problem_form .table-paging nav');
            if (!nav) {{ return null; }}
            const candidates = Array.from(nav.querySelectorAll('a, button'));
            return candidates.find((node) => {{
                const text = clean(node.innerText || node.textContent || node.getAttribute('title') || node.getAttribute('aria-label') || '');
                const disabled = node.disabled || node.classList.contains('disabled') || node.getAttribute('aria-disabled') === 'true';
                return !disabled && (/next|след|›|»/i.test(text) || node.classList.contains('next'));
            }}) || null;
        }}
        const rows = collectCurrentPage().slice(0, MAX_PROBLEMS);
        const next = nextPageButton();
        return {{rows: rows, hasNext: Boolean(next), clickedNext: false, maxPages: MAX_PAGES, maxProblems: MAX_PROBLEMS, pageDelayMs: PAGE_DELAY_MS}};
    }})();
    """


def zabbix_problems_next_page_js():
    return r"""
    (function() {
        function clean(text) { return String(text || '').replace(/\s+/g, ' ').trim(); }
        const nav = document.querySelector('#problem_form > div.table-paging > nav') || document.querySelector('#problem_form .table-paging nav');
        if (!nav) { return false; }
        const candidates = Array.from(nav.querySelectorAll('a, button'));
        const next = candidates.find((node) => {
            const text = clean(node.innerText || node.textContent || node.getAttribute('title') || node.getAttribute('aria-label') || '');
            const disabled = node.disabled || node.classList.contains('disabled') || node.getAttribute('aria-disabled') === 'true';
            return !disabled && (/next|след|›|»/i.test(text) || node.classList.contains('next'));
        }) || null;
        if (!next) { return false; }
        next.click();
        return true;
    })();
    """


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
    if isinstance(cells, dict):
        direct = {
            "time": str(cells.get("time", "") or "").strip(),
            "severity": str(cells.get("severity", "") or "").strip(),
            "host": str(cells.get("host", "") or "").strip(),
            "problem": str(cells.get("problem", "") or "").strip(),
            "tags": str(cells.get("tags", "") or "").strip(),
            "raw_text": str(cells.get("raw_text", cells.get("rawText", "")) or "").strip(),
        }
        if any(direct.values()):
            if not direct["problem"]:
                direct["problem"] = direct["raw_text"]
            return direct
        cells = cells.get("cells", [])

    values = [str(cell or "").strip() for cell in (cells or [])]
    values = [value for value in values if value]
    if not values:
        return None

    severity_words = (
        "disaster", "high", "average", "warning", "information", "not classified",
        "чрезвычай", "высок", "средн", "предупреж", "информац", "не классиф",
    )
    if len(values) >= 5 and parse_zabbix_problem_time(values[0]) is not None and any(word in values[1].casefold() for word in severity_words):
        return {
            "time": values[0],
            "severity": values[1],
            "host": values[2],
            "problem": values[3],
            "tags": "; ".join(cell for cell in values[4:] if cell),
            "raw_text": " | ".join(values),
        }

    time = ""
    severity = ""
    tags = ""
    for value in values:
        lowered = value.casefold()
        if not time and parse_zabbix_problem_time(value) is not None:
            time = value
            continue
        if not severity and any(word in lowered for word in severity_words):
            severity = value
            continue
        if not tags and ("=" in value or ":" in value) and (";" in value or "," in value or "=" in value):
            tags = value

    candidates = [value for value in values if value not in {time, severity, tags}]
    problem = max(candidates, key=len) if candidates else " | ".join(values)
    host_candidates = [value for value in candidates if value != problem]
    host = host_candidates[0] if host_candidates else ""

    if len(values) >= 5 and not any([time, severity, host, tags]):
        time, severity, host, problem = values[0], values[1], values[2], values[3]
        tags = "; ".join(cell for cell in values[4:] if cell)

    raw_text = " | ".join(values)
    return {
        "time": time,
        "severity": severity,
        "host": host,
        "problem": problem or raw_text,
        "tags": tags,
        "raw_text": raw_text,
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
