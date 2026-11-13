"""
Blocking windows for the web UI: the pywebview stand-in for QDialog.exec().
"""
from __future__ import annotations
import threading
import webview

# NOTE: Calls pywebview.api directly so pages without bridge.js can use it too.
MODAL_BUTTONS = """
    <div style="padding: 10px 0; display: flex; gap: 8px; justify-content: flex-end;">
    <button type="button" onclick="pywebview.api.cancel()">Cancel</button>
    <button type="button" id="modal-ok" onclick="this.disabled = true; pywebview.api.accept()">OK</button>
    </div>
"""


class ModalApi(object):
    """
    Base js_api for a window that blocks the calling thread until OK or Cancel.
    """

    def __init__(self):
        self._window = None
        self._done = threading.Event()
        self._accepted = False

    def accept(self) -> None:
        self._accepted = True
        self._done.set()
        self._window.destroy()

    def cancel(self) -> None:
        self._done.set()
        self._window.destroy()


def add_buttons(html: str) -> str:
    """
    Puts OK/Cancel at the end of a page's body.
    """
    if "</body>" in html:
        return html.replace("</body>", MODAL_BUTTONS + "</body>", 1)
    return html + MODAL_BUTTONS

def exec_window(title: str, html: str, api: ModalApi, width: int = 900, height: int = 650) -> bool:
    """
    Shows a window and waits for OK (True), or Cancel / closing the window (False).

    Only call this from a pywebview API call (a worker thread). On the GUI thread it would deadlock.
    """
    api._window = webview.create_window(title, html=html, js_api=api, width=width, height=height)
    api._window.events.closed += lambda: api._done.set()
    api._done.wait()
    return api._accepted