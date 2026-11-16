"""
Preprocessing (results settings) for the web UI, e.g. the Diomni PCR plate map.
Implements the interface of backend.excel.writers.results_settings.QtSettingsUI.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pathlib import Path
import webview
from tools import render_details_template
from .modal import ModalApi, exec_window

# NOTE: OK validates the form first and stays open if it's invalid, as DefaultSettingsDialog.accept does.
SETTINGS_BUTTONS = """
<div style="padding: 10px 0; display: flex; gap: 8px; justify-content: flex-end;">
<button type="button" onclick="pywebview.api.cancel()">Cancel</button>
<button type="button" onclick="settingsOk(this)">OK</button>
</div>
<script>
async function settingsOk(button) {
    if (!validateForm()) return;
    button.disabled = true;
    await sendDataToBackend();
    pywebview.api.accept();
}
</script>
"""


class SettingsApi(ModalApi):
    """
    js_api for the settings window. update_settings matches DefaultSettingsDialog's Qt slot.
    """

    def __init__(self, settings):
        super().__init__()
        self._settings = settings

    def update_settings(self, settings) -> None:
        self._settings = settings


class WebSettingsUI(object):
    """
    The dialogs DefaultSettings needs, shown with pywebview. Use only from a pywebview API call.
    """

    def __init__(self, window):
        # NOTE: Main window, used as the owner of the save dialog.
        self._window = window

    def edit_settings(self, settings, template_name: str):
        api = SettingsApi(settings)
        html = render_details_template(template=template_name, settings=settings)
        html = html.replace("</body>", SETTINGS_BUTTONS + "</body>", 1) if "</body>" in html else html + SETTINGS_BUTTONS
        if not exec_window("Settings", html, api, width=900, height=600):
            return None
        return api._settings

    def choose_save_file(self, default_name: str, file_extension: str) -> Path | None:
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=f"{default_name}.{file_extension}",
            file_types=(f"{file_extension.upper()} files (*.{file_extension})",))
        if not result:
            return None
        return Path(result if isinstance(result, str) else result[0])