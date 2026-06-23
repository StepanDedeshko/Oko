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


def _problem_field(problem, field, default=""):
    if isinstance(problem, dict):
        return problem.get(field, default)
    return getattr(problem, field, default)


def format_zabbix_problems_note_block(problems):
    problems = list(problems or [])
    if not problems:
        return ""
    lines = ["Замеченные проблемы Zabbix:"]
    for index, problem in enumerate(problems, start=1):
        time = str(_problem_field(problem, "time", "") or "").strip() or "Время не указано"
        severity = str(_problem_field(problem, "severity", "") or "").strip() or "Важность не указана"
        host = str(_problem_field(problem, "host", "") or "").strip() or "Узел не указан"
        text = str(
            _problem_field(problem, "problem", "")
            or _problem_field(problem, "raw_text", "")
            or "Проблема не указана"
        ).strip() or "Проблема не указана"
        lines.append(f'{index}. {time}, {severity}, {host}, {text}. - "Ссылка на задачу в Redmine"')
        if _problem_field(problem, "handled", False):
            lines.append("   Примечание: проблема уже была добавлена в задачу ранее.")
    return "\n".join(lines)


# --- CSV-based Zabbix problems export -------------------------------------------------
import csv
import hashlib
import io
import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class ZabbixProblem:
    severity: str = ""
    time: str = ""
    recovery_time: str = ""
    state: str = ""
    host: str = ""
    problem: str = ""
    duration: str = ""
    acknowledged: str = ""
    actions: str = ""
    tags: str = ""
    status: str = "ПРОБЛЕМА"
    handled: bool = False
    raw: dict = field(default_factory=dict)
    key: str = ""

    def get(self, key, default=None):
        return getattr(self, key, default)

    def to_dict(self):
        return asdict(self)


CSV_HEADER_MAP = {
    "важность": "severity",
    "severity": "severity",
    "время": "time",
    "time": "time",
    "время восстановления": "recovery_time",
    "recovery time": "recovery_time",
    "состояние": "state",
    "state": "state",
    "узел сети": "host",
    "host": "host",
    "проблема": "problem",
    "problem": "problem",
    "длительность": "duration",
    "duration": "duration",
    "подтверждено": "acknowledged",
    "acknowledged": "acknowledged",
    "действия": "actions",
    "actions": "actions",
    "теги": "tags",
    "tags": "tags",
}


def zabbix_problem_row_status_color(status):
    status_text = normalize_problem_text(status).casefold()
    if status_text == "проблема":
        return "#ff5c5c"
    if status_text in {"решено", "решена"}:
        return "#7CFC98"
    return ""


def normalize_problem_text(value):
    return " ".join(str(value or "").replace("\ufeff", "").split()).strip()


def _problem_attr(problem, key):
    if isinstance(problem, ZabbixProblem):
        return getattr(problem, key, "")
    if isinstance(problem, dict):
        return problem.get(key, "")
    return ""


def make_zabbix_problem_key(problem):
    parts = [
        normalize_problem_text(_problem_attr(problem, "severity")).casefold(),
        normalize_problem_text(_problem_attr(problem, "time")).casefold(),
        normalize_problem_text(_problem_attr(problem, "host")).casefold(),
        normalize_problem_text(_problem_attr(problem, "problem")).casefold(),
        normalize_problem_text(_problem_attr(problem, "tags")).casefold(),
    ]
    source = "|".join(parts)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _status_from_csv_fields(state, recovery_time):
    state_text = normalize_problem_text(state).casefold()
    if normalize_problem_text(recovery_time) or "реш" in state_text or "resolved" in state_text:
        return "РЕШЕНО"
    return "ПРОБЛЕМА"


def _read_csv_text(path):
    path = Path(path)
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            return path.read_text(encoding=encoding), encoding
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace"), "utf-8"


def parse_zabbix_problems_csv(path):
    text, _encoding = _read_csv_text(path)
    rows = csv.DictReader(io.StringIO(text))
    problems = []
    for row in rows:
        if not row or not any(normalize_problem_text(value) for value in row.values()):
            continue
        normalized = {}
        raw = {}
        for header, value in row.items():
            header_text = normalize_problem_text(header).casefold()
            raw[normalize_problem_text(header)] = normalize_problem_text(value)
            target = CSV_HEADER_MAP.get(header_text)
            if target:
                normalized[target] = normalize_problem_text(value)
        problem = ZabbixProblem(
            severity=normalized.get("severity", ""),
            time=normalized.get("time", ""),
            recovery_time=normalized.get("recovery_time", ""),
            state=normalized.get("state", ""),
            host=normalized.get("host", ""),
            problem=normalized.get("problem", ""),
            duration=normalized.get("duration", ""),
            acknowledged=normalized.get("acknowledged", ""),
            actions=normalized.get("actions", ""),
            tags=normalized.get("tags", ""),
            raw=raw,
        )
        problem.status = _status_from_csv_fields(problem.state, problem.recovery_time)
        problem.key = make_zabbix_problem_key(problem)
        problems.append(problem)
    return problems


def compare_zabbix_problem_exports(current_problems, previous_problems=None):
    current = list(current_problems or [])
    previous = list(previous_problems or [])
    current_keys = {problem.key for problem in current if problem.key}
    result = []
    for problem in current:
        problem.status = _status_from_csv_fields(problem.state, problem.recovery_time)
        result.append(problem)
    for old in previous:
        if old.key and old.key not in current_keys:
            resolved = ZabbixProblem(**old.to_dict()) if isinstance(old, ZabbixProblem) else ZabbixProblem(**old)
            resolved.status = "РЕШЕНО"
            result.append(resolved)
    return result


def zabbix_problem_export_dir(base_dir=None):
    base = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent.parent
    return base / "data" / "zabbix_problem_exports"


def ensure_zabbix_problem_export_dir(base_dir=None):
    path = zabbix_problem_export_dir(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    handled = path / "handled_problems.json"
    if not handled.exists():
        handled.write_text(json.dumps({"handled": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rotate_zabbix_problem_csv_files(export_dir):
    export_dir = Path(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    current = export_dir / "current.csv"
    previous = export_dir / "previous.csv"
    if previous.exists():
        previous.unlink()
    if current.exists():
        current.replace(previous)
    return current, previous


def cleanup_zabbix_problem_csv_files(export_dir, logger=None):
    export_dir = Path(export_dir)
    for csv_path in export_dir.glob("*.csv"):
        if csv_path.name in {"current.csv", "previous.csv"}:
            continue
        try:
            csv_path.unlink()
        except Exception as exc:
            if logger is not None:
                logger.warning("Failed to delete old Zabbix problems CSV: path=%s error=%s", csv_path, exc)


def load_handled_zabbix_problems(export_dir, logger=None):
    path = Path(export_dir) / "handled_problems.json"
    try:
        if not path.exists():
            path.write_text(json.dumps({"handled": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        handled = data.get("handled", {}) if isinstance(data, dict) else {}
        return handled if isinstance(handled, dict) else {}
    except Exception as exc:
        if logger is not None:
            logger.warning("Failed to read handled Zabbix problems, recreating file: path=%s error=%s", path, exc)
        path.write_text(json.dumps({"handled": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {}


def save_handled_zabbix_problems(export_dir, handled):
    path = Path(export_dir) / "handled_problems.json"
    payload = {"handled": handled or {}}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def mark_zabbix_problems_handled(export_dir, problems, handled_at=None):
    handled = load_handled_zabbix_problems(export_dir)
    handled_at = handled_at or datetime.now().isoformat(timespec="seconds")
    for problem in problems or []:
        key = _problem_attr(problem, "key") or make_zabbix_problem_key(problem)
        handled[key] = {
            "handled_at": handled_at,
            "severity": _problem_attr(problem, "severity"),
            "time": _problem_attr(problem, "time"),
            "host": _problem_attr(problem, "host"),
            "problem": _problem_attr(problem, "problem"),
            "tags": _problem_attr(problem, "tags"),
        }
    save_handled_zabbix_problems(export_dir, handled)
    return handled


def apply_handled_zabbix_problems(problems, handled):
    handled = handled or {}
    for problem in problems or []:
        key = _problem_attr(problem, "key") or make_zabbix_problem_key(problem)
        if isinstance(problem, ZabbixProblem):
            problem.key = key
            problem.handled = key in handled
        elif isinstance(problem, dict):
            problem["key"] = key
            problem["handled"] = key in handled
    return problems


def load_compared_zabbix_problem_exports(export_dir, logger=None):
    export_dir = Path(export_dir)
    current_path = export_dir / "current.csv"
    previous_path = export_dir / "previous.csv"
    current = parse_zabbix_problems_csv(current_path) if current_path.exists() else []
    previous = parse_zabbix_problems_csv(previous_path) if previous_path.exists() else []
    compared = compare_zabbix_problem_exports(current, previous)
    handled = load_handled_zabbix_problems(export_dir, logger=logger)
    apply_handled_zabbix_problems(compared, handled)
    return compared


def adopt_latest_zabbix_problem_csv(export_dir):
    export_dir = Path(export_dir)
    current = export_dir / "current.csv"
    candidates = [
        path for path in export_dir.glob("*.csv")
        if path.name not in {"current.csv", "previous.csv"}
    ]
    if current.exists():
        return current
    if not candidates:
        return current
    latest = max(candidates, key=lambda path: path.stat().st_mtime)
    latest.replace(current)
    return current
