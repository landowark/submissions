"""
Pane showing BC control concentrations summary.
"""
from PyQt6.QtWidgets import QWidget, QPushButton, QCheckBox, QLabel
from .info_tab import InfoPane
from backend.excel.reports import ConcentrationMaker
from frontend.visualizations.concentrations_chart import ConcentrationsChart
import logging


logger = logging.getLogger(f"submissions.{__name__}")


class Concentrations(InfoPane):

    def __init__(self, parent: QWidget):
        from .. import CheckableComboBox
        super().__init__(parent)
        self.save_button = QPushButton("Save Chart", parent=self)
        self.save_button.pressed.connect(self.save_png)
        self.layout.addWidget(self.save_button, 0, 2, 1, 1)
        self.export_button = QPushButton("Save Data", parent=self)
        self.export_button.pressed.connect(self.save_excel)
        self.layout.addWidget(self.export_button, 0, 3, 1, 1)
        self.pos_neg = CheckableComboBox(parent=self)
        self.pos_neg.model().itemChanged.connect(self.update_data)
        self.pos_neg.setEditable(False)
        self.pos_neg.addItem("Positive")
        self.pos_neg.addItem("Negative")
        self.pos_neg.addItem("Samples", start_checked=False)
        self.layout.addWidget(QLabel("Control Types"), 1, 0, 1, 1)
        self.layout.addWidget(self.pos_neg, 1, 1, 1, 1)
        self.fig = None
        self.report_object = None
        self.update_data()

    def update_data(self) -> None:
        """
        Sets data in the info pane

        Returns:
            None
        """
        include = self.pos_neg.get_checked()
        # logger.debug(f"Include: {include}")
        super().update_data()
        months = self.diff_month(self.start_date, self.end_date)
        # logger.debug(f"Box checked: {self.all_box.isChecked()}")
        # chart_settings = dict(start_date=self.start_date, end_date=self.end_date, controls_only=self.all_box.isChecked())
        chart_settings = dict(start_date=self.start_date, end_date=self.end_date,
                              include=include)
        self.report_obj = ConcentrationMaker(**chart_settings)
        self.fig = ConcentrationsChart(df=self.report_obj.df, settings=chart_settings, modes=[], months=months)
        self.webview.setHtml(self.fig.html)
