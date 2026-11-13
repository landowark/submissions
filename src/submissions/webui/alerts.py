"""
Shows report_result alerts in the web UI instead of Qt AlertPops.
"""
from __future__ import annotations
import json
import webview


def install(main_window) -> None:
    """
    Routes tools.report_result alerts to a JS alert in the focused window. Call before webview.start().
    """
    from tools import set_alert_handler

    def show(alert) -> None:
        window = webview.active_window() or main_window
        message = json.dumps(f"{alert.status}: {alert.msg}")
        window.evaluate_js(f"alert({message})")

    set_alert_handler(show)