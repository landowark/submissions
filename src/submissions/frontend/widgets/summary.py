from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from .info_tab import InfoPane
from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QLabel
from backend.db import Organization
from backend.excel import ReportMaker
from tools import Report
from .misc import StartEndDatePicker, save_pdf, CheckableComboBox
from .functions import select_save_file
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class Summary(InfoPane):

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.org_select = CheckableComboBox()
        self.org_select.setEditable(False)
        self.org_select.addItem("Select", header=True)
        for org in [org.name for org in Organization.query()]:
            self.org_select.addItem(org)
        self.org_select.model().itemChanged.connect(self.date_changed)
        self.layout.addWidget(QLabel("Client"), 1, 0, 1, 1)
        self.layout.addWidget(self.org_select, 1, 1, 1, 3)
        self.date_changed()

    def date_changed(self):
        orgs = [self.org_select.itemText(i) for i in range(self.org_select.count()) if self.org_select.itemChecked(i)]
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            logger.warning("Start date after end date is not allowed!")
            lastmonth = self.datepicker.end_date.date().addDays(-31)
            # NOTE: block signal that will rerun controls getter and set start date
            # Without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(lastmonth)
            self.date_changed()
            return
        # NOTE: convert to python useable date objects
        # self.start_date = self.datepicker.start_date.date().toPyDate()
        # self.end_date = self.datepicker.end_date.date().toPyDate()
        super().date_changed()
        logger.debug(f"Getting report from {self.start_date} to {self.end_date} using {orgs}")
        self.report_obj = ReportMaker(start_date=self.start_date, end_date=self.end_date, organizations=orgs)
        self.webview.setHtml(self.report_obj.html)
        if self.report_obj.subs:
            self.save_pdf_button.setEnabled(True)
            self.save_excel_button.setEnabled(True)
        else:
            self.save_pdf_button.setEnabled(False)
            self.save_excel_button.setEnabled(False)

    # def save_excel(self):
    #     fname = select_save_file(self, default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}", extension="xlsx")
    #     self.report_obj.write_report(fname, obj=self)
    #
    # def save_pdf(self):
    #     fname = select_save_file(obj=self,
    #                              default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
    #                              extension="pdf")
    #     save_pdf(obj=self.webview, filename=fname)
