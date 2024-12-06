from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QLabel, QComboBox
from .info_tab import InfoPane
from backend.excel.reports import TurnaroundMaker
from pandas import DataFrame
from backend.db import BasicSubmission, SubmissionType
from frontend.visualizations.turnaround_chart import TurnaroundChart
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class TurnaroundTime(InfoPane):

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.save_button.pressed.connect(self.save_png)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.export_button.pressed.connect(self.save_excel)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        self.fig = None
        self.report_object = None
        self.submission_typer = QComboBox(self)
        subs = ["All"] + [item.name for item in SubmissionType.query()]
        self.submission_typer.addItems(subs)
        self.layout.addWidget(self.submission_typer, 1, 1, 1, 3)
        self.submission_typer.currentTextChanged.connect(self.update_data)
        self.update_data()

    def update_data(self):
        super().update_data()
        chart_settings = dict(start_date=self.start_date, end_date=self.end_date)
        if self.submission_typer.currentText() == "All":
            submission_type = None
            subtype_obj = None
        else:
            submission_type = self.submission_typer.currentText()
            subtype_obj = SubmissionType.query(name = submission_type)
        self.report_obj = TurnaroundMaker(start_date=self.start_date, end_date=self.end_date, submission_type=submission_type)
        if subtype_obj:
            threshold = subtype_obj.defaults['turnaround_time'] + 0.5
        else:
            threshold = None
        self.fig = TurnaroundChart(df=self.report_obj.df, settings=chart_settings, modes=[], threshold=threshold)
        self.webview.setHtml(self.fig.to_html())
