"""
A pane to show info e.g. cost reports and turnaround times.
"""
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout
from tools import Report, report_result, Result
from .misc import StartEndDatePicker, save_pdf
from .functions import select_save_file
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class InfoPane(QWidget):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.app = self.parent().parent()
        # logger.debug(f"\n\n{self.app}\n\n")
        self.report = Report()
        self.datepicker = StartEndDatePicker(default_start=-180)
        self.webview = QWebEngineView()
        self.datepicker.start_date.dateChanged.connect(self.update_data)
        self.datepicker.end_date.dateChanged.connect(self.update_data)
        self.layout = QGridLayout(self)
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        self.layout.addWidget(self.webview, 4, 0, 1, 4)
        self.setLayout(self.layout)

    @report_result
    def update_data(self, *args, **kwargs):
        report = Report()
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            lastmonth = self.datepicker.end_date.date().addDays(-31)
            msg = f"Start date after end date is not allowed! Setting to {lastmonth.toString()}."
            logger.warning(msg)
            # NOTE: block signal that will rerun controls getter and set start date
            # Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(lastmonth)
            self.update_data()
            report.add_result(Result(owner=self.__str__(), msg=msg, status="Warning"))
            return report

    def save_excel(self):
        fname = select_save_file(self, default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}", extension="xlsx")
        self.report_obj.write_report(fname, obj=self)

    def save_pdf(self):
        fname = select_save_file(obj=self,
                                 default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
                                 extension="pdf")
        save_pdf(obj=self.webview, filename=fname)

    def save_png(self):
        fname = select_save_file(obj=self,
                                 default_name=f"Plotly {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
                                 extension="png")
        self.fig.write_image(fname.absolute().__str__(), engine="kaleido")