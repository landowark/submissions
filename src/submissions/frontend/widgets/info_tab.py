"""
A pane to show info e.g. cost reports and turnaround times.
"""
from datetime import date, datetime
from PyQt6.QtCore import QSignalBlocker
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QGridLayout, QPushButton, QLabel
from backend.db import SubmissionType
from tools import Report, report_result, Alert
from .misc import CheckableComboBox, StartEndDatePicker
from .functions import select_save_file, save_pdf
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class InfoPane(QWidget):

    results_type = None

    def __init__(self, parent: QWidget) -> None:
        from backend.db.models import SubmissionType
        super().__init__(parent)
        # self.app = self.parent().parent()
        self.app = self.window()
        self.report = Report()
        self.datepicker = StartEndDatePicker(default_start=-180)
        self.webview = QWebEngineView()
        self.datepicker.start_date.dateChanged.connect(self.update_data)
        self.datepicker.end_date.dateChanged.connect(self.update_data)
        self.layout = QGridLayout(self)
        self.layout.addWidget(self.datepicker, 0, 0, 1, 2)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.save_button.pressed.connect(self.save_png)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.export_button.pressed.connect(self.save_excel)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        rt = SubmissionType.find_by_resultstype(self.results_type)
        if rt:
            self.layout.addWidget(QLabel("Filter by Submission Type"), 1, 0, 1, 1)
            self.submission_type = CheckableComboBox(parent=self)
            self.submission_type.model().itemChanged.connect(self.update_data)
            self.layout.addWidget(self.submission_type, 1, 1, 1, 1)
            self.submission_type.setEditable(False)
            for submission_type in rt:
                self.submission_type.addItem(submission_type.name)
        # NOTE: Placed in lower row to allow for addition of custom rows.
        self.layout.addWidget(self.webview, 6, 0, 1, 4)
        self.setLayout(self.layout)
        self.fig = None
        self.report_object = None
        self.chart_settings = {}

    def update_data(self, *args, **kwargs) -> Report | None:
        report = Report()
        if self.datepicker.start_date.date() > self.datepicker.end_date.date():
            lastmonth = self.datepicker.end_date.date().addDays(-31)
            msg = f"Start date after end date is not allowed! Setting to {lastmonth.toString()}."
            logger.warning(msg)
            # NOTE: block signal that will rerun control getter and set start date without triggering this function again
            with QSignalBlocker(self.datepicker.start_date) as blocker:
                self.datepicker.start_date.setDate(lastmonth)
            report.add_result(Alert(owner=self.__str__(), msg=msg, status="Warning"))
            # self.update_data()
        self.start_date = datetime.combine(self.datepicker.start_date.date().toPyDate(), datetime.min.time())
        self.end_date = datetime.combine(self.datepicker.end_date.date().toPyDate(), datetime.max.time())
        if hasattr(self, "submission_type"):
            self.submission_types = self.submission_type.get_checked()
        else:
            self.submission_types = [item.name for item in SubmissionType.query()]
        
    @classmethod
    def diff_month(cls, d1: date, d2: date) -> float:
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
        print(self.report_obj)
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


class PosNegPane(InfoPane):

    def __init__(self, parent: QWidget = None):
        # 1. Block parent signals temporarily during setup to prevent premature execution
        super().__init__(parent)
        self.pos_neg = CheckableComboBox(parent=self)
        self.pos_neg.model().itemChanged.connect(self.update_data)
        self.pos_neg.setEditable(False)
        # with QSignalBlocker(self.pos_neg.model()) as blocker:
        self.pos_neg.addItem("Select", header=True)
        self.pos_neg.addItem("Positive")
        self.pos_neg.addItem("Negative")
        self.pos_neg.addItem("Samples", start_checked=False)
        # 2. Connect the change signal safely after object exists
        
        # 3. Explicitly trigger initial load once fully constructed
        self.layout.addWidget(QLabel("Filter by Control Type"), 2, 0, 1, 1)
        self.layout.addWidget(self.pos_neg, 2, 1, 1, 1)
        self._initialized = True
        self.update_data()
        
    def update_data(self, *args, **kwargs) -> None:
        """
        Sets data in the info pane

        Returns:
            None
        """
<<<<<<< HEAD
        if not getattr(self, "_initialized", False):
            return super().update_data(*args, **kwargs)
        # 5. Call parent to build start_date, end_date, and submission_types safely
        super().update_data(*args, **kwargs)
        
        # 6. Guard clause to handle early initialization safely if signals bypass blockers
        if not hasattr(self, "pos_neg"):
            return 
        include = self.pos_neg.get_checked()
=======
        super().update_data()
        try:
            include = self.pos_neg.get_checked()
        except AttributeError:
            include = []
        submission_types = self.submission_type.get_checked() if hasattr(self, 'submission_type') else []
>>>>>>> b734f605ac9afa15a391470fa1b8921a92ceafc0
        months = self.diff_month(self.start_date, self.end_date)
        # 7. Store the settings as an instance attribute rather than breaking the return type
        self.chart_settings = dict(
            start_date=self.start_date, 
            end_date=self.end_date,
            include=include, 
            submission_types=self.submission_types, 
            months=months
        )
