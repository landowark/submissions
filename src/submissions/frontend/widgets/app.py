'''
Constructs main application.
'''
from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QScrollArea, QMainWindow, 
    QToolBar
)
from PyQt6.QtGui import QAction
from pathlib import Path
from tools import check_if_app, Settings, Report
from datetime import date
from .pop_ups import  AlertPop
from .misc import LogParser
import logging, webbrowser, sys, shutil
from .submission_table import SubmissionsSheet
from .submission_widget import SubmissionFormContainer
from .controls_chart import ControlsViewer
from .kit_creator import KitAdder
from .submission_type_creator import SubmissionTypeAdder
from .sample_search import SearchBox

logger = logging.getLogger(f'submissions.{__name__}')
logger.info("Hello, I am a logger")

class App(QMainWindow):

    def __init__(self, ctx: Settings = None):
        # logger.debug(f"Initializing main window...")
        super().__init__()
        self.ctx = ctx
        self.last_dir = ctx.directory_path
        self.report = Report()
        # indicate version and connected database in title bar
        try:
            self.title = f"Submissions App (v{ctx.package.__version__}) - {ctx.database_path}"
        except (AttributeError, KeyError):
            self.title = f"Submissions App"
        # set initial app position and size
        self.left = 0
        self.top = 0
        self.width = 1300
        self.height = 1000
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        # insert tabs into main app
        self.table_widget = AddSubForm(self)
        self.setCentralWidget(self.table_widget)
        # run initial setups
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._connectActions()
        self.show()
        self.statusBar().showMessage('Ready', 5000)
        self.backup_database()
        
    def _createMenuBar(self):
        """
        adds items to menu bar
        """        
        # logger.debug(f"Creating menu bar...")
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        # NOTE: Creating menus using a title
        methodsMenu = menuBar.addMenu("&Methods")
        reportMenu = menuBar.addMenu("&Reports")
        maintenanceMenu = menuBar.addMenu("&Monthly")
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpAction)
        helpMenu.addAction(self.docsAction)
        helpMenu.addAction(self.githubAction)
        fileMenu.addAction(self.importAction)
        methodsMenu.addAction(self.searchLog)
        methodsMenu.addAction(self.searchSample)
        reportMenu.addAction(self.generateReportAction)
        maintenanceMenu.addAction(self.joinExtractionAction)
        maintenanceMenu.addAction(self.joinPCRAction)
        
    def _createToolBar(self):
        """
        adds items to toolbar
        """        
        # logger.debug(f"Creating toolbar...")
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)
        toolbar.addAction(self.addKitAction)
        toolbar.addAction(self.addOrgAction)

    def _createActions(self):
        """
        creates actions
        """        
        # logger.debug(f"Creating actions...")
        self.importAction = QAction("&Import Submission", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.generateReportAction = QAction("Make Report", self)
        self.addKitAction = QAction("Import Kit", self)
        self.addOrgAction = QAction("Import Org", self)
        self.joinExtractionAction = QAction("Link Extraction Logs")
        self.joinPCRAction = QAction("Link PCR Logs")
        self.helpAction = QAction("&About", self)
        self.docsAction = QAction("&Docs", self)
        self.searchLog = QAction("Search Log", self)
        self.searchSample = QAction("Search Sample", self)
        self.githubAction = QAction("Github", self)

    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        # logger.debug(f"Connecting actions...")
        self.importAction.triggered.connect(self.table_widget.formwidget.importSubmission)
        self.addReagentAction.triggered.connect(self.table_widget.formwidget.add_reagent)
        self.generateReportAction.triggered.connect(self.table_widget.sub_wid.generate_report)
        self.joinExtractionAction.triggered.connect(self.table_widget.sub_wid.link_extractions)
        self.joinPCRAction.triggered.connect(self.table_widget.sub_wid.link_pcr)
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)
        self.searchLog.triggered.connect(self.runSearch)
        self.searchSample.triggered.connect(self.runSampleSearch)
        self.githubAction.triggered.connect(self.openGithub)

    def showAbout(self):
        """
        Show the 'about' message
        """        
        output = f"Version: {self.ctx.package.__version__}\n\nAuthor: {self.ctx.package.__author__['name']} - {self.ctx.package.__author__['email']}\n\nCopyright: {self.ctx.package.__copyright__}"
        about = AlertPop(message=output, status="Information")
        about.exec()

    def openDocs(self):
        """
        Open the documentation html pages
        """        
        if check_if_app():
            url = Path(sys._MEIPASS).joinpath("files", "docs", "index.html")
        else:
            url = Path("docs\\build\\index.html").absolute()
        # logger.debug(f"Attempting to open {url}")
        webbrowser.get('windows-default').open(f"file://{url.__str__()}")

    def openGithub(self):
        """
        Opens the instructions html page
        """
        url = "https://github.com/landowark/submissions"
        webbrowser.get('windows-default').open(url)


    def result_reporter(self):
        """
        Report any anomolous results - if any - to the user

        Args:
            result (dict | None, optional): The result from a function. Defaults to None.
        """        
        # logger.debug(f"Running results reporter for: {self.report.results}")
        if len(self.report.results) > 0:
            # logger.debug(f"We've got some results!")
            for result in self.report.results:
                # logger.debug(f"Showing result: {result}")
                if result is not None:
                    alert = result.report()
                    if alert.exec():
                        pass
            self.report = Report()
        else:
            self.statusBar().showMessage("Action completed sucessfully.", 5000)

    def runSearch(self):
        dlg = LogParser(self)
        dlg.exec()

    def runSampleSearch(self):
        """
        Create a search for samples.
        """        
        dlg = SearchBox(self)
        dlg.exec()

    def backup_database(self):
        """
        Copies the database into the backup directory the first time it is opened every month.
        """        
        month = date.today().strftime("%Y-%m")
        # logger.debug(f"Here is the db directory: {self.ctx.database_path}")
        # logger.debug(f"Here is the backup directory: {self.ctx.backup_path}")
        current_month_bak = Path(self.ctx.backup_path).joinpath(f"submissions_backup-{month}").resolve().with_suffix(".db")
        if not current_month_bak.exists() and "demo" not in self.ctx.database_path.__str__():
            logger.info("No backup found for this month, backing up database.")
            shutil.copyfile(self.ctx.database_path, current_month_bak)


class AddSubForm(QWidget):
    
    def __init__(self, parent:QWidget):
        # logger.debug(f"Initializating subform...")
        super(QWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        # Initialize tab screen
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tab4 = QWidget()
        self.tabs.resize(300,200)
        # Add tabs
        self.tabs.addTab(self.tab1,"Submissions")
        self.tabs.addTab(self.tab2,"Controls")
        self.tabs.addTab(self.tab3, "Add SubmissionType")
        self.tabs.addTab(self.tab4, "Add Kit")
        # Create submission adder form
        self.formwidget = SubmissionFormContainer(self)
        self.formlayout = QVBoxLayout(self)
        self.formwidget.setLayout(self.formlayout)
        self.formwidget.setFixedWidth(300)
        # Make scrollable interior for form
        self.interior = QScrollArea(self.tab1)
        self.interior.setWidgetResizable(True)
        self.interior.setFixedWidth(325)
        self.interior.setWidget(self.formwidget)
        # Create sheet to hold existing submissions
        self.sheetwidget = QWidget(self)
        self.sheetlayout = QVBoxLayout(self)
        self.sheetwidget.setLayout(self.sheetlayout)
        self.sub_wid = SubmissionsSheet(parent=parent)
        self.sheetlayout.addWidget(self.sub_wid)
        # Create layout of first tab to hold form and sheet
        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        self.tab1.layout.addWidget(self.interior)
        self.tab1.layout.addWidget(self.sheetwidget)
        self.tab2.layout = QVBoxLayout(self)
        self.controls_viewer = ControlsViewer(self)
        self.tab2.layout.addWidget(self.controls_viewer)
        self.tab2.setLayout(self.tab2.layout)
        # create custom widget to add new tabs
        ST_adder = SubmissionTypeAdder(self)
        self.tab3.layout = QVBoxLayout(self)
        self.tab3.layout.addWidget(ST_adder)
        self.tab3.setLayout(self.tab3.layout)
        kit_adder = KitAdder(self)
        self.tab4.layout = QVBoxLayout(self)
        self.tab4.layout.addWidget(kit_adder)
        self.tab4.setLayout(self.tab4.layout)
        # add tabs to main widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
