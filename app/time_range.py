from time import time
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


def add_graph_cache_buster(url: str, timestamp_ms=None, param_name: str = "_oko_graph_refresh_ts") -> str:
    """Add a replaceable graph refresh cache-buster without accumulating query params."""
    source_url = str(url or "").strip()
    if not source_url:
        return source_url

    if timestamp_ms is None:
        timestamp_ms = int(time() * 1000)

    parsed = urlparse(source_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query.pop(param_name, None)
    query[param_name] = [str(timestamp_ms)]

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query, doseq=True),
        parsed.fragment,
    ))


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
