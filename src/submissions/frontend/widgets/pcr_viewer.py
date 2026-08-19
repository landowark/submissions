from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from frontend.widgets.info_tab import PosNegPane
from backend.excel.reports import PCRMaker
from frontend.visualizations.pcr_charts import PCRFigure


class PCRViewer(PosNegPane):

    results_type = "Diomni PCR"

    def update_data(self) -> None:
        """
        Sets data in the info pane
        
        """
        super().update_data()
        if not self.chart_settings:      # nothing to plot yet
            return
        try:
            self.report_obj = PCRMaker(**self.chart_settings)    
        except (AttributeError, TypeError) as e:
            logger.exception(f"Error occurred while creating concentration report: {e}")
            self.report_obj = None
        if self.report_obj is None or self.report_obj.df.empty:
            logger.warning("No data available for the selected date range and control types.")
            self.webview.setHtml("<h3>No data available for the selected date range and control types.</h3>")
            return
        self.fig = PCRFigure(df=self.report_obj.df, settings=self.chart_settings)
        self.webview.setHtml(self.fig.html)   

__all__ = ["PCRViewer"]