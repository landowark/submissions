'''
Operations for all user interactions.
'''
import json
import re
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QToolBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit, QHBoxLayout,
    QScrollArea
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
# import pandas as pd
from pathlib import Path
import plotly
import pandas as pd
from openpyxl.utils import get_column_letter
from xhtml2pdf import pisa
# import plotly.express as px
import yaml
import pprint
from backend.excel import convert_data_list_to_df, make_report_xlsx, make_report_html, SheetParser
from backend.db import (construct_submission_info, lookup_reagent, 
    construct_reagent, store_submission, lookup_kittype_by_use,
    lookup_regent_by_type_name, lookup_all_orgs, lookup_submissions_by_date_range,
    get_all_Control_Types_names, create_kit_from_yaml, get_all_available_modes, get_all_controls_by_type,
    get_control_subtypes, lookup_all_submissions_by_type, get_all_controls, lookup_submission_by_rsl_num,
    create_org_from_yaml, store_reagent
)
from backend.db import lookup_kittype_by_name
from .functions import extract_form_info
from tools import check_not_nan, check_kit_integrity, check_if_app
# from backend.excel.reports import 
from frontend.custom_widgets import SubmissionsSheet, AlertPop, QuestionAsker, AddReagentForm, ReportDatePicker, KitAdder, ControlsDatePicker, ImportReagent
import logging
import difflib
from getpass import getuser
from datetime import date
from frontend.visualizations import create_charts
import webbrowser

logger = logging.getLogger(f'submissions.{__name__}')
logger.info("Hello, I am a logger")

class App(QMainWindow):

    def __init__(self, ctx: dict = {}):
        super().__init__()
        self.ctx = ctx
        # indicate version and database connected in title bar
        try:
            self.title = f"Submissions App (v{ctx['package'].__version__}) - {ctx['database']}"
        except AttributeError:
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
        

    def _createMenuBar(self):
        """
        adds items to menu bar
        """        
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        # Creating menus using a title
        editMenu = menuBar.addMenu("&Edit")
        reportMenu = menuBar.addMenu("&Reports")
        maintenanceMenu = menuBar.addMenu("&Monthly")
        helpMenu = menuBar.addMenu("&Help")
        helpMenu.addAction(self.helpAction)
        helpMenu.addAction(self.docsAction)
        fileMenu.addAction(self.importAction)
        reportMenu.addAction(self.generateReportAction)
        maintenanceMenu.addAction(self.joinControlsAction)
        maintenanceMenu.addAction(self.joinExtractionAction)
        
    def _createToolBar(self):
        """
        adds items to toolbar
        """        
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)
        toolbar.addAction(self.addKitAction)
        toolbar.addAction(self.addOrgAction)

    def _createActions(self):
        """
        creates actions
        """        
        self.importAction = QAction("&Import", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.generateReportAction = QAction("Make Report", self)
        self.addKitAction = QAction("Import Kit", self)
        self.addOrgAction = QAction("Import Org", self)
        self.joinControlsAction = QAction("Link Controls")
        self.joinExtractionAction = QAction("Link Ext Logs")
        self.helpAction = QAction("&About", self)
        self.docsAction = QAction("&Docs", self)


    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.importAction.triggered.connect(self.importSubmission)
        self.addReagentAction.triggered.connect(self.add_reagent)
        self.generateReportAction.triggered.connect(self.generateReport)
        self.addKitAction.triggered.connect(self.add_kit)
        self.addOrgAction.triggered.connect(self.add_org)
        self.table_widget.control_typer.currentIndexChanged.connect(self._controls_getter)
        self.table_widget.mode_typer.currentIndexChanged.connect(self._controls_getter)
        self.table_widget.datepicker.start_date.dateChanged.connect(self._controls_getter)
        self.table_widget.datepicker.end_date.dateChanged.connect(self._controls_getter)
        self.joinControlsAction.triggered.connect(self.linkControls)
        self.joinExtractionAction.triggered.connect(self.linkExtractions)
        self.helpAction.triggered.connect(self.showAbout)
        self.docsAction.triggered.connect(self.openDocs)

    def showAbout(self):
        output = f"Version: {self.ctx['package'].__version__}\n\nAuthor: {self.ctx['package'].__author__['name']} - {self.ctx['package'].__author__['email']}\n\nCopyright: {self.ctx['package'].__copyright__}"
        about = AlertPop(message=output, status="information")
        about.exec()

    def openDocs(self):
        if check_if_app():
            url = Path(sys._MEIPASS).joinpath("files", "docs", "index.html")
        else:
            url = Path("docs\\build\\index.html").absolute()
        logger.debug(f"Attempting to open {url}")
        webbrowser.get('windows-default').open(f"file://{url.__str__()}")


    def importSubmission(self):
        """
        import submission from excel sheet into form
        """        
        logger.debug(self.ctx)
        # initialize samples
        self.samples = []
        self.reagents = {}
        # set file dialog
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir)[0])
        logger.debug(f"Attempting to parse file: {fname}")
        assert fname.exists()
        # create sheetparser using excel sheet and context from gui
        try:
            prsr = SheetParser(fname, **self.ctx)
        except PermissionError:
            logger.error(f"Couldn't get permission to access file: {fname}")
            return
        logger.debug(f"prsr.sub = {prsr.sub}")
        # destroy any widgets from previous imports
        for item in self.table_widget.formlayout.parentWidget().findChildren(QWidget):
            item.setParent(None)
        # regex to parser out different variable types for decision making
        variable_parser = re.compile(r"""
            # (?x)
            (?P<extraction_kit>^extraction_kit$) |
            (?P<submitted_date>^submitted_date$) |
            (?P<submitting_lab>)^submitting_lab$ |
            (?P<samples>)^samples$ |
            (?P<reagent>^lot_.*$)
        """, re.VERBOSE)
        for item in prsr.sub:
            logger.debug(f"Item: {item}")
            # attempt to match variable name to regex group
            try:
                mo = variable_parser.fullmatch(item).lastgroup
            except AttributeError:
                mo = "other"
            logger.debug(f"Mo: {mo}")
            match mo:
                case 'submitting_lab':
                    # create label
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    logger.debug(f"{item}: {prsr.sub[item]}")
                    # create combobox to hold looked up submitting labs
                    add_widget = QComboBox()
                    labs = [item.__str__() for item in lookup_all_orgs(ctx=self.ctx)]
                    # try to set closest match to top of list
                    try:
                        labs = difflib.get_close_matches(prsr.sub[item], labs, len(labs), 0)
                    except (TypeError, ValueError):
                        pass
                    # set combobox values to lookedup values
                    add_widget.addItems(labs)
                case 'extraction_kit':
                    # create label
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    # if extraction kit not available, all other values fail
                    if not check_not_nan(prsr.sub[item]):
                        msg = AlertPop(message="Make sure to check your extraction kit in the excel sheet!", status="warning")
                        msg.exec()
                    # create combobox to hold looked up kits
                    add_widget = QComboBox()
                    # lookup existing kits by 'submission_type' decided on by sheetparser
                    uses = [item.__str__() for item in lookup_kittype_by_use(ctx=self.ctx, used_by=prsr.sub['submission_type'])]
                    # if len(uses) > 0:
                    add_widget.addItems(uses)
                    # else:
                        # add_widget.addItems(['bacterial_culture'])
                    self.ext_kit = prsr.sub[item]
                case 'submitted_date':
                    # create label
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    # uses base calendar
                    add_widget = QDateEdit(calendarPopup=True)
                    # sets submitted date based on date found in excel sheet
                    try:
                        add_widget.setDate(prsr.sub[item])
                    # if not found, use today
                    except:
                        add_widget.setDate(date.today())
                case 'reagent':
                    # create label
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    # create reagent choice widget
                    add_widget = ImportReagent(ctx=self.ctx, item=item, prsr=prsr)
                    self.reagents[item] = prsr.sub[item]
                case 'samples':
                    # hold samples in 'self' until form submitted
                    logger.debug(f"{item}: {prsr.sub[item]}")
                    self.samples = prsr.sub[item]
                    add_widget = None
                case _:
                    # anything else gets added in as a line edit
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    add_widget = QLineEdit()
                    add_widget.setText(str(prsr.sub[item]).replace("_", " "))
            try:
                add_widget.setObjectName(item)
                logger.debug(f"Widget name set to: {add_widget.objectName()}")
                self.table_widget.formlayout.addWidget(add_widget)
            except AttributeError as e:
                logger.error(e)
        # compare self.reagents with expected reagents in kit
        if hasattr(self, 'ext_kit'):
            kit = lookup_kittype_by_name(ctx=self.ctx, name=self.ext_kit)
            kit_integrity = check_kit_integrity(kit, [item.replace("lot_", "") for item in self.reagents])
            if kit_integrity != None:
                msg = AlertPop(message=kit_integrity['message'], status="critical")
                msg.exec()
                for item in kit_integrity['missing']:
                    self.table_widget.formlayout.addWidget(QLabel(f"Lot {item.replace('_', ' ').title()}"))
                    add_widget = ImportReagent(ctx=self.ctx, item=item)
                    self.table_widget.formlayout.addWidget(add_widget)
        # create submission button
        submit_btn = QPushButton("Submit")
        self.table_widget.formlayout.addWidget(submit_btn)
        submit_btn.clicked.connect(self.submit_new_sample)
        logger.debug(f"Imported reagents: {self.reagents}")
        
    def submit_new_sample(self):
        """
        Attempt to add sample to database when 'submit' button clicked
        """        
        # get info from form
        info = extract_form_info(self.table_widget.tab1)
        reagents = {k:v for k,v in info.items() if k.startswith("lot_")}
        info = {k:v for k,v in info.items() if not k.startswith("lot_")}
        logger.debug(f"Info: {info}")
        logger.debug(f"Reagents: {reagents}")
        parsed_reagents = []
        # compare reagents in form to reagent database
        for reagent in reagents:
            wanted_reagent = lookup_reagent(ctx=self.ctx, reagent_lot=reagents[reagent])
            logger.debug(f"Looked up reagent: {wanted_reagent}")
            # if reagent not found offer to add to database
            if wanted_reagent == None:
                r_lot = reagents[reagent]
                dlg = QuestionAsker(title=f"Add {r_lot}?", message=f"Couldn't find reagent type {reagent.replace('_', ' ').title().strip('Lot')}: {r_lot} in the database.\n\nWould you like to add it?")
                if dlg.exec():
                    logger.debug(f"checking reagent: {reagent} in self.reagents. Result: {self.reagents[reagent]}")
                    expiry_date = self.reagents[reagent]['exp']
                    wanted_reagent = self.add_reagent(reagent_lot=r_lot, reagent_type=reagent.replace("lot_", ""), expiry=expiry_date)
                else:
                    # In this case we will have an empty reagent and the submission will fail kit integrity check
                    logger.debug("Will not add reagent.")
            if wanted_reagent != None:
                parsed_reagents.append(wanted_reagent)
        # move samples into preliminary submission dict
        info['samples'] = self.samples
        info['uploaded_by'] = getuser()
        # construct submission object
        logger.debug(f"Here is the info_dict: {pprint.pformat(info)}")
        base_submission, result = construct_submission_info(ctx=self.ctx, info_dict=info)
        # check output message for issues
        match result['code']:
            # code 1: ask for overwrite
            case 1:
                dlg = QuestionAsker(title=f"Review {base_submission.rsl_plate_num}?", message=result['message'])
                if dlg.exec():
                    base_submission.reagents = []
                else:
                    return
            # code 2: No RSL plate number given
            case 2:
                dlg = AlertPop(message=result['message'], status='critical')
                dlg.exec()
                return
            case _:
                pass
        # add reagents to submission object
        for reagent in parsed_reagents:
            base_submission.reagents.append(reagent)
        logger.debug("Checking kit integrity...")
        kit_integrity = check_kit_integrity(base_submission)
        if kit_integrity != None:
            msg = AlertPop(message=kit_integrity['message'], status="critical")
            msg.exec()
            return
        logger.debug(f"Sending submission: {base_submission.rsl_plate_num} to database.")
        result = store_submission(ctx=self.ctx, base_submission=base_submission)
        # check result of storing for issues
        if result != None:
            msg = AlertPop(result['message'])
            msg.exec()
        # update summary sheet
        self.table_widget.sub_wid.setData()
        # reset form
        for item in self.table_widget.formlayout.parentWidget().findChildren(QWidget):
            item.setParent(None)


    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None):
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
        dlg = AddReagentForm(ctx=self.ctx, reagent_lot=reagent_lot, reagent_type=reagent_type, expiry=expiry)
        if dlg.exec():
            # extract form info
            info = extract_form_info(dlg)
            logger.debug(f"dictionary from form: {info}")
            # return None
            logger.debug(f"Reagent info: {info}")
            # create reagent object
            reagent = construct_reagent(ctx=self.ctx, info_dict=info)
            # send reagent to db
            store_reagent(ctx=self.ctx, reagent=reagent)
            return reagent
            

    def generateReport(self):
        """
        Action to create a summary of sheet data per client
        """
        # Custom two date picker for start & end dates
        dlg = ReportDatePicker()
        if dlg.exec():
            info = extract_form_info(dlg)
            logger.debug(f"Report info: {info}")
            # find submissions based on date range
            subs = lookup_submissions_by_date_range(ctx=self.ctx, start_date=info['start_date'], end_date=info['end_date'])
            # convert each object to dict
            records = [item.report_dict() for item in subs]
            # make dataframe from record dictionaries
            df = make_report_xlsx(records=records)
            html = make_report_html(df=df, start_date=info['start_date'], end_date=info['end_date'])
            # setup filedialog to handle save location of report
            home_dir = Path(self.ctx["directory_path"]).joinpath(f"Submissions_Report_{info['start_date']}-{info['end_date']}.pdf").resolve().__str__()
            fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".pdf")[0])
            # logger.debug(f"report output name: {fname}")
            with open(fname, "w+b") as f:
                pisa.CreatePDF(html, dest=f)
            writer = pd.ExcelWriter(fname.with_suffix(".xlsx"), engine='openpyxl')
            df.to_excel(writer, sheet_name="Report") 
            worksheet = writer.sheets['Report']
            for idx, col in enumerate(df):  # loop through all columns
                series = df[col]
                max_len = max((
                    series.astype(str).map(len).max(),  # len of largest item
                    len(str(series.name))  # len of column name/header
                    )) + 20  # adding a little extra space
                try:
                    worksheet.column_dimensions[get_column_letter(idx)].width = max_len 
                except ValueError:
                    pass
            for cell in worksheet['D']:
                if cell.row > 1:
                    cell.style = 'Currency'
            writer.close()
                  

    def add_kit(self):
        """
        Constructs new kit from yaml and adds to DB.
        """
        # setup file dialog to find yaml flie
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir, filter = "yml(*.yml)")[0])
        assert fname.exists()
        # read yaml file
        try:
            with open(fname.__str__(), "r") as stream:
                try:
                    exp = yaml.load(stream, Loader=yaml.Loader)
                except yaml.YAMLError as exc:
                    logger.error(f'Error reading yaml file {fname}: {exc}')
                    return {}
        except PermissionError:
            return
        # send to kit creator function
        result = create_kit_from_yaml(ctx=self.ctx, exp=exp)
        match result['code']:
            case 0:
                msg = AlertPop(message=result['message'], status='info')
            case 1:
                msg = AlertPop(message=result['message'], status='critical')
        msg.exec()


    def add_org(self):
        """
        Constructs new kit from yaml and adds to DB.
        """
        # setup file dialog to find yaml flie
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir, filter = "yml(*.yml)")[0])
        assert fname.exists()
        # read yaml file
        try:
            with open(fname.__str__(), "r") as stream:
                try:
                    org = yaml.load(stream, Loader=yaml.Loader)
                except yaml.YAMLError as exc:
                    logger.error(f'Error reading yaml file {fname}: {exc}')
                    return {}
        except PermissionError:
            return
        # send to kit creator function
        result = create_org_from_yaml(ctx=self.ctx, org=org)
        match result['code']:
            case 0:
                msg = AlertPop(message=result['message'], status='information')
            case 1:
                msg = AlertPop(message=result['message'], status='critical')
        msg.exec()




    def _controls_getter(self):
        """
        Lookup controls from database and send to chartmaker
        """        
        # subtype defaults to disabled  
        try:
            self.table_widget.sub_typer.disconnect()
        except TypeError:
            pass
        # correct start date being more recent than end date and rerun
        if self.table_widget.datepicker.start_date.date() > self.table_widget.datepicker.end_date.date():
            logger.warning("Start date after end date is not allowed!")
            threemonthsago = self.table_widget.datepicker.end_date.date().addDays(-60)
            # block signal that will rerun controls getter and set start date
            with QSignalBlocker(self.table_widget.datepicker.start_date) as blocker:
                self.table_widget.datepicker.start_date.setDate(threemonthsago)
            self._controls_getter()
            return
            # convert to python useable date object
        self.start_date = self.table_widget.datepicker.start_date.date().toPyDate()
        self.end_date = self.table_widget.datepicker.end_date.date().toPyDate()
        self.con_type = self.table_widget.control_typer.currentText()
        self.mode = self.table_widget.mode_typer.currentText()
        self.table_widget.sub_typer.clear()
        # lookup subtypes
        sub_types = get_control_subtypes(ctx=self.ctx, type=self.con_type, mode=self.mode)
        if sub_types != []:
            # block signal that will rerun controls getter and update sub_typer
            with QSignalBlocker(self.table_widget.sub_typer) as blocker: 
                self.table_widget.sub_typer.addItems(sub_types)
            self.table_widget.sub_typer.setEnabled(True)
            self.table_widget.sub_typer.currentTextChanged.connect(self._chart_maker)
        else:
            self.table_widget.sub_typer.clear()
            self.table_widget.sub_typer.setEnabled(False)
        self._chart_maker()
        
        
    def _chart_maker(self):
        """
        Creates plotly charts for webview
        """        
        logger.debug(f"Control getter context: \n\tControl type: {self.con_type}\n\tMode: {self.mode}\n\tStart Date: {self.start_date}\n\tEnd Date: {self.end_date}")
        if self.table_widget.sub_typer.currentText() == "":
            self.subtype = None
        else:
            self.subtype = self.table_widget.sub_typer.currentText()
        logger.debug(f"Subtype: {self.subtype}")
        # query all controls using the type/start and end dates from the gui
        controls = get_all_controls_by_type(ctx=self.ctx, con_type=self.con_type, start_date=self.start_date, end_date=self.end_date)
        # if no data found from query set fig to none for reporting in webview
        if controls == None:
            fig = None
        else:
            # change each control to list of dicts
            data = [control.convert_by_mode(mode=self.mode) for control in controls]
            # flatten data to one dimensional list
            data = [item for sublist in data for item in sublist]
            # send to dataframe creator
            df = convert_data_list_to_df(ctx=self.ctx, input=data, subtype=self.subtype)
            if self.subtype == None:
                title = self.mode
            else:
                title = f"{self.mode} - {self.subtype}"
            # send dataframe to chart maker
            fig = create_charts(ctx=self.ctx, df=df, ytitle=title)
        logger.debug(f"Updating figure...")
        # construct html for webview
        html = '<html><body>'
        if fig != None:
            html += plotly.offline.plot(fig, output_type='div', include_plotlyjs='cdn')#, image = 'png', auto_open=True, image_filename='plot_image')
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        self.table_widget.webengineview.setHtml(html)
        self.table_widget.webengineview.update()
        logger.debug("Figure updated... I hope.")


    def linkControls(self):
        all_bcs = lookup_all_submissions_by_type(self.ctx, "Bacterial Culture")
        logger.debug(all_bcs)
        all_controls = get_all_controls(self.ctx)
        ac_list = [control.name for control in all_controls]
        count = 0
        for bcs in all_bcs:
            logger.debug(f"Running for {bcs.rsl_plate_num}")
            logger.debug(f"Here is the current control: {[control.name for control in bcs.controls]}")
            samples = [sample.sample_id for sample in bcs.samples]
            logger.debug(bcs.controls)
            for sample in samples:
                # replace below is a stopgap method because some dingus decided to add spaces in some of the ATCC49... so it looks like "ATCC 49"...
                if " " in sample:
                    logger.warning(f"There is not supposed to be a space in the sample name!!!")
                    sample = sample.replace(" ", "")
                # if sample not in ac_list:
                if not any([ac.startswith(sample) for ac in ac_list]):
                    continue
                else:
                    for control in all_controls:
                        diff = difflib.SequenceMatcher(a=sample, b=control.name).ratio()
                        if control.name.startswith(sample):
                            logger.debug(f"Checking {sample} against {control.name}... {diff}")
                            logger.debug(f"Found match:\n\tSample: {sample}\n\tControl: {control.name}\n\tDifference: {diff}")
                            if control in bcs.controls:
                                logger.debug(f"{control.name} already in {bcs.rsl_plate_num}, skipping")
                                continue
                            else:
                                logger.debug(f"Adding {control.name} to {bcs.rsl_plate_num} as control")
                                bcs.controls.append(control)
                                # bcs.control_id.append(control.id)
                                control.submission = bcs
                                control.submission_id = bcs.id
                                self.ctx["database_session"].add(control)
                                count += 1
            self.ctx["database_session"].add(bcs)
            logger.debug(f"Here is the new control: {[control.name for control in bcs.controls]}")
        result = f"We added {count} controls to bacterial cultures."
        logger.debug(result)
        self.ctx['database_session'].commit()
        msg = QMessageBox()
        msg.setText("Controls added")
        msg.setInformativeText(result)
        msg.setWindowTitle("Controls added")
        msg.exec()


    def linkExtractions(self):
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir, filter = "csv(*.csv)")[0])
        with open(fname.__str__(), 'r') as f:
            runs = [col.strip().split(",") for col in f.readlines()]
        count = 0
        for run in runs:
            obj = dict(
                    start_time=run[0].strip(), 
                    rsl_plate_num=run[1].strip(), 
                    sample_count=run[2].strip(), 
                    status=run[3].strip(),
                    experiment_name=run[4].strip(),
                    end_time=run[5].strip()
                )
            for ii in range(6, len(run)):
                obj[f"column{str(ii-5)}_vol"] = run[ii]
            sub = lookup_submission_by_rsl_num(ctx=self.ctx, rsl_num=obj['rsl_plate_num'])
            try:
                logger.debug(f"Found submission: {sub.rsl_plate_num}")
                count += 1
            except AttributeError:
                continue
            if sub.extraction_info != None:
                existing = json.loads(sub.extraction_info)
            else:
                existing = None
            try:
                if json.dumps(obj) in sub.extraction_info:
                    logger.debug(f"Looks like we already have that info.")
                    continue
            except TypeError:
                pass
            if existing != None:
                try:
                    logger.debug(f"Updating {type(existing)}: {existing} with {type(obj)}: {obj}")
                    existing.append(obj)
                    logger.debug(f"Setting: {existing}")
                    sub.extraction_info = json.dumps(existing)
                except TypeError:
                    logger.error(f"Error updating!")
                    sub.extraction_info = json.dumps([obj])
                logger.debug(f"Final ext info for {sub.rsl_plate_num}: {sub.extraction_info}")
            else:
                sub.extraction_info = json.dumps([obj])        
            self.ctx['database_session'].add(sub)
            self.ctx["database_session"].commit()
        dlg = AlertPop(message=f"We added {count} logs to the database.", status='information')
        dlg.exec()


class AddSubForm(QWidget):
    
    def __init__(self, parent):
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
        self.formwidget = QWidget(self)
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
        con_types = get_all_Control_Types_names(ctx=parent.ctx)
        self.control_typer.addItems(con_types)
        # create custom widget to get types of analysis
        self.mode_typer = QComboBox()
        mode_types = get_all_available_modes(ctx=parent.ctx)
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

        
