"""
Functions for constructing irida controls graphs using plotly.
"""
from datetime import date
from pprint import pformat
import plotly
from . import CustomFigure
import plotly.express as px
import pandas as pd
from PyQt6.QtWidgets import QWidget
from plotly.graph_objects import Figure
import logging
from tools import get_unique_values_in_df_column, divide_chunks
from frontend.widgets.functions import select_save_file

logger = logging.getLogger(f"submissions.{__name__}")


class PCRFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, ytitle: str | None = None, parent: QWidget | None = None,
                 months: int = 6):
        super().__init__(df=df, modes=modes)
        logger.debug(f"DF: {self.df}")
        self.construct_chart(df=df)
        # self.generic_figure_markers(modes=modes, ytitle=ytitle, months=months)

    def construct_chart(self, df: pd.DataFrame):
        logger.debug(f"PCR df: {df}")
        try:
            scatter = px.scatter(data_frame=df, x='submitted_date', y="ct", hover_data=["name", "target", "ct", "reagent_lot"], color='target')
        except ValueError:
            scatter = px.scatter()
        self.add_traces(scatter.data)

