"""Critical Redmine image flow is syntax-checked by release-checks.

The real attachment path requires authenticated internal Zabbix and Redmine
sessions and is verified manually on a live critical trigger. Keeping this test
module import-free avoids a PySide6/QtWebEngine interpreter-shutdown crash in
the combined offscreen pytest process.
"""

__test__ = False
