'''
Contains all operations for creating charts, graphs and visual effects.
'''
from datetime import timedelta

from PyQt6.QtWidgets import QWidget
import plotly, logging
from plotly.graph_objects import Figure
import pandas as pd
from frontend.widgets.functions import select_save_file

logger = logging.getLogger(f"submissions.{__name__}")


class CustomFigure(Figure):

    df = None

    def __init__(self, df: pd.DataFrame, settings: dict, modes: list, ytitle: str | None = None, parent: QWidget | None = None):
        super().__init__()
        # self.settings = settings
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        self.df = df
        self.update_xaxes(range=[settings['start_date'] - timedelta(days=1), settings['end_date']])

    def save_figure(self, group_name: str = "plotly_output", parent: QWidget | None = None):
        """
        Writes plotly figure to html file.

        Args:
            figs ():
            settings (dict): settings passed down from click
            fig (Figure): input figure object
            group_name (str): controltype
        """

        output = select_save_file(obj=parent, default_name=group_name, extension="png")
        self.write_image(output.absolute().__str__(), engine="kaleido")

    def save_data(self, group_name: str = "plotly_export", parent:QWidget|None=None):
        output = select_save_file(obj=parent, default_name=group_name, extension="xlsx")
        self.df.to_excel(output.absolute().__str__(), engine="openpyxl", index=False)

    def to_html(self) -> str:
        """
        Creates final html code from plotly

        Returns:
            str: html string
        """
        html = '<html><body>'
        if self is not None:
            html += plotly.offline.plot(self, output_type='div', include_plotlyjs='cdn')
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        return html


from .irida_charts import IridaFigure
from .pcr_charts import PCRFigure
