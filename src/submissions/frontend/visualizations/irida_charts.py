"""
Functions for constructing irida controls graphs using plotly.
"""
from datetime import date
from pprint import pformat
from typing import Generator
import plotly.express as px
import pandas as pd
from PyQt6.QtWidgets import QWidget
from . import CustomFigure
import logging
from tools import get_unique_values_in_df_column, divide_chunks

logger = logging.getLogger(f"submissions.{__name__}")


class IridaFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, ytitle: str | None = None, parent: QWidget | None = None):

        super().__init__(df=df, modes=modes, settings=settings)
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        self.construct_chart(df=df, modes=modes, start_date=settings['start_date'], end_date=settings['end_date'])
        self.generic_figure_markers(modes=modes, ytitle=ytitle, months=months)

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

    def generic_figure_markers(self, modes: list = [], ytitle: str | None = None, months: int = 6):
        """
        Adds standard layout to figure.

        Args:
            fig (Figure): Input figure.
            modes (list, optional): List of modes included in figure. Defaults to [].
            ytitle (str, optional): Title for the y-axis. Defaults to None.

        Returns:
            Figure: Output figure with updated titles, rangeslider, buttons.
        """
        if modes:
            ytitle = modes[0]
        # logger.debug("Creating visibles list for each mode.")
        self.update_layout(
            xaxis_title="Submitted Date (* - Date parsed from fastq file creation date)",
            yaxis_title=ytitle,
            showlegend=True,
            barmode='stack',
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=0.7,
                    y=1.2,
                    showactive=True,
                    buttons=[button for button in self.make_pyqt_buttons(modes=modes)],
                )
            ]
        )
        self.update_xaxes(
            rangeslider_visible=True,
            rangeselector=dict(
                buttons=[button for button in self.make_plotly_buttons(months=months)]
            )
        )
        assert isinstance(self, CustomFigure)

    def make_plotly_buttons(self, months: int = 6) -> Generator[dict, None, None]:
        """
        Creates html buttons to zoom in on date areas

        Args:
            months (int, optional): Number of months of data given. Defaults to 6.

        Yields:
            Generator[dict, None, None]: Button details.
        """        
        rng = [1]
        if months > 2:
            rng += [iii for iii in range(3, months, 3)]
        # logger.debug(f"Making buttons for months: {rng}")
        buttons = [dict(count=iii, label=f"{iii}m", step="month", stepmode="backward") for iii in rng]
        if months > date.today().month:
            buttons += [dict(count=1, label="YTD", step="year", stepmode="todate")]
        buttons += [dict(step="all")]
        for button in buttons:
            yield button

    def make_pyqt_buttons(self, modes: list) -> Generator[dict, None, None]:
        """
        Creates list of buttons with one for each mode to be used in showing/hiding mode traces.

        Args:
            modes (list): list of modes used by main parser.
            fig_len (int): number of traces in the figure

        Returns:
            Generator[dict, None, None]: list of buttons.
        """
        fig_len = len(self.data)
        if len(modes) > 1:
            for ii, mode in enumerate(modes):
                # NOTE: What I need to do is create a list of bools with the same length as the fig.data
                mode_vis = [True] * fig_len
                # NOTE: And break it into {len(modes)} chunks
                mode_vis = list(divide_chunks(mode_vis, len(modes)))
                # NOTE: Then, for each chunk, if the chunk index isn't equal to the index of the current mode, set to false
                for jj, sublist in enumerate(mode_vis):
                    if jj != ii:
                        mode_vis[jj] = [not elem for elem in mode_vis[jj]]
                # NOTE: Finally, flatten list.
                mode_vis = [item for sublist in mode_vis for item in sublist]
                # NOTE: Now, yield button to add to list
                yield dict(label=mode, method="update", args=[
                    {"visible": mode_vis},
                    {"yaxis.title.text": mode},
                ])

