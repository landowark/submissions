"""
Functions for constructing irida control graphs using plotly.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from plotly.express import bar as pxbar
from pandas import DataFrame, to_numeric as pd_to_numeric
from . import CustomFigure
from tools import get_unique_values_in_df_column


class IridaFigure(CustomFigure):

    def __init__(self, df: DataFrame, modes: list, settings: dict, **kwargs):

        super().__init__(df=df, modes=modes, settings=settings, **kwargs)
        self.df = df
        self.construct_chart(df=df, modes=modes, start_date=settings['start_date'], end_date=settings['end_date'])

    def construct_chart(self, df: DataFrame, modes: list, **kwargs):
        """
        Creates a plotly chart for control from a pandas dataframe

        Args:
            end_date ():
            start_date ():
            df (DataFrame): input dataframe of control
            modes (list): analysis modes to construct charts for
            ytitle (str | None, optional): title on the y-axis. Defaults to None.

        Returns:
            Figure: output stacked bar chart.
        """
        for ii, mode in enumerate(modes):
            if "count" in mode:
                df[mode] = pd_to_numeric(df[mode], errors='coerce')
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
            # NOTE April 24th and 30 not in this df.
            bar = pxbar(df,
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