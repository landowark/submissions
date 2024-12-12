"""
Functions for constructing irida controls graphs using plotly.
"""
from datetime import date
from pprint import pformat
import plotly.express as px
import pandas as pd
from PyQt6.QtWidgets import QWidget
from . import CustomFigure
import logging
from tools import get_unique_values_in_df_column

logger = logging.getLogger(f"submissions.{__name__}")


class IridaFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, ytitle: str | None = None, parent: QWidget | None = None):

        super().__init__(df=df, modes=modes, settings=settings)
        self.df = df
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        self.construct_chart(df=df, modes=modes, start_date=settings['start_date'], end_date=settings['end_date'])


    def construct_chart(self, df: pd.DataFrame, modes: list, start_date: date, end_date:date):
        """
        Creates a plotly chart for controls from a pandas dataframe

        Args:
            end_date ():
            start_date ():
            df (pd.DataFrame): input dataframe of controls
            modes (list): analysis modes to construct charts for
            ytitle (str | None, optional): title on the y-axis. Defaults to None.

        Returns:
            Figure: output stacked bar chart.
        """
        for ii, mode in enumerate(modes):
            if "count" in mode:
                df[mode] = pd.to_numeric(df[mode], errors='coerce')
                color = "genus"
                color_discrete_sequence = None
            elif 'percent' in mode:
                color = "genus"
                color_discrete_sequence = None
            else:
                color = "target"
                match get_unique_values_in_df_column(df, 'target'):
                    case ['Target']:
                        color_discrete_sequence = ["blue"]
                    case ['Off-target']:
                        color_discrete_sequence = ['red']
                    case _:
                        color_discrete_sequence = ['blue', 'red']
            bar = px.bar(df,
                         x="submitted_date",
                         y=mode,
                         color=color,
                         title=mode,
                         barmode='stack',
                         hover_data=["genus", "name", "target", mode],
                         text="genera",
                         color_discrete_sequence=color_discrete_sequence
                         )
            bar.update_traces(visible=ii == 0)
            self.add_traces(bar.data)
