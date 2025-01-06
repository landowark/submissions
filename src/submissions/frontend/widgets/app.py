"""
Constructs main application.
"""
from pprint import pformat
from PyQt6.QtCore import qInstallMessageHandler
from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QScrollArea, QMainWindow,
    QToolBar
)
from PyQt6.QtGui import QAction
from pathlib import Path
from markdown import markdown
from __init__ import project_path
from backend import SubmissionType, Reagent, BasicSample, Organization
from tools import check_if_app, Settings, Report, jinja_template_loading, check_authorization, page_size, is_power_user
from .functions import select_save_file, select_open_file
# from datetime import date
from .pop_ups import HTMLPop, AlertPop
from .misc import Pagifier
import logging, webbrowser, sys, shutil
from .submission_table import SubmissionsSheet
from .submission_widget import SubmissionFormContainer
from .controls_chart import ControlsViewer
from .summary import Summary
from .turnaround import TurnaroundTime
from .omni_search import SearchBox
from .omni_manager import ManagerWindow

logger = logging.getLogger(f'submissions.{__name__}')


class App(QMainWindow):

    def __init__(self, ctx: Settings = None):
        super().__init__()
        qInstallMessageHandler(lambda x, y, z: None)
        self.ctx = ctx
        self.last_dir = ctx.directory_path
        self.report = Report()
        # NOTE: indicate version and connected database in title bar
        try:
            self.title = f"Submissions App (v{ctx.package.__version__}) - {ctx.database_path}/{ctx.database_name}"
        except (AttributeError, KeyError):
            self.title = f"Submissions App"
        # NOTE: set initial app position and size
        self.left = 0
        self.top = 0
        self.width = 1300
        self.height = 1000
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        self.page_size = page_size
        # NOTE: insert tabs into main app
        self.table_widget = AddSubForm(self)
        self.setCentralWidget(self.table_widget)
        # NOTE: run initial setups
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._connectActions()
        self.show()
        self.statusBar().showMessage('Ready', 5000)

    def _createMenuBar(self):
        """
        adds items to menu bar
        """
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        editMenu = menuBar.addMenu("&Edit")
        # NOTE: Creating menus using a title
        methodsMenu = menuBar.addMenu("&Search")
        maintenanceMenu = menuBar.addMenu("&Monthly")
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpAction)
        helpMenu.addAction(self.docsAction)
        helpMenu.addAction(self.githubAction)
        fileMenu.addAction(self.importAction)
        fileMenu.addAction(self.yamlExportAction)
        fileMenu.addAction(self.yamlImportAction)
        methodsMenu.addAction(self.searchSample)
        maintenanceMenu.addAction(self.joinExtractionAction)
        maintenanceMenu.addAction(self.joinPCRAction)
        editMenu.addAction(self.editReagentAction)
        editMenu.addAction(self.manageOrgsAction)
        if not is_power_user():
            editMenu.setEnabled(False)

    def _createToolBar(self):
        """
        adds items to toolbar
        """
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)

    def _createActions(self):
        """
        creates actions
        """
        self.importAction = QAction("&Import Submission", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.joinExtractionAction = QAction("Link Extraction Logs")
        self.joinPCRAction = QAction("Link PCR Logs")
        self.helpAction = QAction("&About", self)
        self.docsAction = QAction("&Docs", self)
        self.searchSample = QAction("Search Sample", self)
        self.githubAction = QAction("Github", self)
        self.yamlExportAction = QAction("Export Type Example", self)
        self.yamlImportAction = QAction("Import Type Template", self)
        self.editReagentAction = QAction("Edit Reagent", self)
        self.manageOrgsAction = QAction("Manage Clients", self)

    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.importAction.triggered.connect(self.table_widget.formwidget.importSubmission)
        self.addReagentAction.triggered.connect(self.table_widget.formwidget.new_add_reagent)
        self.joinExtractionAction.triggered.connect(self.table_widget.sub_wid.link_extractions)
        self.joinPCRAction.triggered.connect(self.table_widget.sub_wid.link_pcr)
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)
        self.searchSample.triggered.connect(self.runSampleSearch)
        self.githubAction.triggered.connect(self.openGithub)
        self.yamlExportAction.triggered.connect(self.export_ST_yaml)
        self.yamlImportAction.triggered.connect(self.import_ST_yaml)
        self.table_widget.pager.current_page.textChanged.connect(self.update_data)
        self.editReagentAction.triggered.connect(self.edit_reagent)
        self.manageOrgsAction.triggered.connect(self.manage_orgs)

    def showAbout(self):
        """
        Show the 'about' message
        """
        j_env = jinja_template_loading()
        template = j_env.get_template("project.html")
        html = template.render(info=self.ctx.package.__dict__)
        about = HTMLPop(html=html, title="About")
        about.exec()

    def openDocs(self):
        """
        Open the documentation html pages
        """
        if check_if_app():
            url = Path(sys._MEIPASS).joinpath("files", "docs", "index.html")
        else:
            url = Path("docs\\build\\index.html").absolute()
        webbrowser.get('windows-default').open(f"file://{url.__str__()}")

    def openGithub(self):
        """
        Opens the github page
        """
        url = "https://github.com/landowark/submissions"
        webbrowser.get('windows-default').open(url)

    def openInstructions(self):
        if check_if_app():
            url = Path(sys._MEIPASS).joinpath("files", "README.md")
        else:
            url = Path("README.md")
        with open(url, "r", encoding="utf-8") as f:
            html = markdown(f.read())
        instr = HTMLPop(html=html, title="Instructions")
        instr.exec()

    def runSampleSearch(self):
        """
        Create a search for samples.
        """
        dlg = SearchBox(self, object_type=BasicSample, extras=[])
        dlg.exec()

    def export_ST_yaml(self):
        """
        Copies submission type yaml to file system for editing and remport

        Returns:
            None
        """
        if check_if_app():
            yaml_path = Path(sys._MEIPASS).joinpath("files", "resources", "viral_culture.yml")
        else:
            yaml_path = project_path.joinpath("src", "submissions", "resources", "viral_culture.yml")
        fname = select_save_file(obj=self, default_name="Submission Type Template.yml", extension="yml")
        shutil.copyfile(yaml_path, fname)

    @check_authorization
    def edit_reagent(self, *args, **kwargs):
        dlg = SearchBox(parent=self, object_type=Reagent, extras=['role'])
        dlg.exec()

    @check_authorization
    def import_ST_yaml(self, *args, **kwargs):
        fname = select_open_file(obj=self, file_extension="yml")
        if not fname:
            logger.info(f"Import cancelled.")
            return
        ap = AlertPop(message="This function will proceed in the debug window.", status="Warning", owner=self)
        ap.exec()
        st = SubmissionType.import_from_json(filepath=fname)
        if st:
            # NOTE: Do not delete the print statement below.
            choice = input("Save the above submission type? [y/N]: ")
            if choice.lower() == "y":
                pass
            else:
                logger.warning("Save of submission type cancelled.")

    def update_data(self):
        self.table_widget.sub_wid.setData(page=self.table_widget.pager.page_anchor, page_size=page_size)

    def manage_orgs(self):
        dlg = ManagerWindow(parent=self, object_type=Organization, extras=[])
        if dlg.exec():
            new_org = dlg.parse_form()
            logger.debug(new_org.__dict__)

class AddSubForm(QWidget):

    def __init__(self, parent: QWidget):
        super(QWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        # NOTE: Initialize tab screen
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tab4 = QWidget()
        self.tab5 = QWidget()
        self.tabs.resize(300, 200)
        # NOTE: Add tabs
        self.tabs.addTab(self.tab1, "Submissions")
        self.tabs.addTab(self.tab2, "Irida Controls")
        self.tabs.addTab(self.tab3, "PCR Controls")
        self.tabs.addTab(self.tab4, "Cost Report")
        self.tabs.addTab(self.tab5, "Turnaround Times")
        # NOTE: Create submission adder form
        self.formwidget = SubmissionFormContainer(self)
        self.formlayout = QVBoxLayout(self)
        self.formwidget.setLayout(self.formlayout)
        self.formwidget.setFixedWidth(300)
        # NOTE: Make scrollable interior for form
        self.interior = QScrollArea(self.tab1)
        self.interior.setWidgetResizable(True)
        self.interior.setFixedWidth(325)
        self.interior.setWidget(self.formwidget)
        # NOTE: Create sheet to hold existing submissions
        self.sheetwidget = QWidget(self)
        self.sheetlayout = QVBoxLayout(self)
        self.sheetwidget.setLayout(self.sheetlayout)
        self.sub_wid = SubmissionsSheet(parent=parent)
        self.pager = Pagifier(page_max=self.sub_wid.total_count / page_size)
        self.sheetlayout.addWidget(self.sub_wid)
        self.sheetlayout.addWidget(self.pager)
        # NOTE: Create layout of first tab to hold form and sheet
        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        self.tab1.layout.addWidget(self.interior)
        self.tab1.layout.addWidget(self.sheetwidget)
        self.tab2.layout = QVBoxLayout(self)
        self.irida_viewer = ControlsViewer(self, archetype="Irida Control")
        self.tab2.layout.addWidget(self.irida_viewer)
        self.tab2.setLayout(self.tab2.layout)
        self.tab3.layout = QVBoxLayout(self)
        self.pcr_viewer = ControlsViewer(self, archetype="PCR Control")
        self.tab3.layout.addWidget(self.pcr_viewer)
        self.tab3.setLayout(self.tab3.layout)
        summary_report = Summary(self)
        self.tab4.layout = QVBoxLayout(self)
        self.tab4.layout.addWidget(summary_report)
        self.tab4.setLayout(self.tab4.layout)
        turnaround = TurnaroundTime(self)
        self.tab5.layout = QVBoxLayout(self)
        self.tab5.layout.addWidget(turnaround)
        self.tab5.setLayout(self.tab5.layout)
        # NOTE: add tabs to main widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
