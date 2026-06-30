"""Host/node matching helpers for Live Zabbix detection checks."""

from __future__ import annotations

import re


def normalize_host(value):
    return re.sub(r"\s+", " ", str(value or "").strip().casefold()).replace("ё", "е")


def compact_host(value):
    return re.sub(r"[\W_]+", "", normalize_host(value), flags=re.UNICODE)


def _node_value(node, key):
    if isinstance(node, dict):
        return str(node.get(key) or "").strip()
    if key in {"host", "normalized_host"}:
        return str(node or "").strip()
    return ""


def _node_host(node):
    return _node_value(node, "normalized_host") or _node_value(node, "host")


def _aliases_for_zabbix_host(host):
    text = str(host or "").strip()
    aliases = [text]
    if " - " in text:
        aliases.append(text.rsplit(" - ", 1)[-1].strip())
    if "—" in text:
        aliases.append(text.rsplit("—", 1)[-1].strip())
    return [alias for alias in aliases if alias]


def build_node_indexes(nodes):
    indexes = {"host": {}, "compact": {}, "ip": {}}
    for node in nodes or []:
        host = _node_host(node)
        for value in {host, _node_value(node, "host"), _node_value(node, "normalized_host")}:
            if value:
                indexes["host"].setdefault(normalize_host(value), node)
                indexes["compact"].setdefault(compact_host(value), node)
        ip = _node_value(node, "ip")
        if ip:
            indexes["ip"].setdefault(ip, node)
    return indexes


def match_zabbix_host_to_node(zabbix_host, nodes, host_ip=""):
    indexes = build_node_indexes(nodes)
    for alias in _aliases_for_zabbix_host(zabbix_host):
        key = normalize_host(alias)
        if key in indexes["host"]:
            node = indexes["host"][key]
            return _match_result(node, "dash_alias" if alias != str(zabbix_host or "").strip() else "host", alias)
        compact = compact_host(alias)
        if compact and compact in indexes["compact"]:
            node = indexes["compact"][compact]
            return _match_result(node, "compact_host", alias)
    ip = str(host_ip or "").strip()
    if ip and ip in indexes["ip"]:
        return _match_result(indexes["ip"][ip], "ip", ip)
    return {"matched": False, "version": "", "matched_by": "", "matched_alias": ""}


def _match_result(node, matched_by, alias):
    return {
        "matched": True,
        "version": _node_value(node, "version"),
        "matched_by": matched_by,
        "matched_alias": str(alias or ""),
    }
