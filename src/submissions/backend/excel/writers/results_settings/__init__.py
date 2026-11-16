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


class QtSettingsUI(object):
    """
    The dialogs DefaultSettings needs, shown with Qt. The web UI passes webui.preprocessing.WebSettingsUI instead.
    """

    def __init__(self, parent=None):
        self.parent = parent

    def edit_settings(self, settings, template_name: str):
        """
        :return: The edited settings, or None if cancelled.
        """
        from frontend.widgets.results_settings_dialog import DefaultSettingsDialog
        dlg = DefaultSettingsDialog(parent=self.parent, settings=settings, template_name=template_name)
        dlg.setModal(True)
        if dlg.exec():
            return dlg.settings
        return None

    def choose_save_file(self, default_name: str, file_extension: str):
        from frontend.widgets.functions import select_save_file
        return select_save_file(obj=self.parent, default_name=default_name, file_extension=file_extension)


class DefaultSettings(object):
    """
    Default object for setting up Results.

    Currently used only for creating a Diomni csv plate map.
    """
    
    def __init__(self, obj, resultstype: ResultsType, procedure: PydProcedure, ui=None) -> None:
        """
        :param obj: Parent Qt gui.
        :param resultstype: The resultstype referenced in the ProcedureTypeResultsTypeAssociation.
        :type resultstype: ResultsType
        :param procedure: The procedure these results will be tagged to.
        :type procedure: PydProcedure
        """
        self.parent = obj
        self.ui = ui or QtSettingsUI(parent=obj)
        self.settings = resultstype.load_saved_settings()
        self.procedure = procedure
        self.resultstype = resultstype
        self.proceduretype = self.procedure.proceduretype
        # NOTE: Set by write_output once a file is written, so callers can tell a save from a cancel.
        self.output_path = None
        assert isinstance(self.proceduretype, PydProcedureType)
        template_name = f"{resultstype.name.replace(" ", "").lower()}_settings"
        settings = self.ui.edit_settings(settings=self.settings, template_name=template_name)
        if settings is None:
            logger.info("Dialog Cancelled or Rejected")
            return
        self.settings = settings
        self.write_output()

    def render_file_path(self, file_extension: str = "xlsx") -> Path:
        """
        Renders a filepath specific to this type of result.

        :param file_extension: The extension type of the file to save. (E.g.: csv, xlsx, jpg). Defaults to xlsx.
        :type file_extension: str
        :returns: Path object.
        :rtype: Path
        """
        # from frontend.widgets.functions import select_save_file
        fallback_name =  f"{self.resultstype.name} - {date.today().isoformat()}"
        match self.procedure.name:
            case dict():
                default_name = self.procedure.name.get("value", fallback_name)
            case str():
                default_name = self.procedure.name
            case _:
                default_name = fallback_name
        default_name = default_name.replace(":", "")
        # return select_save_file(obj=self.parent, default_name=default_name, file_extension=file_extension)
        return self.ui.choose_save_file(default_name=default_name, file_extension=file_extension)

    # def handle_dialog_finished(self, result: QDialog.DialogCode):
    #     """
    #     Gets settings and writes to file if 'Okay' clicked in the QDialog .

    #     :param result: DialogCode of either Accepted, Cancelled or Rejected.
    #     """
    #     from PyQt6.QtWidgets import QDialog
    #     # Check if the result was QDialog.Accepted (usually 1)
    #     if result == QDialog.DialogCode.Accepted:
    #         self.settings = self.dlg.settings
    #         self.write_output()
    #     else:
    #         logger.info("Dialog Cancelled or Rejected")

    def write_output(self):
        """
        Write to output file.

        To be defined in child classes only.

        :raises: NotImplementedError("This method is meant to be overwritten by subclasses only.") 
        """
        raise NotImplementedError("This method is meant to be overwritten by subclasses only.")


from .diomni_pcr import *
