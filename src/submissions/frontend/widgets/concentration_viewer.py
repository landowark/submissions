"""
Pane showing BC control concentrations summary.
"""
from tools import report_result

from .info_tab import PosNegPane
from backend.excel.reports import ConcentrationMaker
from frontend.visualizations.concentrations_chart import ConcentrationsChart
import logging


logger = logging.getLogger(f"submissions.{__name__}")


class ConcentrationViewer(PosNegPane):

    results_type = "Qubit"

    def update_data(self) -> None:
        """
        Sets data in the info pane

        Returns:
            None
        """

        super().update_data()
        try:
            self.report_obj = ConcentrationMaker(**self.chart_settings)
        except (TypeError,  AttributeError) as e:
            self.report_obj = None
        if self.report_obj is None or self.report_obj.df.empty:
            self.webview.setHtml("<h3>No data available for the selected date range and control types.</h3>")
            return 
        self.fig = ConcentrationsChart(df=self.report_obj.df, settings=self.chart_settings)
        self.webview.setHtml(self.fig.html)
        