"""
Construct turnaround time charts
"""
from pprint import pformat
from . import CustomFigure
from PyQt6.QtWidgets import QWidget
import logging, plotly.express as px, pandas as pd

logger = logging.getLogger(f"submissions.{__name__}")


class TurnaroundChart(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, threshold: float | None = None,
                 ytitle: str | None = None,
                 parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes, settings=settings)
        self.df = df
        self.construct_chart()
        if threshold:
            self.add_hline(y=threshold)
        self.update_layout(showlegend=False)

    def construct_chart(self, df: pd.DataFrame | None = None):
        if df:
            self.df = df
        try:
            self.df = self.df[self.df.days.notnull()]
            self.df = self.df.sort_values(['submitted_date', 'name'], ascending=[True, True]).reset_index(drop=True)
            self.df = self.df.reset_index().rename(columns={"index": "idx"})
            scatter = px.scatter(data_frame=self.df, x='idx', y="days",
                                 hover_data=["name", "submitted_date", "completed_date", "days"],
                                 color="acceptable", color_discrete_map={True: "green", False: "red"}
                                 )
        except (ValueError, AttributeError):
            scatter = px.scatter()
        self.add_traces(scatter.data)
        self.update_traces(marker={'size': 15})
        try:
            tickvals = self.df['idx'].tolist()
        except KeyError:
            tickvals = []
        try:
            ticklabels = self.df['name'].tolist()
        except KeyError:
            ticklabels = []
        self.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticklabels,
            )
        )
