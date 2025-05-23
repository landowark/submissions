'''
Contains all operations for creating charts, graphs and visual effects.
'''
from datetime import timedelta, date
from pathlib import Path
from typing import Generator

import plotly
from PyQt6.QtWidgets import QWidget
import pandas as pd, logging
from plotly.graph_objects import Figure
from tools import divide_chunks

logger = logging.getLogger(f"submissions.{__name__}")


class CustomFigure(Figure):

    df = None

    def __init__(self, df: pd.DataFrame, settings: dict, modes: list, ytitle: str | None = None, parent: QWidget | None = None):
        super().__init__()
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        self.df = df
        self.update_xaxes(range=[settings['start_date'] - timedelta(days=1), settings['end_date']])
        self.generic_figure_markers(modes=modes, ytitle=ytitle, months=months)

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

    @classmethod
    def make_plotly_buttons(cls, months: int = 6) -> Generator[dict, None, None]:
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

    @property
    def html(self) -> str:
        """
        Creates final html code from plotly

        Returns:
            str: html string
        """
        html = f'<html><body>'
        if self is not None:
            # NOTE: Just cannot get this load from string to freaking work.
            # html += self.to_html(include_plotlyjs='cdn', full_html=False)
            html += plotly.offline.plot(self, output_type='div', include_plotlyjs="cdn")
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        # with open("test.html", "w", encoding="utf-8") as f:
        #     f.write(html)
        return html


from .irida_charts import IridaFigure
from .pcr_charts import PCRFigure
from .concentrations_chart import ConcentrationsChart
from .turnaround_chart import TurnaroundChart
