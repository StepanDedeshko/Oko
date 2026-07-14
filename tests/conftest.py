from __future__ import annotations

import gc

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Destroy the shared Qt application before Python unloads PySide modules.

    Several offscreen UI tests intentionally share one QApplication. Letting the
    interpreter finalize QtWebEngine extension modules before that application
    is destroyed can end an otherwise successful test run with SIGSEGV. Close
    and delete Qt objects while their Python bindings are still fully alive.
    """
    app = QApplication.instance()
    if app is None:
        return

    for widget in list(QApplication.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            pass

    try:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        app.quit()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    except RuntimeError:
        pass

    if shiboken6.isValid(app):
        shiboken6.delete(app)
    gc.collect()
