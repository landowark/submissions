from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from PyQt6.QtCore import pyqtSlot, QVariant
from tools import render_details_template
from . import DefaultWebDialog

class DefaultSettingsDialog(DefaultWebDialog):
    """
    Derived from DefaultWebDialog to handle settings of results.

    Currently only used for making DiomniPCR csv plate maps.
    """

    def __init__(self, parent, settings:dict, template_name: str) -> None:
        """
        :param parent: Parent Qt gui widget
        :param settings: Incoming settings
        :type settings: dict
        :param template_name: Template to use in rendering.
        :type template_name: str
        """
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.template_name = template_name
        self.set_html()

    def accept(self):
        """
        Action to run when dialog is accepted (Okay).

        Callback is self._handle_validation_result
        """
        # Ask JavaScript if the form is valid
        self.webview.page().runJavaScript("validateForm();", self._handle_validation_result)

    def _handle_validation_result(self, is_valid: bool):
        """
        Checks validation of results form.

        :param is_valid: if the javascript validates the form.
        :type is_valid: bool
        """
        if is_valid:
            # If valid, proceed with the normal QDialog accept process
            super().accept()
        else:
            # If invalid, the browser will already be showing validation bubbles
            # We do nothing here, which keeps the dialog open
            raise ValueError(f"We need a target name.")

    def set_html(self):
        """
        Sets the html of the dialog as a rendered template.
        """
        html = render_details_template(template=self.template_name, settings=self.settings)
        self.webview.setHtml(html)

    @pyqtSlot(QVariant)
    def update_settings(self, settings:dict):
        """
        Updates the settings dict based on form output.

        :param settings: Incoming settings.
        :type settings: dict
        """
        self.settings = settings