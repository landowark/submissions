"""
Functions for constructing irida control graphs using plotly.
"""
from pprint import pformat
from . import CustomFigure
import logging, plotly.express as px, pandas as pd

logger = logging.getLogger(f"submissions.{__name__}")


class PCRFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, **kwargs):
        super().__init__(df=df, modes=modes, settings=settings, **kwargs)
        self.df = df
        self.construct_chart(df=df)

    def construct_chart(self, df: pd.DataFrame):
        try:
            scatter = px.scatter(data_frame=df, x='submitted_date', y="ct",
                                           hover_data=["name", "target", "ct", "reagent_lot"],
                                           color="target")
        except ValueError:
            scatter = px.scatter()
        self.add_traces(scatter.data)
        self.update_traces(marker={'size': 15})
