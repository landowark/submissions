'''
Contains all operations for creating charts, graphs and visual effects.
'''
from PyQt6.QtWidgets import QWidget
import plotly
from plotly.graph_objects import Figure
import pandas as pd
from frontend.widgets.functions import select_save_file


class CustomFigure(Figure):

    df = None

    def __init__(self, df: pd.DataFrame, modes: list, ytitle: str | None = None, parent: QWidget | None = None,
                 months: int = 6):
        super().__init__()
        self.df = df

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

        Args:
            figure (Figure): input figure

        Returns:
            str: html string
        """
        html = '<html><body>'
        if self is not None:
            html += plotly.offline.plot(self, output_type='div',
                                        include_plotlyjs='cdn')  #, image = 'png', auto_open=True, image_filename='plot_image')
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        return html


from .irida_charts import IridaFigure
from .pcr_charts import PCRFigure
