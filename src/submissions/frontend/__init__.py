import re
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QToolBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QPushButton, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit, QHBoxLayout,
    QSpinBox, QScrollArea
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView

# import pandas as pd

from pathlib import Path
import plotly
import pandas as pd
from xhtml2pdf import pisa
# import plotly.express as px
import yaml

from backend.excel.parser import SheetParser
from backend.excel.reports import convert_control_by_mode, convert_data_list_to_df
from backend.db import (construct_submission_info, lookup_reagent, 
    construct_reagent, store_reagent, store_submission, lookup_kittype_by_use,
    lookup_regent_by_type_name_and_kit_name, lookup_all_orgs, lookup_submissions_by_date_range,
    get_all_Control_Types_names, create_kit_from_yaml, get_all_available_modes, get_all_controls_by_type,
    get_control_subtypes
)
from backend.excel.reports import make_report_xlsx, make_report_html
import numpy
from frontend.custom_widgets import AddReagentQuestion, AddReagentForm, SubmissionsSheet, ReportDatePicker, KitAdder, ControlsDatePicker, OverwriteSubQuestion
import logging
import difflib
from datetime import date
from frontend.visualizations.charts import create_charts

logger = logging.getLogger(__name__)
logger.info("Hello, I am a logger")

class App(QMainWindow):

    def __init__(self, ctx: dict = {}):
        super().__init__()
        self.ctx = ctx
        try:
            self.title = f"Submissions App (v{ctx['package'].__version__})"
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
        self.controls_getter()
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
        helpMenu = menuBar.addMenu("&Help")
        fileMenu.addAction(self.importAction)
        reportMenu.addAction(self.generateReportAction)
        
    def _createToolBar(self):
        """
        adds items to toolbar
        """        
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)
        toolbar.addAction(self.addKitAction)

    def _createActions(self):
        """
        creates actions
        """        
        self.importAction = QAction("&Import", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.generateReportAction = QAction("Make Report", self)
        self.addKitAction = QAction("Add Kit", self)


    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.importAction.triggered.connect(self.importSubmission)
        self.addReagentAction.triggered.connect(self.add_reagent)
        self.generateReportAction.triggered.connect(self.generateReport)
        self.addKitAction.triggered.connect(self.add_kit)
        self.table_widget.control_typer.currentIndexChanged.connect(self.controls_getter)
        self.table_widget.mode_typer.currentIndexChanged.connect(self.controls_getter)
        self.table_widget.datepicker.start_date.dateChanged.connect(self.controls_getter)
        self.table_widget.datepicker.end_date.dateChanged.connect(self.controls_getter)


    def importSubmission(self):
        """
        import submission from excel sheet into form
        """        
        logger.debug(self.ctx)
        # initialize samples
        self.samples = []
        # set file dialog
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir)[0])
        logger.debug(f"Attempting to parse file: {fname}")
        assert fname.exists()
        # create sheetparser using excel sheet and context from gui
        try:
            prsr = SheetParser(fname, **self.ctx)
        except PermissionError:
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
                    if prsr.sub[item] == 'nan':
                        msg = QMessageBox()
                        # msg.setIcon(QMessageBox.critical)
                        msg.setText("Error")
                        msg.setInformativeText('You need to enter a value for extraction kit.')
                        msg.setWindowTitle("Error")
                        msg.exec()
                        break
                    # create combobox to hold looked up kits
                    add_widget = QComboBox()
                    # lookup existing kits by 'submission_type' decided on by sheetparser
                    uses = [item.__str__() for item in lookup_kittype_by_use(ctx=self.ctx, used_by=prsr.sub['submission_type'])]
                    if len(uses) > 0:
                        add_widget.addItems(uses)
                    else:
                        add_widget.addItems(['bacterial_culture'])
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
                    add_widget = QComboBox()
                    add_widget.setEditable(True)
                    # Ensure that all reagenttypes have a name that matches the items in the excel parser
                    query_var = item.replace("lot_", "")
                    logger.debug(f"Query for: {query_var}")
                    if isinstance(prsr.sub[item], numpy.float64):
                        logger.debug(f"{prsr.sub[item]} is a numpy float!")
                        try:
                            prsr.sub[item] = int(prsr.sub[item])
                        except ValueError:
                            pass
                    # query for reagents using type name from sheet and kit from sheet
                    relevant_reagents = [item.__str__() for item in lookup_regent_by_type_name_and_kit_name(ctx=self.ctx, type_name=query_var, kit_name=prsr.sub['extraction_kit'])]
                    logger.debug(f"Relevant reagents: {relevant_reagents}")
                    # if reagent in sheet is not found insert it into items
                    if prsr.sub[item] not in relevant_reagents and prsr.sub[item] != 'nan':
                        try:
                            check = not numpy.isnan(prsr.sub[item])
                        except TypeError:
                            check = True
                        if check:
                            relevant_reagents.insert(0, str(prsr.sub[item]))
                    logger.debug(f"Relevant reagents: {relevant_reagents}")
                    add_widget.addItems(relevant_reagents)
                # TODO: make samples not appear in frame.
                case 'samples':
                    # hold samples in 'self' until form submitted
                    logger.debug(f"{item}: {prsr.sub[item]}")
                    self.samples = prsr.sub[item]
                case _:
                    # anything else gets added in as a line edit
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    add_widget = QLineEdit()
                    add_widget.setText(str(prsr.sub[item]).replace("_", " "))
            self.table_widget.formlayout.addWidget(add_widget)
        # create submission button
        submit_btn = QPushButton("Submit")
        self.table_widget.formlayout.addWidget(submit_btn)
        submit_btn.clicked.connect(self.submit_new_sample)
        
    def submit_new_sample(self):
        """
        Attempt to add sample to database when 'submit' button clicked
        """        
        # get info from form
        labels, values = self.extract_form_info(self.table_widget.tab1)
        info = {item[0]:item[1] for item in zip(labels, values) if not item[0].startswith("lot_")}
        reagents = {item[0]:item[1] for item in zip(labels, values) if item[0].startswith("lot_")}
        logger.debug(f"Reagents: {reagents}")
        parsed_reagents = []
        # compare reagents in form to reagent database
        for reagent in reagents:
            wanted_reagent = lookup_reagent(ctx=self.ctx, reagent_lot=reagents[reagent])
            logger.debug(f"Looked up reagent: {wanted_reagent}")
            # if reagent not found offer to add to database
            if wanted_reagent == None:
                dlg = AddReagentQuestion(reagent_type=reagent, reagent_lot=reagents[reagent])
                if dlg.exec():
                    wanted_reagent = self.add_reagent(reagent_lot=reagents[reagent], reagent_type=reagent.replace("lot_", ""))
                else:
                    logger.debug("Will not add reagent.")
            if wanted_reagent != None:
                parsed_reagents.append(wanted_reagent)
                logger.debug(info)
        # move samples into preliminary submission dict
        info['samples'] = self.samples
        # construct submission object
        base_submission, output = construct_submission_info(ctx=self.ctx, info_dict=info)
        # check output message for issues
        if output['message'] != None:
            dlg = OverwriteSubQuestion(output['message'], base_submission.rsl_plate_num)
            if dlg.exec():
                base_submission.reagents = []
            else:
                return
        # add reagents to submission object
        for reagent in parsed_reagents:
            base_submission.reagents.append(reagent)
        logger.debug(f"Sending submission: {base_submission.rsl_plate_num} to database.")
        result = store_submission(ctx=self.ctx, base_submission=base_submission)
        # check result of storing for issues
        if result != None:
            msg = QMessageBox()
            # msg.setIcon(QMessageBox.critical)
            msg.setText("Error")
            msg.setInformativeText(result['message'])
            msg.setWindowTitle("Error")
            msg.exec()
        # update summary sheet
        self.table_widget.sub_wid.setData()
        # reset form
        for item in self.table_widget.formlayout.parentWidget().findChildren(QWidget):
            item.setParent(None)


    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None):
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
        dlg = AddReagentForm(ctx=self.ctx, reagent_lot=reagent_lot, reagent_type=reagent_type)
        if dlg.exec():
            # extract form info
            labels, values = self.extract_form_info(dlg)
            info = {item[0]:item[1] for item in zip(labels, values)}
            logger.debug(f"Reagent info: {info}")
            # create reagent object
            reagent = construct_reagent(ctx=self.ctx, info_dict=info)
            # send reagent to db
            store_reagent(ctx=self.ctx, reagent=reagent)
            return reagent
            

    def extract_form_info(self, object):
        """
        retrieves arbitrary number of labels, values from form

        Args:
            object (_type_): _description_

        Returns:
            _type_: _description_
        """        
        labels = []
        values = []
        # grab all widgets in form
        for item in object.layout.parentWidget().findChildren(QWidget):
            match item:
                case QLabel():
                    labels.append(item.text().replace(" ", "_").lower())
                case QLineEdit():
                    # ad hoc check to prevent double reporting of qdatedit under lineedit for some reason
                    if not isinstance(prev_item, QDateEdit) and not isinstance(prev_item, QComboBox) and not isinstance(prev_item, QSpinBox):
                        logger.debug(f"Previous: {prev_item}")
                        logger.debug(f"Item: {item}")
                        values.append(item.text())
                case QComboBox():
                    values.append(item.currentText())
                case QDateEdit():
                    values.append(item.date().toPyDate())
            # value for ad hoc check above
            prev_item = item
        return labels, values

    def generateReport(self):
        """
        Action to create a summary of sheet data per client
        """
        # Custom two date picker for start & end dates
        dlg = ReportDatePicker()
        if dlg.exec():
            labels, values = self.extract_form_info(dlg)
            info = {item[0]:item[1] for item in zip(labels, values)}
            # find submissions based on date range
            subs = lookup_submissions_by_date_range(ctx=self.ctx, start_date=info['start_date'], end_date=info['end_date'])
            # convert each object to dict
            records = [item.report_dict() for item in subs]
            df = make_report_xlsx(records=records)
            html = make_report_html(df=df, start_date=info['start_date'], end_date=info['end_date'])
            # make dataframe from record dictionaries
            # df = make_report_xlsx(records=records)
            # # setup filedialog to handle save location of report
            home_dir = Path(self.ctx["directory_path"]).joinpath(f"Submissions_Report_{info['start_date']}-{info['end_date']}.pdf").resolve().__str__()
            # fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".xlsx")[0])
            fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".pdf")[0])
            # logger.debug(f"report output name: {fname}")
            # df.to_excel(fname, engine='openpyxl')
            with open(fname, "w+b") as f:
                pisa.CreatePDF(html, dest=f)
            df.to_excel(fname.with_suffix(".xlsx"), engine='openpyxl')       

            
            

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
        msg = QMessageBox()
        # msg.setIcon(QMessageBox.critical)
        match result['code']:
            case 0:
                msg.setText("Kit added")
                msg.setInformativeText(result['message'])
                msg.setWindowTitle("Kit added")
            case 1:
                msg.setText("Permission Error")
                msg.setInformativeText(result['message'])
                msg.setWindowTitle("Permission Error")
        msg.exec()



    def controls_getter(self):
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
            threemonthsago = self.table_widget.datepicker.end_date.date().addDays(-90)
            # block signal that will rerun controls getter and set start date
            with QSignalBlocker(self.table_widget.datepicker.start_date) as blocker:
                self.table_widget.datepicker.start_date.setDate(threemonthsago)
            self.controls_getter()
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
            self.table_widget.sub_typer.currentTextChanged.connect(self.chart_maker)
        else:
            self.table_widget.sub_typer.clear()
            self.table_widget.sub_typer.setEnabled(False)
        self.chart_maker()
        
        
    def chart_maker(self):
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
            # return
            fig = None
        else:
            data = []
            for control in controls:
                # change each control to list of dicts
                dicts = convert_control_by_mode(ctx=self.ctx, control=control, mode=self.mode)
                data.append(dicts)
            # flatten data to one dimensional list
            data = [item for sublist in data for item in sublist]
            # logger.debug(data)
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
        # with open("C:\\Users\\lwark\\Desktop\\test.html", "w") as f:
        #     f.write(html)
        # add html to webview and update.
        self.table_widget.webengineview.setHtml(html)
        self.table_widget.webengineview.update()
        logger.debug("Figure updated... I hope.")


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

        
