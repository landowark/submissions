"""
Contains all custom generated PyQT6 derivative widgets.
"""
from PyQt6.QtCore import QAbstractTableModel, Qt
from PyQt6.QtWebEngineCore import QWebEnginePage
import logging

logger = logging.getLogger("submissions.frontend.widgets")


class CustomWebEnginePage(QWebEnginePage):

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # You can customize the output format here
        # Use logger so messages follow the app logging configuration
        try:
            logger.debug(f"JS Console ({lineNumber}) [{level}]: {message}")
        except Exception:
            print(f"JS Console ({lineNumber}) [{level}]: {message}")

    # Note: do not override `renderProcessTerminated` here because in PyQt6
    # it may be exposed as a signal; instead we connect to the signal from
    # the code that creates the page (ProcedureCreation) to log terminations.

    # def acceptNavigationRequest(self, url, _type, isMainFrame):
    #     print(f"Navigation request to: {url.toString()}")
    #     return super().acceptNavigationRequest(url, _type, isMainFrame)
    
    # def navigationRequested(self, url, _type, isMainFrame):
    #     print(f"Navigation requested to: {url.toString()}")
    #     return super().navigationRequested(url, _type, isMainFrame)

class pandasModel(QAbstractTableModel):
    """
    pandas model for inserting summary sheet into gui
    NOTE: Copied from Stack Overflow. I have no idea how it actually works.
    """

    def __init__(self, data) -> None:
        QAbstractTableModel.__init__(self)
        self._data = data

    def rowCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of rows in data
        """
        return self._data.shape[0]

    def columnCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of columns in data
        """
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> str | None:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._data.columns[col]
        return None


from .app import App
from .concentrations import Concentrations
from .controls_chart import ControlsViewer
from .date_type_picker import DateTypePicker
from .equipment_usage import EquipmentUsage, RoleComboBox
from .excel_sheet_selector import ExcelSheetSelector
from .functions import select_open_file, select_save_file, save_pdf
from .gel_checker import GelBox, ControlsForm
from .info_tab import InfoPane
from .misc import StartEndDatePicker, CheckableComboBox, Pagifier
from .omni_search import SearchBox, SearchResults, FieldSearch
from .pop_ups import QuestionAsker, AlertPop, HTMLPop, ObjectSelector
from .procedure_creation import ProcedureCreation
from .sample_checker import SampleChecker
from .submission_details import SubmissionDetails, SubmissionComment
from .submission_table import SubmissionsTree, ClientSubmissionRunModel
from .submission_widget import MyQComboBox, MyQDateEdit, SubmissionFormContainer, SubmissionFormWidget, ClientSubmissionFormWidget
from .summary import Summary
from .turnaround import TurnaroundMaker
