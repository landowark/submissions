from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QLabel
from .info_tab import InfoPane
from backend.excel.reports import TurnaroundMaker
from pandas import DataFrame
from backend.db import BasicSubmission
from frontend.visualizations.turnaround_chart import TurnaroundChart
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class TurnaroundTime(InfoPane):

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.chart = None
        self.report_object = None
        self.date_changed()

    def date_changed(self):
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            logger.warning("Start date after end date is not allowed!")
            lastmonth = self.datepicker.end_date.date().addDays(-31)
            # NOTE: block signal that will rerun controls getter and set start date
            # Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(lastmonth)
            self.date_changed()
            return
        super().date_changed()
        chart_settings = dict(start_date=self.start_date, end_date=self.end_date)
        self.report_obj = TurnaroundMaker(start_date=self.start_date, end_date=self.end_date)
        self.chart = TurnaroundChart(df=self.report_obj.df, settings=chart_settings, modes=[])
        self.webview.setHtml(self.chart.to_html())
