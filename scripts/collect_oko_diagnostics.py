#!/usr/bin/env python3
"""Collect safe Oko diagnostics without secrets or arbitrary HOME scans."""
from __future__ import annotations
import json, platform, re, shutil, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / f"oko_diagnostics_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
SECRET_RE = re.compile(r"(?i)(password|passwd|token|cookie|login|username|email|secret|auth)\s*[:=]\s*[^\s,;]+")
URL_RE = re.compile(r"https?://[^\s\"']+")

def redact(text: str) -> str:
    return URL_RE.sub("https://<redacted-url>", SECRET_RE.sub(r"\1=<redacted>", text))

def copy_log(path: Path):
    if path.exists() and path.is_file():
        target = OUT / "logs" / path.name.replace("/", "_")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(redact(path.read_text(encoding="utf-8", errors="replace")[-200000:]), encoding="utf-8")

def safe_config_summary(path: Path):
    if not path.exists(): return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "top_level_keys": sorted(data.keys()),
        "products_count": len(data.get("products") or []),
        "zabbix_instances_count": len(data.get("zabbix_instances") or []),
        "duty_mode": {k: ("<set>" if v else "") for k, v in (data.get("duty_mode") or {}).items() if "password" not in k.lower() and "login" not in k.lower()},
        "live_zabbix_monitor_keys": sorted((data.get("live_zabbix_monitor") or {}).keys()),
    }

def main():
    OUT.mkdir()
    for path in [Path.home()/"Monitor/logs/oko.log", Path("/opt/oko/logs/oko.log")]: copy_log(path)
    for path in (Path.home()/".config/zabbix_duty_panel").glob("*.log"): copy_log(path)
    cred = Path.home()/".config/zabbix_duty_panel/credentials.json"
    cred_keys = []
    if cred.exists():
        try: cred_keys = sorted(json.loads(cred.read_text(encoding="utf-8")).keys())
        except Exception: cred_keys = ["<unreadable>"]
    summary = {
        "version_app_path": {"repo": str(ROOT), "config": str(ROOT/"config.json")},
        "python": {"executable": sys.executable, "version": sys.version, "platform": platform.platform()},
        "launcher": {"run_oko_exists": (ROOT/"run_oko.sh").exists()},
        "config_summary": safe_config_summary(ROOT/"config.json"),
        "credentials_keys_only": cred_keys,
    }
    (OUT/"summary.json").write_text(redact(json.dumps(summary, ensure_ascii=False, indent=2)), encoding="utf-8")
    archive = shutil.make_archive(str(OUT), "zip", OUT)
    print(archive)
if __name__ == "__main__": main()
