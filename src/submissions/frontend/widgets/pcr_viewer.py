from tools import report_result
from frontend.widgets.info_tab import PosNegPane
from backend.excel.reports import PCRMaker
from frontend.visualizations.pcr_charts import PCRFigure
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class PCRViewer(PosNegPane):

    results_type = "Diomni PCR"

    def update_data(self) -> None:
        """
        Sets data in the info pane
        
        """
        super().update_data()
        try:
            self.report_obj = PCRMaker(**self.chart_settings)    
        except (AttributeError, TypeError) as e:
            logger.error(f"Error occurred while creating concentration report: {e}")
            self.report_obj = None
        if self.report_obj is None or self.report_obj.df.empty:
            logger.warning("No data available for the selected date range and control types.")
            self.webview.setHtml("<h3>No data available for the selected date range and control types.</h3>")
            return
        self.fig = PCRFigure(df=self.report_obj.df, settings=self.chart_settings)

        self.webview.setHtml(self.fig.html)   

__all__ = ["PCRViewer"]