from pprint import pformat
from . import CustomFigure
import plotly.express as px
import pandas as pd
import numpy as np
from PyQt6.QtWidgets import QWidget
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class TurnaroundChart(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, ytitle: str | None = None,
                 parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes, settings=settings)
        try:
            months = int(settings['months'])
        except KeyError:
            months = 6
        # logger.debug(f"DF: {self.df}")
        self.construct_chart(df=df)
        self.add_hline(y=3.5)
        # self.update_xaxes()
        self.update_layout(showlegend=False)

    def construct_chart(self, df: pd.DataFrame):
        # logger.debug(f"PCR df:\n {df}")
        df = df.sort_values(by=['submitted_date', 'name'])
        try:
            scatter = px.scatter(data_frame=df, x='name', y="days",
                                 hover_data=["name", "submitted_date", "completed_date", "days"],
                                 color="acceptable", color_discrete_map={True: "green", False: "red"}
                                 )
        except ValueError:
            scatter = px.scatter()
        self.add_traces(scatter.data)
        self.update_traces(marker={'size': 15})
