import html


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
