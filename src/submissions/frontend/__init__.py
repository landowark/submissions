import re
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QToolBar, QStatusBar, 
    QTabWidget, QWidget, QVBoxLayout,
    QPushButton, QMenuBar, QFileDialog,
    QLineEdit, QMessageBox, QComboBox, QDateEdit, QHBoxLayout,
    QSpinBox
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtCore import QDateTime, QDate, QSignalBlocker
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWebEngineWidgets import QWebEngineView

import pandas as pd

from pathlib import Path
import plotly
import plotly.express as px
import yaml

from backend.excel.parser import SheetParser
from backend.excel.reports import convert_control_by_mode, convert_data_list_to_df
from backend.db import (construct_submission_info, lookup_reagent, 
    construct_reagent, store_reagent, store_submission, lookup_kittype_by_use,
    lookup_regent_by_type_name_and_kit_name, lookup_all_orgs, lookup_submissions_by_date_range,
    get_all_Control_Types_names, create_kit_from_yaml, get_all_available_modes, get_all_controls_by_type,
    get_control_subtypes
)
from backend.excel.reports import make_report_xlsx
import numpy
from frontend.custom_widgets import AddReagentQuestion, AddReagentForm, SubmissionsSheet, ReportDatePicker, KitAdder, ControlsDatePicker
import logging
import difflib

from frontend.visualizations.charts import create_charts

logger = logging.getLogger(__name__)
logger.info("Hello, I am a logger")

class App(QMainWindow):
# class App(QScrollArea):

    def __init__(self, ctx: dict = {}):
        super().__init__()
        self.ctx = ctx
        self.title = 'Submissions App - PyQT6'
        self.left = 0
        self.top = 0
        self.width = 1300
        self.height = 1000
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)
        
        self.table_widget = AddSubForm(self)
        self.setCentralWidget(self.table_widget)
        
        self._createActions()
        self._createMenuBar()
        self._createToolBar()
        self._connectActions()
        # self.renderPage()
        self.controls_getter()
        self.show()

    def _createMenuBar(self):
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("&File")
        # menuBar.addMenu(fileMenu)
        # Creating menus using a title
        editMenu = menuBar.addMenu("&Edit")
        reportMenu = menuBar.addMenu("&Reports")
        helpMenu = menuBar.addMenu("&Help")
        fileMenu.addAction(self.importAction)
        reportMenu.addAction(self.generateReportAction)
        
    def _createToolBar(self):
        toolbar = QToolBar("My main toolbar")
        self.addToolBar(toolbar)
        toolbar.addAction(self.addReagentAction)
        toolbar.addAction(self.addKitAction)

    def _createActions(self):
        self.importAction = QAction("&Import", self)
        self.addReagentAction = QAction("Add Reagent", self)
        self.generateReportAction = QAction("Make Report", self)
        self.addKitAction = QAction("Add Kit", self)


    def _connectActions(self):
        self.importAction.triggered.connect(self.importSubmission)
        self.addReagentAction.triggered.connect(self.add_reagent)
        self.generateReportAction.triggered.connect(self.generateReport)
        self.addKitAction.triggered.connect(self.add_kit)
        self.table_widget.control_typer.currentIndexChanged.connect(self.controls_getter)
        self.table_widget.mode_typer.currentIndexChanged.connect(self.controls_getter)
        self.table_widget.datepicker.start_date.dateChanged.connect(self.controls_getter)
        self.table_widget.datepicker.end_date.dateChanged.connect(self.controls_getter)


    def importSubmission(self):
        logger.debug(self.ctx)
        self.samples = []
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir)[0])
        logger.debug(f"Attempting to parse file: {fname}")
        assert fname.exists()
        try:
            prsr = SheetParser(fname, **self.ctx)
        except PermissionError:
            return
        print(f"prsr.sub = {prsr.sub}")
        # replace formlayout with tab1.layout
        for item in self.table_widget.formlayout.parentWidget().findChildren(QWidget):
            item.setParent(None)
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
            
            try:
                mo = variable_parser.fullmatch(item).lastgroup
            except AttributeError:
                mo = "other"
            print(f"Mo: {mo}")
            match mo:
                case 'submitting_lab':
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    print(f"{item}: {prsr.sub[item]}")
                    add_widget = QComboBox()
                    labs = [item.__str__() for item in lookup_all_orgs(ctx=self.ctx)]
                    try:
                        labs = difflib.get_close_matches(prsr.sub[item], labs, len(labs), 0)
                    except (TypeError, ValueError):
                        pass
                    add_widget.addItems(labs)
                case 'extraction_kit':
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    if prsr.sub[item] == 'nan':
                        msg = QMessageBox()
                        # msg.setIcon(QMessageBox.critical)
                        msg.setText("Error")
                        msg.setInformativeText('You need to enter a value for extraction kit.')
                        msg.setWindowTitle("Error")
                        msg.exec()
                        break
                    add_widget = QComboBox()
                    uses = [item.__str__() for item in lookup_kittype_by_use(ctx=self.ctx, used_by=prsr.sub['submission_type'])]
                    if len(uses) > 0:
                        add_widget.addItems(uses)
                    else:
                        add_widget.addItems(['bacterial_culture'])
                case 'submitted_date':
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    add_widget = QDateEdit(calendarPopup=True)
                    # add_widget.setDateTime(QDateTime.date(prsr.sub[item]))
                    add_widget.setDate(prsr.sub[item])
                case 'reagent':
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    add_widget = QComboBox()
                    add_widget.setEditable(True)
                    # Ensure that all reagenttypes have a name that matches the items in the excel parser
                    query_var = item.replace("lot_", "")
                    print(f"Query for: {query_var}")
                    if isinstance(prsr.sub[item], numpy.float64):
                        print(f"{prsr.sub[item]} is a numpy float!")
                        try:
                            prsr.sub[item] = int(prsr.sub[item])
                        except ValueError:
                            pass
                    relevant_reagents = [item.__str__() for item in lookup_regent_by_type_name_and_kit_name(ctx=self.ctx, type_name=query_var, kit_name=prsr.sub['extraction_kit'])]
                    print(f"Relevant reagents: {relevant_reagents}")
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
                    print(f"{item}: {prsr.sub[item]}")
                    self.samples = prsr.sub[item]
                case _:
                    self.table_widget.formlayout.addWidget(QLabel(item.replace("_", " ").title()))
                    add_widget = QLineEdit()
                    add_widget.setText(str(prsr.sub[item]).replace("_", " "))
            self.table_widget.formlayout.addWidget(add_widget)
        submit_btn = QPushButton("Submit")
        self.table_widget.formlayout.addWidget(submit_btn)
        submit_btn.clicked.connect(self.submit_new_sample)


    def renderPage(self):
        """
        Test function for plotly chart rendering
        """        
        df = pd.read_excel("C:\\Users\\lwark\\Desktop\\test_df.xlsx", engine="openpyxl")
        fig = px.bar(df, x="submitted_date", y="kraken_percent", color="genus", title="Long-Form Input")
        fig.update_layout(
            xaxis_title="Submitted Date (* - Date parsed from fastq file creation date)",
            yaxis_title="Kraken Percent",
            showlegend=True,
            barmode='stack'
        )
        html = '<html><body>'
        html += plotly.offline.plot(fig, output_type='div', include_plotlyjs='cdn', auto_open=True, image = 'png', image_filename='plot_image')
        html += '</body></html>'
        self.table_widget.webengineview.setHtml(html)
        self.table_widget.webengineview.update()
        # type = self.table_widget.control_typer.currentText()
        # mode = self.table_widget.mode_typer.currentText()
        # controls = get_all_controls_by_type(ctx=self.ctx, type=type)
        # data = []
        # for control in controls:
        #     dicts = convert_control_by_mode(ctx=self.ctx, control=control, mode=mode)
        #     data.append(dicts)
        # data = [item for sublist in data for item in sublist]
        # # print(data)
        # df = convert_data_list_to_df(ctx=self.ctx, input=data)
        # fig = create_charts(ctx=self.ctx, df=df)
        
        # print(fig)
        # html = '<html><body>'
        # html += plotly.offline.plot(fig, output_type='div', auto_open=True, image = 'png', image_filename='plot_image')
        # html += '</body></html>'
        # html = plotly.io.to_html(fig)
        # # print(html)
        # # with open("C:\\Users\\lwark\\Desktop\\test.html", "w") as f:
        # #     f.write(html)
        # self.table_widget.webengineview.setHtml(html)
        # self.table_widget.webengineview.update()


    def submit_new_sample(self):
        labels, values = self.extract_form_info(self.table_widget.tab1)
        info = {item[0]:item[1] for item in zip(labels, values) if not item[0].startswith("lot_")}
        reagents = {item[0]:item[1] for item in zip(labels, values) if item[0].startswith("lot_")}
        logger.debug(f"Reagents: {reagents}")
        parsed_reagents = []
        for reagent in reagents:
            wanted_reagent = lookup_reagent(ctx=self.ctx, reagent_lot=reagents[reagent])
            logger.debug(wanted_reagent)
            if wanted_reagent == None:
                dlg = AddReagentQuestion(reagent_type=reagent, reagent_lot=reagents[reagent])
                if dlg.exec():
                    wanted_reagent = self.add_reagent(reagent_lot=reagents[reagent], reagent_type=reagent.replace("lot_", ""))
                else:
                    logger.debug("Will not add reagent.")
            if wanted_reagent != None:
                parsed_reagents.append(wanted_reagent)
                logger.debug(info)
        info['samples'] = self.samples
        base_submission = construct_submission_info(ctx=self.ctx, info_dict=info)
        for reagent in parsed_reagents:
            base_submission.reagents.append(reagent)
        result = store_submission(ctx=self.ctx, base_submission=base_submission)
        if result != None:
            msg = QMessageBox()
            # msg.setIcon(QMessageBox.critical)
            msg.setText("Error")
            msg.setInformativeText(result['message'])
            msg.setWindowTitle("Error")
            msg.exec()
        self.table_widget.sub_wid.setData()


    def add_reagent(self, reagent_lot:str|None=None, reagent_type:str|None=None):
        if isinstance(reagent_lot, bool):
            reagent_lot = ""
        dlg = AddReagentForm(ctx=self.ctx, reagent_lot=reagent_lot, reagent_type=reagent_type)
        if dlg.exec():
            labels, values = self.extract_form_info(dlg)
            info = {item[0]:item[1] for item in zip(labels, values)}
            logger.debug(f"Reagent info: {info}")
            reagent = construct_reagent(ctx=self.ctx, info_dict=info)
            store_reagent(ctx=self.ctx, reagent=reagent)
            return reagent
            

    def extract_form_info(self, object):
        labels = []
        values = []
        for item in object.layout.parentWidget().findChildren(QWidget):
            
            match item:
                case QLabel():
                    labels.append(item.text().replace(" ", "_").lower())
                case QLineEdit():
                    # ad hoc check to prevent double reporting of qdatedit under lineedit for some reason
                    if not isinstance(prev_item, QDateEdit) and not isinstance(prev_item, QComboBox) and not isinstance(prev_item, QSpinBox):
                        print(f"Previous: {prev_item}")
                        print(f"Item: {item}")
                        values.append(item.text())
                case QComboBox():
                    values.append(item.currentText())
                case QDateEdit():
                    values.append(item.date().toPyDate())
            prev_item = item
        return labels, values

    def generateReport(self):
        dlg = ReportDatePicker()
        if dlg.exec():
            labels, values = self.extract_form_info(dlg)
            info = {item[0]:item[1] for item in zip(labels, values)}
            subs = lookup_submissions_by_date_range(ctx=self.ctx, start_date=info['start_date'], end_date=info['end_date'])
            records = [item.report_dict() for item in subs]
            df = make_report_xlsx(records=records)
            home_dir = Path(self.ctx["directory_path"]).joinpath(f"Submissions_{info['start_date']}-{info['end_date']}.xlsx").resolve().__str__()
            fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".xlsx")[0])
            try:
                df.to_excel(fname, engine="openpyxl")
            except PermissionError:
                pass


    def add_kit(self):
        home_dir = str(Path(self.ctx["directory_path"]))
        fname = Path(QFileDialog.getOpenFileName(self, 'Open file', home_dir, filter = "yml(*.yml)")[0])
        assert fname.exists()
        try:
            with open(fname.__str__(), "r") as stream:
                try:
                    exp = yaml.load(stream, Loader=yaml.Loader)
                except yaml.YAMLError as exc:
                    logger.error(f'Error reading yaml file {fname}: {exc}')
                    return {}
        except PermissionError:
            return
        create_kit_from_yaml(ctx=self.ctx, exp=exp)


    def controls_getter(self):
        # self.table_widget.webengineview.setHtml("")
        try:
            self.table_widget.sub_typer.disconnect()
        except TypeError:
            pass
        if self.table_widget.datepicker.start_date.date() > self.table_widget.datepicker.end_date.date():
            print("that is not allowed!")
            # self.table_widget.datepicker.start_date.setDate(e_date)
            threemonthsago = self.table_widget.datepicker.end_date.date().addDays(-90)
            with QSignalBlocker(self.table_widget.datepicker.start_date) as blocker:
                self.table_widget.datepicker.start_date.setDate(threemonthsago)
            self.controls_getter()
            return
        self.start_date = self.table_widget.datepicker.start_date.date().toPyDate()
        self.end_date = self.table_widget.datepicker.end_date.date().toPyDate()
        self.con_type = self.table_widget.control_typer.currentText()
        self.mode = self.table_widget.mode_typer.currentText()
        self.table_widget.sub_typer.clear()
        sub_types = get_control_subtypes(ctx=self.ctx, type=self.con_type, mode=self.mode)
        if sub_types != []:
            with QSignalBlocker(self.table_widget.sub_typer) as blocker: 
                self.table_widget.sub_typer.addItems(sub_types)
            self.table_widget.sub_typer.setEnabled(True)
            self.table_widget.sub_typer.currentTextChanged.connect(self.chart_maker)
        else:
           
            self.table_widget.sub_typer.clear()
            self.table_widget.sub_typer.setEnabled(False)
        self.chart_maker()
        
        
    def chart_maker(self):
        print(f"Control getter context: \n\tControl type: {self.con_type}\n\tMode: {self.mode}\n\tStart Date: {self.start_date}\n\tEnd Date: {self.end_date}")
        if self.table_widget.sub_typer.currentText() == "":
            self.subtype = None
        else:
            self.subtype = self.table_widget.sub_typer.currentText()
        print(f"Subtype: {self.subtype}")
        controls = get_all_controls_by_type(ctx=self.ctx, con_type=self.con_type, start_date=self.start_date, end_date=self.end_date)
        if controls == None:
            return
        data = []
        for control in controls:
            dicts = convert_control_by_mode(ctx=self.ctx, control=control, mode=self.mode)
            data.append(dicts)
        data = [item for sublist in data for item in sublist]
        # print(data)
        df = convert_data_list_to_df(ctx=self.ctx, input=data, subtype=self.subtype)
        if self.subtype == None:
            title = self.mode
        else:
            title = f"{self.mode} - {self.subtype}"
        fig = create_charts(ctx=self.ctx, df=df, ytitle=title)
        print(f"Updating figure...")
        html = '<html><body>'
        if fig != None:
            html += plotly.offline.plot(fig, output_type='div', include_plotlyjs='cdn')#, image = 'png', auto_open=True, image_filename='plot_image')
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        # with open("C:\\Users\\lwark\\Desktop\\test.html", "w") as f:
        #     f.write(html)
        self.table_widget.webengineview.setHtml(html)
        self.table_widget.webengineview.update()
        print("Figure updated... I hope.")


    # def datechange(self):
        
    #     s_date = self.table_widget.datepicker.start_date.date()
    #     e_date = self.table_widget.datepicker.end_date.date()
    #     if s_date > e_date:
    #         print("that is not allowed!")
    #         # self.table_widget.datepicker.start_date.setDate(e_date)
    #         threemonthsago = e_date.addDays(-90)
    #         self.table_widget.datepicker.start_date.setDate(threemonthsago)
    #     self.chart_maker()

        
   
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
        
        # Create first tab
        # self.scroller = QWidget()
        # self.scroller.layout = QVBoxLayout(self)
        # self.scroller.setLayout(self.scroller.layout)
        # self.tab1.setMaximumHeight(1000)

        self.formwidget = QWidget(self)
        self.formlayout = QVBoxLayout(self)
        self.formwidget.setLayout(self.formlayout)
        self.formwidget.setFixedWidth(300)

        self.sheetwidget = QWidget(self)
        self.sheetlayout = QVBoxLayout(self)
        self.sheetwidget.setLayout(self.sheetlayout)
        self.sub_wid = SubmissionsSheet(parent.ctx)
        self.sheetlayout.addWidget(self.sub_wid)


        self.tab1.layout = QHBoxLayout(self)
        self.tab1.setLayout(self.tab1.layout)
        # self.tab1.layout.addLayout(self.formlayout)
        self.tab1.layout.addWidget(self.formwidget)
        self.tab1.layout.addWidget(self.sheetwidget)
        # self.tab1.layout.addLayout(self.sheetlayout)
        # self.tab1.setWidgetResizable(True)
        # self.tab1.setVerticalScrollBar(QScrollBar())
        # self.tab1.layout.addWidget(self.scroller)
        # self.tab1.setWidget(self.scroller)
        # self.tab1.setMinimumHeight(300)
        self.datepicker = ControlsDatePicker()
        self.webengineview = QWebEngineView()
        # data = '''<html>Hello World</html>'''
        # self.webengineview.setHtml(data)
        self.tab2.layout = QVBoxLayout(self)
        self.control_typer = QComboBox()
        con_types = get_all_Control_Types_names(ctx=parent.ctx)
        self.control_typer.addItems(con_types)
        self.mode_typer = QComboBox()
        mode_types = get_all_available_modes(ctx=parent.ctx)
        self.mode_typer.addItems(mode_types)
        self.sub_typer = QComboBox()
        self.sub_typer.setEnabled(False)
        self.tab2.layout.addWidget(self.datepicker)
        self.tab2.layout.addWidget(self.control_typer)
        self.tab2.layout.addWidget(self.mode_typer)
        self.tab2.layout.addWidget(self.sub_typer)
        self.tab2.layout.addWidget(self.webengineview)
        self.tab2.setLayout(self.tab2.layout)
        # Add tabs to widget
        adder = KitAdder(parent_ctx=parent.ctx)
        self.tab3.layout = QVBoxLayout(self)
        self.tab3.layout.addWidget(adder)
        self.tab3.setLayout(self.tab3.layout)
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
