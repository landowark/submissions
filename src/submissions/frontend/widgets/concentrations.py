"""
Pane showing BC control concentrations summary.
"""
from PyQt6.QtWidgets import QWidget, QPushButton
from .info_tab import InfoPane
from backend.excel.reports import ConcentrationMaker
from frontend.visualizations.concentrations_chart import ConcentrationsChart
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class Concentrations(InfoPane):

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
        self.update_data()

    def update_data(self) -> None:
        """
        Sets data in the info pane

        Returns:
            None
        """
        super().update_data()
        months = self.diff_month(self.start_date, self.end_date)
        chart_settings = dict(start_date=self.start_date, end_date=self.end_date)
        self.report_obj = ConcentrationMaker(**chart_settings)
        self.fig = ConcentrationsChart(df=self.report_obj.df, settings=chart_settings, modes=[], months=months)
        self.webview.setHtml(self.fig.html)
