"""
Contains all custom generated PyQT6 derivative widgets.
"""
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import QAbstractTableModel, Qt
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QGridLayout, QDialogButtonBox
import logging, os

from tools import get_application_from_parent

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

class DefaultWebDialog(QDialog):

    def __init__(self, parent) -> None:
        super().__init__(parent)
        if 'QTWEBENGINE_REMOTE_DEBUGGING' not in os.environ:
            os.environ['QTWEBENGINE_REMOTE_DEBUGGING'] = '9222'
            logger.info('Enabled QTWEBENGINE_REMOTE_DEBUGGING=9222 for remote inspection')
        self.app = get_application_from_parent(parent)
        # Ensure remote debugging is enabled before the WebEngine is initialised.
        # This exposes the remote inspector on localhost:9222 so you can open
        # http://localhost:9222/ in a desktop browser and inspect console/network errors.
        self.webview = QWebEngineView(parent=self)
        self.webview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.webview.setMinimumSize(1200, 800)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
        # NOTE: Decide if exporting should be allowed.
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
        self.setLayout(self.layout)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.page().setWebChannel(self.channel)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, 11, 1, 1, 1)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint)

    
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


from .app import *
from .concentration_viewer import *
from .controls_chart import *
from .date_type_picker import *
from .excel_sheet_selector import *
from .functions import *
from .gel_checker import *
from .info_tab import *
from .kraken_viewer import *
from .misc import *
from .omni_manager_pydant import *
from .omni_search import *
from .pcr_viewer import *
from .pop_ups import *
from .procedure_creation import *
from .results_sample_matcher import *
from .sample_checker import *
from .submission_details import *
from .submission_table import *
from .submission_widget import *
from .summary import *
from .turnaround import *

__all__ = ["CustomWebEnginePage", "DefaultWebDialog", "pandasModel", 
           "App", "AddSubForm", 
           "ConcentrationViewer",
           "ControlsViewer", 
           "DateTypePicker", 
           "ExcelSheetSelector", 
           "select_open_file", "select_save_file", "save_pdf",
           "GelBox", "ControlsForm", 
           "InfoPane", "PosNegPane",
           "KrakenViewer", 
           "StartEndDatePicker", "CheckableComboBox", "Pagifier",
           "OmniManager", 
           "SearchBox", "SearchResults", "FieldSearch", 
           "PCRViewer", 
           "QuestionAsker", "AlertPop", "HTMLPop", "ObjectSelector", 
           "ProcedureCreation", 
           "ResultsSampleMatcher", 
           "SampleChecker", 
           "SubmissionDetails", "SubmissionComment",
           "SubmissionsTree", "TreeItem", "ClientSubmissionRunModel",
           "MyQComboBox", "MyQDateEdit", "MyQSpinBox", "MyQDoubleSpinBox", "SubmissionFormContainer", "SubmissionFormWidget", "ClientSubmissionFormWidget",
           "Summary",
            "TurnaroundTime"
           ]