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
from backend.validators import PydReagent
from tools import check_if_app, Settings, Report
from .pop_ups import  AlertPop
from .misc import AddReagentForm, LogParser
import logging, webbrowser, sys
from datetime import date
from .submission_table import SubmissionsSheet
from .submission_widget import SubmissionFormContainer
from .controls_chart import ControlsViewer
from .kit_creator import KitAdder

logger = logging.getLogger(f'submissions.{__name__}')
logger.info("Hello, I am a logger")

class App(QMainWindow):

    def __init__(self, ctx: Settings = None):
        logger.debug(f"Initializing main window...")
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
        # self._controls_getter()
        self.show()
        self.statusBar().showMessage('Ready', 5000)
        
    def _createMenuBar(self):
        """
        adds items to menu bar
        """        
        logger.debug(f"Creating menu bar...")
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        # Creating menus using a title
        methodsMenu = menuBar.addMenu("&Methods")
        reportMenu = menuBar.addMenu("&Reports")
        maintenanceMenu = menuBar.addMenu("&Monthly")
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpAction)
        helpMenu.addAction(self.docsAction)
        fileMenu.addAction(self.importAction)
        fileMenu.addAction(self.importPCRAction)
        methodsMenu.addAction(self.searchLog)
        reportMenu.addAction(self.generateReportAction)
        maintenanceMenu.addAction(self.joinExtractionAction)
        maintenanceMenu.addAction(self.joinPCRAction)
        
    def _createToolBar(self):
        """
        adds items to toolbar
        """        
        logger.debug(f"Creating toolbar...")
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)
        toolbar.addAction(self.addKitAction)
        toolbar.addAction(self.addOrgAction)

    def _createActions(self):
        """
        creates actions
        """        
        logger.debug(f"Creating actions...")
        self.importAction = QAction("&Import Submission", self)
        self.importPCRAction = QAction("&Import PCR Results", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.generateReportAction = QAction("Make Report", self)
        self.addKitAction = QAction("Import Kit", self)
        self.addOrgAction = QAction("Import Org", self)
        self.joinExtractionAction = QAction("Link Extraction Logs")
        self.joinPCRAction = QAction("Link PCR Logs")
        self.helpAction = QAction("&About", self)
        self.docsAction = QAction("&Docs", self)
        self.searchLog = QAction("Search Log", self)

    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        logger.debug(f"Connecting actions...")
        self.importAction.triggered.connect(self.table_widget.formwidget.importSubmission)
        self.importPCRAction.triggered.connect(self.table_widget.formwidget.import_pcr_results)
        self.addReagentAction.triggered.connect(self.add_reagent)
        self.generateReportAction.triggered.connect(self.table_widget.sub_wid.generate_report)
        # self.addKitAction.triggered.connect(self.add_kit)
        # self.addOrgAction.triggered.connect(self.add_org)
        self.joinExtractionAction.triggered.connect(self.table_widget.sub_wid.link_extractions)
        self.joinPCRAction.triggered.connect(self.table_widget.sub_wid.link_pcr)
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)
        # self.constructFS.triggered.connect(self.construct_first_strand)
        # self.table_widget.formwidget.import_drag.connect(self.importSubmission)
        self.searchLog.triggered.connect(self.runSearch)

    def showAbout(self):
        """
        Show the 'about' message
        """        
        output = f"Version: {self.ctx.package.__version__}\n\nAuthor: {self.ctx.package.__author__['name']} - {self.ctx.package.__author__['email']}\n\nCopyright: {self.ctx.package.__copyright__}"
        about = AlertPop(message=output, status="information")
        about.exec()

    def openDocs(self):
        """
        Open the documentation html pages
        """        
        if check_if_app():
            url = Path(sys._MEIPASS).joinpath("files", "docs", "index.html")
        else:
            url = Path("docs\\build\\index.html").absolute()
        logger.debug(f"Attempting to open {url}")
        webbrowser.get('windows-default').open(f"file://{url.__str__()}")

    def result_reporter(self):
        """
        Report any anomolous results - if any - to the user

        Args:
            result (dict | None, optional): The result from a function. Defaults to None.
        """        
        logger.debug(f"Running results reporter for: {self.report.results}")
        if len(self.report.results) > 0:
            logger.debug(f"We've got some results!")
            for result in self.report.results:
                logger.debug(f"Showing result: {result}")
                if result != None:
                    alert = result.report()
                    if alert.exec():
                        pass
            self.report = Report()
        else:
            self.statusBar().showMessage("Action completed sucessfully.", 5000)
        
    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None, name:str|None=None):
        """
        Action to create new reagent in DB.

        Args:
            reagent_lot (str | None, optional): Parsed reagent from import form. Defaults to None.
            reagent_type (str | None, optional): Parsed reagent type from import form. Defaults to None.
            expiry (date | None, optional): Parsed reagent expiry data. Defaults to None.
            name (str | None, optional): Parsed reagent name. Defaults to None.

        Returns:
            models.Reagent: the constructed reagent object to add to submission
        """        
        report = Report()
        if isinstance(reagent_lot, bool):
            reagent_lot = ""
        # create form
        dlg = AddReagentForm(reagent_lot=reagent_lot, reagent_type=reagent_type, expiry=expiry, reagent_name=name)
        if dlg.exec():
            # extract form info
            info = dlg.parse_form()
            logger.debug(f"Reagent info: {info}")
            # create reagent object
            reagent = PydReagent(ctx=self.ctx, **info)
            # send reagent to db
            sqlobj, result = reagent.toSQL()
            sqlobj.save()
            report.add_result(result)
            self.result_reporter()
            return reagent

    def runSearch(self):
        dlg = LogParser(self)
        dlg.exec()

class AddSubForm(QWidget):
    
    def __init__(self, parent:QWidget):
        logger.debug(f"Initializating subform...")
        super(QWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        # Initialize tab screen
        self.tabs = QTabWidget()
        self.tab1 = QWidget()
        self.tab2 = QWidget()
        self.tab3 = QWidget()
        self.tabs.resize(300,200)
        # Add tabs
        self.tabs.addTab(self.tab1,"Submissions")
        self.tabs.addTab(self.tab2,"Controls")
        self.tabs.addTab(self.tab3, "Add Kit")
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
        adder = KitAdder(self)
        self.tab3.layout = QVBoxLayout(self)
        self.tab3.layout.addWidget(adder)
        self.tab3.setLayout(self.tab3.layout)
        # add tabs to main widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)