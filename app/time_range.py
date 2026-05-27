from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

SECONDS_MAP = {
    "30m": 1800,
    "1h": 3600,
    "3h": 10800,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "3d": 259200,
    "7d": 604800,
}


def apply_time_range_to_url(url: str, range_value: str) -> str:
    """
    Меняет период графика Zabbix.

    Если в URL есть period=3600 — меняет period.
    Если period нет — добавляет from=now-X&to=now.
    """
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    if "period" in query:
        query["period"] = [str(SECONDS_MAP.get(range_value, 3600))]
        query.pop("from", None)
        query.pop("to", None)
    else:
        query["from"] = [f"now-{range_value}"]
        query["to"] = ["now"]
        query.pop("period", None)

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query, doseq=True),
        parsed.fragment
    ))
