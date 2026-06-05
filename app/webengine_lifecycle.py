"""Safe lifecycle helpers for Qt WebEngine widgets."""

from __future__ import annotations

import os
import weakref

from PySide6.QtCore import QTimer, QUrl

_TRACKED_WEB_VIEWS = weakref.WeakSet()


def register_web_view(view):
    """Track a QWebEngineView for lightweight diagnostics."""
    if view is not None:
        try:
            _TRACKED_WEB_VIEWS.add(view)
        except TypeError:
            pass
    return view


def tracked_web_view_count():
    return len(_TRACKED_WEB_VIEWS)


def current_rss_mb():
    """Return current process RSS in MB without external dependencies."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) / 1024.0
    except OSError:
        pass

    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if os.name == "posix":
            return float(rss) / 1024.0
        return float(rss) / (1024.0 * 1024.0)
    except Exception:
        return None


def _log(logger, level, message, *args):
    if logger is None:
        return
    try:
        getattr(logger, level)(message, *args)
    except Exception:
        pass


def _safe_disconnect(signal, handler=None):
    try:
        if signal is not None:
            if handler is None:
                signal.disconnect()
            else:
                signal.disconnect(handler)
    except (RuntimeError, TypeError):
        pass


def safe_delete_web_view(view, logger=None, context="", load_handler=None, extra_signals=None):
    """
    Stop and delete a QWebEngineView/QWebEnginePage pair safely via the Qt event loop.

    Callers should clear their own references after invoking this helper.
    """
    label = f": {context}" if context else ""
    _log(logger, "info", "WebEngine cleanup started%s", label)

    if view is None:
        _log(logger, "info", "WebEngine cleanup finished%s", label)
        return

    try:
        _TRACKED_WEB_VIEWS.discard(view)
    except Exception:
        pass

    def delete_objects(hidden_view=view):
        hidden_page = None
        try:
            hidden_view.stop()
        except RuntimeError:
            pass
        except Exception:
            pass

        try:
            if load_handler is not None:
                _safe_disconnect(hidden_view.loadFinished, load_handler)
            else:
                _safe_disconnect(hidden_view.loadFinished)
        except RuntimeError:
            pass
        except Exception:
            pass

        for signal_handler in extra_signals or ():
            if not signal_handler:
                continue
            signal, handler = signal_handler if isinstance(signal_handler, tuple) else (signal_handler, None)
            _safe_disconnect(signal, handler)

        try:
            hidden_page = hidden_view.page()
        except RuntimeError:
            hidden_page = None
        except Exception:
            hidden_page = None

        try:
            hidden_view.setUrl(QUrl("about:blank"))
        except RuntimeError:
            pass
        except Exception:
            pass

        try:
            if hidden_page is not None:
                hidden_page.deleteLater()
        except RuntimeError:
            pass
        except Exception:
            pass

        try:
            hidden_view.setParent(None)
            hidden_view.deleteLater()
        except RuntimeError:
            pass
        except Exception:
            pass

        _log(logger, "info", "WebEngine cleanup finished%s", label)

    QTimer.singleShot(0, delete_objects)
