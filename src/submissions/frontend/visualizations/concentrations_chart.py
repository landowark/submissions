"""
Construct BC control concentration charts
"""
from pprint import pformat
from . import CustomFigure
import plotly.express as px
import pandas as pd
from PyQt6.QtWidgets import QWidget
import logging
from operator import itemgetter

logger = logging.getLogger(f"submissions.{__name__}")


class ConcentrationsChart(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict,
                 ytitle: str | None = None,
                 parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes, settings=settings)
        self.df = df
        self.construct_chart()
        self.update_layout(showlegend=False)

    def construct_chart(self, df: pd.DataFrame | None = None):
        if df:
            self.df = df
        try:
            self.df = self.df[self.df.concentration.notnull()]
            self.df = self.df.sort_values(['submitted_date', 'submission'], ascending=[True, True]).reset_index(
                drop=True)
            self.df = self.df.reset_index().rename(columns={"index": "idx"})
            # logger.debug(f"DF after changes:\n{self.df}")
            scatter = px.scatter(data_frame=self.df, x='submission', y="concentration",
                                 hover_data=["name", "submission", "submitted_date", "concentration"],
                                 color="positive", color_discrete_map={True: "red", False: "green"}
                                 )
        except (ValueError, AttributeError) as e:
            logger.error(f"Error constructing chart: {e}")
            scatter = px.scatter()
        # NOTE: For some reason if data is allowed to sort itself it leads to wrong ordering of x axis.
        traces = sorted(scatter.data, key=itemgetter("name"))
        for trace in traces:
            self.add_trace(trace)
        try:
            tickvals = self.df['submission'].tolist()
        except KeyError:
            tickvals = []
        try:
            ticklabels = self.df['submission'].tolist()
        except KeyError:
            ticklabels = []
        self.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticklabels,
            ),
            yaxis=dict(
                rangemode="nonnegative"
            )
        )
        self.update_traces(marker={'size': 15})
