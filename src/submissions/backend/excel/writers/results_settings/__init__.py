from backend.db.models import ResultsType
from backend.validators.pydant import PydProcedure
from frontend.widgets import DefaultWebDialog
from PyQt6.QtCore import pyqtSlot, QVariant
from tools import render_details_template
import logging
from pprint import pformat

logger = logging.getLogger(f"submissions.{__name__}")


class DefaultSettings(object):
    
    def __init__(self, parent, resultstype: ResultsType, procedure: PydProcedure) -> None:
        self.settings = resultstype.saved_settings
        self.procedure = procedure
        template_name = f"{resultstype.name.replace(" ", "").lower()}_settings"
        self.dlg = DefaultSettingsDialog(parent=parent, settings=self.settings, template_name=template_name)
        if self.dlg.exec():
            self.settings = self.dlg.settings
            self.write_output()

    def write_output(self):
        raise NotImplementedError("This method is meant to be overwritten by subclasses only.")


class DefaultSettingsDialog(DefaultWebDialog):

    def __init__(self, parent, settings:dict, template_name: str) -> None:
        super().__init__(parent)
        self.settings = settings
        logger.debug(f"Settings:\n{pformat(self.settings)}")
        self.template_name = template_name
        self.set_html()

    def set_html(self):
        html = render_details_template(template=self.template_name, settings=self.settings)
        with open("test.html", "w") as f:
            f.write(html)
        self.webview.setHtml(html)

    @pyqtSlot(QVariant)
    def update_settings(self, settings:dict):
        logger.debug(pformat(settings))
        self.settings = settings

from .diomni_pcr import DiomniPCRSettings