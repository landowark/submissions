from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QComboBox, QHBoxLayout,
    QDateEdit, QLabel, QSizePolicy
)
from PyQt6.QtCore import QSignalBlocker
from backend.db import ControlType, Control
from PyQt6.QtCore import QDate, QSize
import logging
from tools import Report, Result
from backend.excel.reports import convert_data_list_to_df
from frontend.visualizations.control_charts import create_charts, construct_html

logger = logging.getLogger(f"submissions.{__name__}")

class ControlsViewer(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.app = self.parent().parent()
        print(f"\n\n{self.app}\n\n")
        self.report = Report()
        self.datepicker = ControlsDatePicker()
        self.webengineview = QWebEngineView()
        # set tab2 layout
        self.layout = QVBoxLayout(self)
        self.control_typer = QComboBox()
        # fetch types of controls 
        con_types = [item.name for item in ControlType.query()]
        self.control_typer.addItems(con_types)
        # create custom widget to get types of analysis
        self.mode_typer = QComboBox()
        mode_types = Control.get_modes()
        self.mode_typer.addItems(mode_types)
        # create custom widget to get subtypes of analysis
        self.sub_typer = QComboBox()
        self.sub_typer.setEnabled(False)
        # add widgets to tab2 layout
        self.layout.addWidget(self.datepicker)
        self.layout.addWidget(self.control_typer)
        self.layout.addWidget(self.mode_typer)
        self.layout.addWidget(self.sub_typer)
        self.layout.addWidget(self.webengineview)
        self.setLayout(self.layout)
        self.controls_getter()
        self.control_typer.currentIndexChanged.connect(self.controls_getter)
        self.mode_typer.currentIndexChanged.connect(self.controls_getter)
        self.datepicker.start_date.dateChanged.connect(self.controls_getter)
        self.datepicker.end_date.dateChanged.connect(self.controls_getter)

    def controls_getter(self):
        """
        Lookup controls from database and send to chartmaker
        """    
        self.controls_getter_function()
        
    def chart_maker(self):
        """
        Creates plotly charts for webview
        """   
        self.chart_maker_function()     

    def controls_getter_function(self):
        """
        Get controls based on start/end dates
        """    
        report = Report()
        # subtype defaults to disabled  
        try:
            self.sub_typer.disconnect()
        except TypeError:
            pass
        # correct start date being more recent than end date and rerun
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            logger.warning("Start date after end date is not allowed!")
            threemonthsago = self.datepicker.end_date.date().addDays(-60)
            # block signal that will rerun controls getter and set start date
            # Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(threemonthsago)
            self.controls_getter()
            self.report.add_result(report)
            return
        # convert to python useable date objects
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()
        self.con_type = self.control_typer.currentText()
        self.mode = self.mode_typer.currentText()
        self.sub_typer.clear()
        # lookup subtypes
        sub_types = ControlType.query(name=self.con_type).get_subtypes(mode=self.mode)
        if sub_types != []:
            # block signal that will rerun controls getter and update sub_typer
            with QSignalBlocker(self.sub_typer) as blocker: 
                self.sub_typer.addItems(sub_types)
            self.sub_typer.setEnabled(True)
            self.sub_typer.currentTextChanged.connect(self.chart_maker)
        else:
            self.sub_typer.clear()
            self.sub_typer.setEnabled(False)
        self.chart_maker()
        self.report.add_result(report)
        
    def chart_maker_function(self):
        """
        Create html chart for controls reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        logger.debug(f"Control getter context: \n\tControl type: {self.con_type}\n\tMode: {self.mode}\n\tStart Date: {self.start_date}\n\tEnd Date: {self.end_date}")
        # set the subtype for kraken
        if self.sub_typer.currentText() == "":
            self.subtype = None
        else:
            self.subtype = self.sub_typer.currentText()
        logger.debug(f"Subtype: {self.subtype}")
        # query all controls using the type/start and end dates from the gui
        controls = Control.query(control_type=self.con_type, start_date=self.start_date, end_date=self.end_date)
        # if no data found from query set fig to none for reporting in webview
        if controls == None:
            fig = None
        else:
            # change each control to list of dictionaries
            data = [control.convert_by_mode(mode=self.mode) for control in controls]
            # flatten data to one dimensional list
            data = [item for sublist in data for item in sublist]
            logger.debug(f"Control objects going into df conversion: {type(data)}")
            if data == []:
                self.report.add_result(Result(status="Critical", msg="No data found for controls in given date range."))
                return
            # send to dataframe creator
            df = convert_data_list_to_df(input=data, subtype=self.subtype)
            if self.subtype == None:
                title = self.mode
            else:
                title = f"{self.mode} - {self.subtype}"
            # send dataframe to chart maker
            fig = create_charts(ctx=self.app.ctx, df=df, ytitle=title)
        logger.debug(f"Updating figure...")
        # construct html for webview
        html = construct_html(figure=fig)
        logger.debug(f"The length of html code is: {len(html)}")
        self.webengineview.setHtml(html)
        self.webengineview.update()
        logger.debug("Figure updated... I hope.")
        self.report.add_result(report)

class ControlsDatePicker(QWidget):
    """
    custom widget to pick start and end dates for controls graphs
    """    
    def __init__(self) -> None:
        super().__init__()
        self.start_date = QDateEdit(calendarPopup=True)
        # start date is two months prior to end date by default
        twomonthsago = QDate.currentDate().addDays(-60)
        self.start_date.setDate(twomonthsago)
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDate(QDate.currentDate())
        self.layout = QHBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(self.start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(self.end_date)
        self.setLayout(self.layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(80,20)  
