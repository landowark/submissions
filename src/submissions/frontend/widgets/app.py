"""
Constructs main application.
"""
import logging, webbrowser, sys
from pprint import pformat
from PyQt6.QtCore import QEvent, QTimer, qInstallMessageHandler
from PyQt6.QtWidgets import (
    QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QScrollArea, QMainWindow,
    QToolBar, QApplication
)
from PyQt6.QtGui import QAction
from pathlib import Path
from markdown import markdown
from pandas import ExcelWriter
from backend.validators.pydant import PydAbstract, PydConcrete
from tools import (
    check_if_app, Settings, Report, jinja_template_loading, check_authorization, page_size, is_power_user,
    under_development, ctx
)
from .date_type_picker import DateTypePicker
from .functions import select_save_file
from .pop_ups import HTMLPop
from .misc import Pagifier
from .submission_table import SubmissionsTree, ClientSubmissionRunModel
from .submission_widget import SubmissionFormContainer
from .summary import Summary
from .turnaround import TurnaroundTime
from .concentration_viewer import ConcentrationViewer
from .omni_search import SearchBox
from .kraken_viewer import KrakenViewer
from .pcr_viewer import PCRViewer

logger = logging.getLogger(f'submissions.{__name__}')


class App(QMainWindow):

    def __init__(self, ctx: Settings = None):
        super().__init__()
        qInstallMessageHandler(lambda x, y, z: None)
        self.ctx = ctx
        self.last_dir = ctx.directories.main
        self.report = Report()
        # NOTE: indicate version and connected database in title bar
        try:
            self.title = f"Submissions App (v{ctx.package.__version__}) - {ctx.database.path}/{ctx.database.name}"
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
        # NOTE: procedure initial setups
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._connectActions()
        self.show()
        self.statusBar().showMessage('Ready', 5000)
        # 1. Define the timeout in milliseconds (e.g., 5 minutes)
        self.timeout_limit = 5 * 60 * 1000 
        
        # 2. Setup the idle timer
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(self.timeout_limit)
        self.idle_timer.setSingleShot(True)  # Only fire once per cycle
        self.idle_timer.timeout.connect(self.handle_timeout)
        self.idle_timer.start()

        # 3. Monitor global events by installing a filter on the app instance
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):
        # Define events that count as "activity"
        activity_events = {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, 
                           QEvent.Type.KeyPress, QEvent.Type.Wheel}
        if event.type() in activity_events:
            self.reset_timer()
        return super().eventFilter(obj, event)

    def reset_timer(self):
        # Restarting the timer resets the countdown
        self.idle_timer.start()

    def handle_timeout(self):
        sys.exit(ctx.run_teardown()) # Standard way to exit a PyQt6 application


    def _createMenuBar(self):
        """
        adds items to menu bar
        """
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        # NOTE: Creating menus using a title
        methodsMenu = menuBar.addMenu("&Search")
        manageabstractsMenu = menuBar.addMenu("&Manage Abstracts")
        managedconcreteMenu = menuBar.addMenu("&Manage Concrete")
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpAction)
        helpMenu.addAction(self.docsAction)
        helpMenu.addAction(self.githubAction)
        fileMenu.addAction(self.importAction)
        fileMenu.addAction(self.archiveSubmissionsAction)
        methodsMenu.addAction(self.searchSample)
        for action in self.abstractActions:
            manageabstractsMenu.addAction(action)
            if not is_power_user():
                action.setEnabled(False)
        for action in self.concreateActions:
            managedconcreteMenu.addAction(action)
            
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
        self.archiveSubmissionsAction = QAction("Submissions to Excel", self)
        self.abstractActions = [QAction(f"Manage {subcls.__name__.replace("Pyd", "")}", self) for subcls in PydAbstract.get_managables()]
        self.concreateActions = [QAction(f"Manage {subcls.__name__.replace("Pyd", "")}", self) for subcls in PydConcrete.get_managables()]
                

    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.importAction.triggered.connect(lambda fname: self.table_widget.formwidget.import_submission_function(fname=fname))
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)
        self.searchSample.triggered.connect(self.runSampleSearch)
        self.githubAction.triggered.connect(self.openGithub)
        self.archiveSubmissionsAction.triggered.connect(self.submissions_to_excel)
        self.table_widget.pager.current_page.textChanged.connect(self.update_data)
        for action in self.abstractActions:
            class_ = next((subcls for subcls in PydAbstract.get_managables() if f"Manage {subcls.__name__.replace('Pyd', '')}" == action.text()), None)
            if class_:
                action.triggered.connect(lambda checked, parent=self, obj_type=class_: obj_type.manage(parent=parent))
        for action in self.concreateActions:
            class_ = next((subcls for subcls in PydConcrete.get_managables() if f"Manage {subcls.__name__.replace('Pyd', '')}" == action.text()), None)
            if class_:
                action.triggered.connect(lambda checked, parent=self, obj_type=class_: obj_type.manage(parent=parent))

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
        Create a search for sample.
        """
        from backend.db.models.submissions import Sample
        dlg = SearchBox(self, object_type=Sample, extras=[])
        dlg.exec()

    @check_authorization
    def edit_reagent(self, *args, **kwargs):
        from backend.db.models import ReagentLot
        dlg = SearchBox(parent=self, object_type=ReagentLot, extras=ReagentLot.get_searchables())
        dlg.exec()

    def update_data(self):
        self.table_widget.sub_wid.setData(page=self.table_widget.pager.page_anchor, page_size=page_size)

    # TODO: Change this to the Pydantic version.
    def manage_orgs(self):
        from frontend.widgets.omni_manager_pydant import ManagerWindow as ManagerWindowPyd
        dlg = ManagerWindowPyd(parent=self, object_type=Organization, extras=[], add_edit='edit', managers=set())
        if dlg.exec():
            new_org = dlg.parse_form()
            new_org.save()

    @under_development
    def submissions_to_excel(self, *args, **kwargs):
        from backend.db.models import Run
        dlg = DateTypePicker(self)
        if dlg.exec():
            output = dlg.parse_form()
            # TODO: Move to ClientSubmissions
            df = Run.archive_submissions(**output)
            filepath = select_save_file(self, f"Submissions {output['start_date']}-{output['end_date']}", "xlsx")
            writer = ExcelWriter(filepath, "openpyxl")
            df.to_excel(writer)
            writer.close()

    def closeEvent(self, event):
        try:
            self.ctx.run_teardown()   # closes session + disposes engine (checkpoints WAL)
        finally:
            super().closeEvent(event)


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
        self.tab6 = QWidget()
        self.tabs.resize(300, 200)
        # NOTE: Add tabs
        self.tabs.addTab(self.tab1, "Submissions")
        self.tabs.addTab(self.tab2, "Irida Controls")
        self.tabs.addTab(self.tab6, "Concentrations")
        self.tabs.addTab(self.tab3, "PCR Controls")
        self.tabs.addTab(self.tab4, "Cost Report")
        self.tabs.addTab(self.tab5, "Turnaround Times")
        # NOTE: Create procedure adder form
        self.formwidget = SubmissionFormContainer(self)
        self.formlayout = QVBoxLayout(self)
        self.formwidget.setLayout(self.formlayout)
        self.formwidget.setFixedWidth(300)
        # NOTE: Make scrollable interior for form
        self.interior = QScrollArea(self.tab1)
        self.interior.setWidgetResizable(True)
        self.interior.setFixedWidth(325)
        self.interior.setWidget(self.formwidget)
        # NOTE: Create sheet to hold existing procedure
        self.sheetwidget = QWidget(self)
        self.sheetlayout = QVBoxLayout(self)
        self.sheetwidget.setLayout(self.sheetlayout)
        self.sub_wid = SubmissionsTree(parent=parent, model=ClientSubmissionRunModel(self))
        self.pager = Pagifier(page_max=self.sub_wid.total_count / page_size)
        self.sheetlayout.addWidget(self.sub_wid)
        self.sheetlayout.addWidget(self.pager)
        # NOTE: Create layout of first tab to hold form and sheet
        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        self.tab1.layout.addWidget(self.interior)
        self.tab1.layout.addWidget(self.sheetwidget)
        self.tab2.layout = QVBoxLayout(self)
        self.irida_viewer = KrakenViewer(self)
        self.tab2.layout.addWidget(self.irida_viewer)
        self.tab2.setLayout(self.tab2.layout)
        self.tab3.layout = QVBoxLayout(self)
        self.pcr_viewer = PCRViewer(self)
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
        concentration = ConcentrationViewer(self)
        self.tab6.layout = QVBoxLayout(self)
        self.tab6.layout.addWidget(concentration)
        self.tab6.setLayout(self.tab6.layout)
        # NOTE: add tabs to main widget
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
