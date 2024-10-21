"""
Functions for constructing irida controls graphs using plotly.
"""
from pprint import pformat

from plotly.graph_objs import FigureWidget, Scatter

from . import CustomFigure
import plotly.express as px
import pandas as pd
from PyQt6.QtWidgets import QWidget
import logging

logger = logging.getLogger(f"submissions.{__name__}")

# NOTE: For click events try (haven't got working yet) ipywidgets >=7.0.0 required for figurewidgets:
# https://plotly.com/python/click-events/


class PCRFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, ytitle: str | None = None, parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes)
        logger.debug(f"DF: {self.df}")
        self.construct_chart(df=df)

    def hello(self):
        print("hello")

    def construct_chart(self, df: pd.DataFrame):
        logger.debug(f"PCR df:\n {df}")
        try:
            express = px.scatter(data_frame=df, x='submitted_date', y="ct",
                                           hover_data=["name", "target", "ct", "reagent_lot"],
                                           color="target")
        except ValueError:
            express = px.scatter()
        scatter = FigureWidget([datum for datum in express.data])
        self.add_traces(scatter.data)
        self.update_traces(marker={'size': 15})


