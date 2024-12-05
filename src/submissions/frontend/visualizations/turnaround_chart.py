from pprint import pformat
from . import CustomFigure
import plotly.express as px
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QWidget
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class TurnaroundChart(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, threshold: float | None = None,
                 ytitle: str | None = None,
                 parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes, settings=settings)
        self.df = df
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        # logger.debug(f"DF: {self.df}")
        self.construct_chart()
        if threshold:
            self.add_hline(y=threshold)
        # self.update_xaxes()
        self.update_layout(showlegend=False)

    def construct_chart(self, df: pd.DataFrame | None = None):
        if df:
            self.df = df
        # logger.debug(f"PCR df:\n {df}")
        self.df = self.df[self.df.days.notnull()]
        self.df = self.df.sort_values(['submitted_date', 'name'], ascending=[True, True]).reset_index(drop=True)
        self.df = self.df.reset_index().rename(columns={"index": "idx"})
        # logger.debug(f"DF: {self.df}")
        try:
            scatter = px.scatter(data_frame=self.df, x='idx', y="days",
                                 hover_data=["name", "submitted_date", "completed_date", "days"],
                                 color="acceptable", color_discrete_map={True: "green", False: "red"}
                                 )
        except ValueError:
            scatter = px.scatter()
        self.add_traces(scatter.data)
        self.update_traces(marker={'size': 15})
        tickvals = self.df['idx'].tolist()
        ticklabels = self.df['name'].tolist()
        self.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=tickvals,
                ticktext=ticklabels,
            )
        )
