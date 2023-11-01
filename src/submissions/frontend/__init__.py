'''
Constructs main application.
'''
from pprint import pformat
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QComboBox, QHBoxLayout,
    QScrollArea, QLineEdit, QDateEdit
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWebEngineWidgets import QWebEngineView
from pathlib import Path
from backend.db.functions import (
    lookup_control_types, lookup_modes
)
from backend.validators import PydSubmission, PydReagent
from tools import check_if_app, Settings
from frontend.custom_widgets import SubmissionsSheet, AlertPop, AddReagentForm, KitAdder, ControlsDatePicker, ImportReagent, ReagentFormWidget
import logging
from datetime import date
import webbrowser
from pathlib import Path

logger = logging.getLogger(f'submissions.{__name__}')
logger.info("Hello, I am a logger")

class App(QMainWindow):

    def __init__(self, ctx: Settings = {}):
        logger.debug(f"Initializing main window...")
        super().__init__()
        self.ctx = ctx
        self.last_dir = ctx.directory_path
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
        self._controls_getter()
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
        methodsMenu.addAction(self.constructFS)
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
        self.constructFS = QAction("Make First Strand", self)


    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        logger.debug(f"Connecting actions...")
        self.importAction.triggered.connect(self.importSubmission)
        self.importPCRAction.triggered.connect(self.importPCRResults)
        self.addReagentAction.triggered.connect(self.add_reagent)
        self.generateReportAction.triggered.connect(self.generateReport)
        self.addKitAction.triggered.connect(self.add_kit)
        self.addOrgAction.triggered.connect(self.add_org)
        self.table_widget.control_typer.currentIndexChanged.connect(self._controls_getter)
        self.table_widget.mode_typer.currentIndexChanged.connect(self._controls_getter)
        self.table_widget.datepicker.start_date.dateChanged.connect(self._controls_getter)
        self.table_widget.datepicker.end_date.dateChanged.connect(self._controls_getter)
        self.joinExtractionAction.triggered.connect(self.linkExtractions)
        self.joinPCRAction.triggered.connect(self.linkPCR)
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)
        self.constructFS.triggered.connect(self.construct_first_strand)
        self.table_widget.formwidget.import_drag.connect(self.importSubmission)

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

    def result_reporter(self, result:dict|None=None):
    # def result_reporter(self, result:TypedDict[]|None=None):
        """
        Report any anomolous results - if any - to the user

        Args:
            result (dict | None, optional): The result from a function. Defaults to None.
        """        
        logger.info(f"We got the result: {result}")
        if result != None:
            msg = AlertPop(message=result['message'], status=result['status'])
            msg.exec()
        else:
            self.statusBar().showMessage("Action completed sucessfully.", 5000)

    def importSubmission(self, fname:Path|None=None):
        """
        import submission from excel sheet into form
        """        
        from .main_window_functions import import_submission_function
        self.raise_()
        self.activateWindow()
        self, result = import_submission_function(self, fname)
        logger.debug(f"Import result: {result}")
        self.result_reporter(result)

    def kit_reload(self):
        """
        Removes all reagents from form before running kit integrity completion.
        """        
        from .main_window_functions import kit_reload_function
        self, result = kit_reload_function(self)
        self.result_reporter(result)

    def kit_integrity_completion(self):
        """
        Performs check of imported reagents
        NOTE: this will not change self.reagents which should be fine
        since it's only used when looking up 
        """        
        from .main_window_functions import kit_integrity_completion_function
        self, result = kit_integrity_completion_function(self)
        self.result_reporter(result)

    def submit_new_sample(self):
        """
        Attempt to add sample to database when 'submit' button clicked
        """        
        from .main_window_functions import submit_new_sample_function
        self, result = submit_new_sample_function(self)
        self.result_reporter(result)

    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None, name:str|None=None):
        """
        Action to create new reagent in DB.

        Args:
            reagent_lot (str | None, optional): Parsed reagent from import form. Defaults to None.
            reagent_type (str | None, optional): Parsed reagent type from import form. Defaults to None.

        Returns:
            models.Reagent: the constructed reagent object to add to submission
        """        
        if isinstance(reagent_lot, bool):
            reagent_lot = ""
        # create form
        dlg = AddReagentForm(ctx=self.ctx, reagent_lot=reagent_lot, reagent_type=reagent_type, expiry=expiry, reagent_name=name)
        if dlg.exec():
            # extract form info
            # info = extract_form_info(dlg)
            info = dlg.parse_form()
            logger.debug(f"Reagent info: {info}")
            # create reagent object
            # reagent = construct_reagent(ctx=self.ctx, info_dict=info)
            reagent = PydReagent(ctx=self.ctx, **info)
            # send reagent to db
            # store_reagent(ctx=self.ctx, reagent=reagent)
            sqlobj, result = reagent.toSQL()
            sqlobj.save(ctx=self.ctx)
            # result = store_object(ctx=self.ctx, object=reagent.toSQL()[0])
            self.result_reporter(result=result)
            return reagent

    def generateReport(self):
        """
        Action to create a summary of sheet data per client
        """
        from .main_window_functions import generate_report_function
        self, result = generate_report_function(self)
        self.result_reporter(result)

    def add_kit(self):
        """
        Constructs new kit from yaml and adds to DB.
        """
        from .main_window_functions import add_kit_function
        self, result = add_kit_function(self)
        self.result_reporter(result)

    def add_org(self):
        """
        Constructs new kit from yaml and adds to DB.
        """
        from .main_window_functions import add_org_function
        self, result = add_org_function(self)
        self.result_reporter(result)

    def _controls_getter(self):
        """
        Lookup controls from database and send to chartmaker
        """    
        from .main_window_functions import controls_getter_function
        self, result = controls_getter_function(self)
        self.result_reporter(result)    
        
    def _chart_maker(self):
        """
        Creates plotly charts for webview
        """   
        from .main_window_functions import chart_maker_function
        self, result = chart_maker_function(self)     
        self.result_reporter(result)

    def linkControls(self):
        """
        Adds controls pulled from irida to relevant submissions
        NOTE: Depreciated due to improvements in controls scraper.
        """    
        from .main_window_functions import link_controls_function
        self, result = link_controls_function(self)
        self.result_reporter(result)  

    def linkExtractions(self):
        """
        Links extraction logs from .csv files to relevant submissions.
        """     
        from .main_window_functions import link_extractions_function
        self, result = link_extractions_function(self)
        self.result_reporter(result)

    def linkPCR(self):
        """
        Links PCR logs from .csv files to relevant submissions.
        """        
        from .main_window_functions import link_pcr_function
        self, result = link_pcr_function(self)
        self.result_reporter(result)

    def importPCRResults(self):
        """
        Imports results exported from Design and Analysis .eds files
        """        
        from .main_window_functions import import_pcr_results_function
        self, result = import_pcr_results_function(self)
        self.result_reporter(result)

    def construct_first_strand(self):
        """
        Converts first strand excel sheet to Biomek CSV
        """        
        from .main_window_functions import construct_first_strand_function
        self, result = construct_first_strand_function(self)
        self.result_reporter(result)

    def scrape_reagents(self, *args, **kwargs):
        from .main_window_functions import scrape_reagents
        logger.debug(f"Args: {args}")
        logger.debug(F"kwargs: {kwargs}")
        self, result = scrape_reagents(self, args[0])
        self.kit_integrity_completion()
        self.result_reporter(result)

class AddSubForm(QWidget):
    
    def __init__(self, parent:QWidget):
        logger.debug(f"Initializating subform...")
        super(QWidget, self).__init__(parent)
        self.layout = QVBoxLayout(self)
        self.parent = parent
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
        self.sub_wid = SubmissionsSheet(parent.ctx)
        self.sheetlayout.addWidget(self.sub_wid)
        # Create layout of first tab to hold form and sheet
        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        self.tab1.layout.addWidget(self.interior)
        self.tab1.layout.addWidget(self.sheetwidget)
        # create widgets for tab 2
        self.datepicker = ControlsDatePicker()
        self.webengineview = QWebEngineView()
        # set tab2 layout
        self.tab2.layout = QVBoxLayout(self)
        self.control_typer = QComboBox()
        # fetch types of controls 
        # con_types = get_all_Control_Types_names(ctx=parent.ctx)
        con_types = [item.name for item in lookup_control_types(ctx=parent.ctx)]
        self.control_typer.addItems(con_types)
        # create custom widget to get types of analysis
        self.mode_typer = QComboBox()
        # mode_types = get_all_available_modes(ctx=parent.ctx)
        mode_types = lookup_modes(ctx=parent.ctx)
        self.mode_typer.addItems(mode_types)
        # create custom widget to get subtypes of analysis
        self.sub_typer = QComboBox()
        self.sub_typer.setEnabled(False)
        # add widgets to tab2 layout
        self.tab2.layout.addWidget(self.datepicker)
        self.tab2.layout.addWidget(self.control_typer)
        self.tab2.layout.addWidget(self.mode_typer)
        self.tab2.layout.addWidget(self.sub_typer)
        self.tab2.layout.addWidget(self.webengineview)
        self.tab2.setLayout(self.tab2.layout)
        # create custom widget to add new tabs
        adder = KitAdder(parent_ctx=parent.ctx)
        self.tab3.layout = QVBoxLayout(self)
        self.tab3.layout.addWidget(adder)
        self.tab3.setLayout(self.tab3.layout)
        # add tabs to main widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

class SubmissionFormContainer(QWidget):

    import_drag = pyqtSignal(Path)

    def __init__(self, parent: QWidget) -> None:
        logger.debug(f"Setting form widget...")
        super().__init__(parent)
        # self.parent = parent
        
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        fname = Path([u.toLocalFile() for u in event.mimeData().urls()][0])
        app = self.parent().parent().parent().parent().parent().parent().parent
        logger.debug(f"App: {app}")
        app.last_dir = fname.parent
        self.import_drag.emit(fname)

