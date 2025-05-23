"""
A pane to show info e.g. cost reports and turnaround times.
"""
from datetime import date
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout
from tools import Report, report_result, Result
from .misc import StartEndDatePicker
from .functions import select_save_file, save_pdf
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class InfoPane(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.app = self.parent().parent()
        self.report = Report()
        self.datepicker = StartEndDatePicker(default_start=-180)
        self.webview = QWebEngineView()
        self.datepicker.start_date.dateChanged.connect(self.update_data)
        self.datepicker.end_date.dateChanged.connect(self.update_data)
        self.layout = QGridLayout(self)
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        # NOTE: Placed in lower row to allow for addition of custom rows.
        self.layout.addWidget(self.webview, 5, 0, 1, 4)
        self.setLayout(self.layout)

    @report_result
    def update_data(self, *args, **kwargs):
        report = Report()
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()
        # logger.debug(f"Start date: {self.start_date}, End date: {self.end_date}")
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            lastmonth = self.datepicker.end_date.date().addDays(-31)
            msg = f"Start date after end date is not allowed! Setting to {lastmonth.toString()}."
            logger.warning(msg)
            # NOTE: block signal that will rerun controls getter and set start date without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(lastmonth)
            self.update_data()
            report.add_result(Result(owner=self.__str__(), msg=msg, status="Warning"))
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

    def save_excel(self):
        fname = select_save_file(self, default_name=f"{self.__class__.__name__} Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}", extension="xlsx")
        self.report_obj.write_report(fname, obj=self)

    def save_pdf(self):
        fname = select_save_file(obj=self,
                                 default_name=f"{self.__class__.__name__} Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
                                 extension="pdf")
        save_pdf(obj=self.webview, filename=fname)

    def save_png(self):
        fname = select_save_file(obj=self,
                                 default_name=f"Plotly {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
                                 extension="png")
        self.fig.write_image(fname.absolute().__str__(), engine="kaleido")
