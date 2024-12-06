"""
Handles display of control charts
"""
from datetime import date
from pprint import pformat
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QWidget, QComboBox, QPushButton, QGridLayout
)
from PyQt6.QtCore import QSignalBlocker
from backend.db import ControlType, IridaControl
import logging
from tools import Report, report_result, Result
from frontend.visualizations import CustomFigure
from .misc import StartEndDatePicker
from .info_tab import InfoPane

logger = logging.getLogger(f"submissions.{__name__}")


class ControlsViewer(QWidget):

    def __init__(self, parent: QWidget, archetype: str) -> None:
        super().__init__(parent)
        logger.debug(f"Incoming Archetype: {archetype}")
        self.archetype = ControlType.query(name=archetype)
        if not self.archetype:
            return
        logger.debug(f"Archetype set as: {self.archetype}")
        self.app = self.parent().parent()
        # logger.debug(f"\n\n{self.app}\n\n")
        self.report = Report()
        self.datepicker = StartEndDatePicker(default_start=-180)
        self.webengineview = QWebEngineView()
        # NOTE: set tab2 layout
        self.layout = QGridLayout(self)
        self.control_sub_typer = QComboBox()
        # NOTE: fetch types of controls
        con_sub_types = [item for item in self.archetype.targets.keys()]
        self.control_sub_typer.addItems(con_sub_types)
        # NOTE: create custom widget to get types of analysis -- disabled by PCR control
        self.mode_typer = QComboBox()
        mode_types = IridaControl.get_modes()
        self.mode_typer.addItems(mode_types)
        # NOTE: create custom widget to get subtypes of analysis -- disabled by PCR control
        self.mode_sub_typer = QComboBox()
        self.mode_sub_typer.setEnabled(False)
        # NOTE: add widgets to tab2 layout
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        self.layout.addWidget(self.control_sub_typer, 1, 0, 1, 4)
        self.layout.addWidget(self.mode_typer, 2, 0, 1, 4)
        self.layout.addWidget(self.mode_sub_typer, 3, 0, 1, 4)
        self.archetype.get_instance_class().make_parent_buttons(parent=self)
        self.layout.addWidget(self.webengineview, self.layout.rowCount(), 0, 1, 4)
        self.setLayout(self.layout)
        self.controls_getter_function()
        self.control_sub_typer.currentIndexChanged.connect(self.controls_getter_function)
        self.mode_typer.currentIndexChanged.connect(self.controls_getter_function)
        self.datepicker.start_date.dateChanged.connect(self.controls_getter_function)
        self.datepicker.end_date.dateChanged.connect(self.controls_getter_function)
        self.save_button.pressed.connect(self.save_chart_function)
        self.export_button.pressed.connect(self.save_data_function)

    def save_chart_function(self):
        self.fig.save_figure(parent=self)

    def save_data_function(self):
        self.fig.save_data(parent=self)

    @report_result
    def controls_getter_function(self, *args, **kwargs):
        """
        Get controls based on start/end dates
        """
        report = Report()
        # NOTE: mode_sub_type defaults to disabled
        try:
            self.mode_sub_typer.disconnect()
        except TypeError:
            pass
        # NOTE: correct start date being more recent than end date and rerun
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            threemonthsago = self.datepicker.end_date.date().addDays(-60)
            msg = f"Start date after end date is not allowed! Setting to {threemonthsago.toString()}."
            logger.warning(msg)
            # NOTE: block signal that will rerun controls getter and set start date Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(threemonthsago)
            self.controls_getter_function()
            report.add_result(Result(owner=self.__str__(), msg=msg, status="Warning"))
            return report
        # NOTE: convert to python useable date objects
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()
        self.con_sub_type = self.control_sub_typer.currentText()
        self.mode = self.mode_typer.currentText()
        self.mode_sub_typer.clear()
        # NOTE: lookup subtypes
        try:
            sub_types = self.archetype.get_modes(mode=self.mode)
        except AttributeError:
            sub_types = []
        # NOTE: added in allowed to have subtypes in case additions made in future.
        if sub_types and self.mode.lower() in self.archetype.get_instance_class().subtyping_allowed:
            # NOTE: block signal that will rerun controls getter and update mode_sub_typer
            with QSignalBlocker(self.mode_sub_typer) as blocker:
                self.mode_sub_typer.addItems(sub_types)
            self.mode_sub_typer.setEnabled(True)
            self.mode_sub_typer.currentTextChanged.connect(self.chart_maker_function)
        else:
            self.mode_sub_typer.clear()
            self.mode_sub_typer.setEnabled(False)
        self.chart_maker_function()
        return report

    @classmethod
    def diff_month(self, d1: date, d2: date) -> float:
        """
        Gets the number of months difference between two different dates

        Args:
            d1 (date): Start date.
            d2 (date): End date.

        Returns:
            float: Number of months difference
        """        
        return abs((d1.year - d2.year) * 12 + d1.month - d2.month)

    @report_result
    def chart_maker_function(self, *args, **kwargs):
        # TODO: Generalize this by moving as much code as possible to IridaControl
        """
        Create html chart for controls reporting

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """
        report = Report()
        # logger.debug(f"Control getter context: \n\tControl type: {self.con_sub_type}\n\tMode: {self.mode}\n\tStart \
        #     Date: {self.start_date}\n\tEnd Date: {self.end_date}")
        # NOTE: set the mode_sub_type for kraken
        if self.mode_sub_typer.currentText() == "":
            self.mode_sub_type = None
        else:
            self.mode_sub_type = self.mode_sub_typer.currentText()
        logger.debug(f"Subtype: {self.mode_sub_type}")
        months = self.diff_month(self.start_date, self.end_date)
        # NOTE: query all controls using the type/start and end dates from the gui
        chart_settings = dict(sub_type=self.con_sub_type, start_date=self.start_date, end_date=self.end_date,
                              mode=self.mode,
                              sub_mode=self.mode_sub_type, parent=self, months=months)
        self.fig = self.archetype.get_instance_class().make_chart(chart_settings=chart_settings, parent=self, ctx=self.app.ctx)
        if issubclass(self.fig.__class__, CustomFigure):
            self.save_button.setEnabled(True)
        # logger.debug(f"Updating figure...")
        # NOTE: construct html for webview
        html = self.fig.to_html()
        # logger.debug(f"The length of html code is: {len(html)}")
        self.webengineview.setHtml(html)
        self.webengineview.update()
        # logger.debug("Figure updated... I hope.")
        return report
