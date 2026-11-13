from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from backend.db.models import ResultsType
from backend.validators.pydant import PydProcedure, PydProcedureType
# from frontend.widgets import DefaultWebDialog
# from PyQt6.QtCore import pyqtSlot, QVariant
# from PyQt6.QtWidgets import QDialog
from datetime import date
from tools import render_details_template
from pathlib import Path
# from frontend.widgets.functions import select_save_file


class DefaultSettings(object):
    """
    Default object for setting up Results.

    Currently used only for creating a Diomni csv plate map.
    """
    
    def __init__(self, obj, resultstype: ResultsType, procedure: PydProcedure) -> None:
        """
        :param obj: Parent Qt gui.
        :param resultstype: The resultstype referenced in the ProcedureTypeResultsTypeAssociation.
        :type resultstype: ResultsType
        :param procedure: The procedure these results will be tagged to.
        :type procedure: PydProcedure
        """
        self.parent = obj
        self.settings = resultstype.load_saved_settings()
        self.procedure = procedure
        self.resultstype = resultstype
        self.proceduretype = self.procedure.proceduretype
        assert isinstance(self.proceduretype, PydProcedureType)
        template_name = f"{resultstype.name.replace(" ", "").lower()}_settings"
        from frontend.widgets.results_settings_dialog import DefaultSettingsDialog
        self.dlg = DefaultSettingsDialog(parent=obj, settings=self.settings, template_name=template_name)
        self.dlg.setModal(True) # Keeps it "modal" to the user
        self.dlg.finished.connect(self.handle_dialog_finished)
    
        # Use show() to keep the event loop and debugger active
        self.dlg.setModal(True)
        self.dlg.exec()
        # if self.dlg.exec():
        #     self.write_output()

    def render_file_path(self, file_extension: str = "xlsx") -> Path:
        """
        Renders a filepath specific to this type of result.

        :param file_extension: The extension type of the file to save. (E.g.: csv, xlsx, jpg). Defaults to xlsx.
        :type file_extension: str
        :returns: Path object.
        :rtype: Path
        """
        from frontend.widgets.functions import select_save_file
        fallback_name =  f"{self.resultstype.name} - {date.today().isoformat()}"
        match self.procedure.name:
            case dict():
                default_name = self.procedure.name.get("value", fallback_name)
            case str():
                default_name = self.procedure.name
            case _:
                default_name = fallback_name
        default_name = default_name.replace(":", "")
        return select_save_file(obj=self.parent, default_name=default_name, file_extension=file_extension)

    def handle_dialog_finished(self, result: QDialog.DialogCode):
        """
        Gets settings and writes to file if 'Okay' clicked in the QDialog .

        :param result: DialogCode of either Accepted, Cancelled or Rejected.
        """
        from PyQt6.QtWidgets import QDialog
        # Check if the result was QDialog.Accepted (usually 1)
        if result == QDialog.DialogCode.Accepted:
            self.settings = self.dlg.settings
            self.write_output()
        else:
            logger.info("Dialog Cancelled or Rejected")

    def write_output(self):
        """
        Write to output file.

        To be defined in child classes only.

        :raises: NotImplementedError("This method is meant to be overwritten by subclasses only.") 
        """
        raise NotImplementedError("This method is meant to be overwritten by subclasses only.")


from .diomni_pcr import *
