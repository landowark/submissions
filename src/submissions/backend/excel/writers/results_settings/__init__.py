from backend.db.models import ResultsType
from backend.validators.pydant import PydProcedure, PydProcedureType
from frontend.widgets import DefaultWebDialog
from PyQt6.QtCore import pyqtSlot, QVariant
from PyQt6.QtWidgets import QDialog
from tools import render_details_template
import logging
from pprint import pformat

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultSettings(object):
    
    def __init__(self, parent, resultstype: ResultsType, procedure: PydProcedure) -> None:
        self.parent = parent
        self.settings = resultstype.saved_settings
        self.procedure = procedure
        self.proceduretype = self.procedure.proceduretype
        assert isinstance(self.proceduretype, PydProcedureType)
        template_name = f"{resultstype.name.replace(" ", "").lower()}_settings"
        
        self.dlg = DefaultSettingsDialog(parent=parent, settings=self.settings, template_name=template_name)
        self.dlg.setModal(True) # Keeps it "modal" to the user
        self.dlg.finished.connect(self.handle_dialog_finished)
    
        # Use show() to keep the event loop and debugger active
        self.dlg.setModal(True)
        self.dlg.open()

    def handle_dialog_finished(self, result):
        # Check if the result was QDialog.Accepted (usually 1)
        if result == QDialog.DialogCode.Accepted:
            self.settings = self.dlg.settings
            self.write_output()
        else:
            logger.info("Dialog Cancelled or Rejected")

    def write_output(self):
        raise NotImplementedError("This method is meant to be overwritten by subclasses only.")


class DefaultSettingsDialog(DefaultWebDialog):

    def __init__(self, parent, settings:dict, template_name: str) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.template_name = template_name
        self.set_html()

    def accept(self):
        # Ask JavaScript if the form is valid
        self.webview.page().runJavaScript("validateForm();", self._handle_validation_result)

    def _handle_validation_result(self, is_valid):
        if is_valid:
            # If valid, proceed with the normal QDialog accept process
            super().accept()
        else:
            # If invalid, the browser will already be showing validation bubbles
            # We do nothing here, which keeps the dialog open
            raise ValueError(f"We need a target name.")

    def set_html(self):
        html = render_details_template(template=self.template_name, settings=self.settings)
        self.webview.setHtml(html)

    @pyqtSlot(QVariant)
    def update_settings(self, settings:dict):
        self.settings = settings

from .diomni_pcr import *