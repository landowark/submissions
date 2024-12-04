from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton
from tools import Report
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
        self.datepicker = StartEndDatePicker(default_start=-31)
        self.webview = QWebEngineView()
        self.datepicker.start_date.dateChanged.connect(self.date_changed)
        self.datepicker.end_date.dateChanged.connect(self.date_changed)
        self.layout = QGridLayout(self)
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        self.save_excel_button = QPushButton("Save Excel", parent=self)
        self.save_excel_button.pressed.connect(self.save_excel)
        self.save_pdf_button = QPushButton("Save PDF", parent=self)
        self.save_pdf_button.pressed.connect(self.save_pdf)
        self.layout.addWidget(self.save_excel_button, 0, 2, 1, 1)
        self.layout.addWidget(self.save_pdf_button, 0, 3, 1, 1)
        self.layout.addWidget(self.webview, 2, 0, 1, 4)
        self.setLayout(self.layout)

    def date_changed(self):
        self.start_date = self.datepicker.start_date.date().toPyDate()
        self.end_date = self.datepicker.end_date.date().toPyDate()

    def save_excel(self):
        fname = select_save_file(self, default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}", extension="xlsx")
        self.report_obj.write_report(fname, obj=self)

    def save_pdf(self):
        fname = select_save_file(obj=self,
                                 default_name=f"Report {self.start_date.strftime('%Y%m%d')} - {self.end_date.strftime('%Y%m%d')}",
                                 extension="pdf")
        save_pdf(obj=self.webview, filename=fname)