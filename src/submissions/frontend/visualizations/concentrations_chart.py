"""
Construct BC control concentration charts
"""
from pprint import pformat
from . import ResultsFigure
import logging, sys, plotly.express as px
import pandas as pd
from operator import itemgetter

logger = logging.getLogger(f"submissions.{__name__}")


class ConcentrationsChart(ResultsFigure):

    def __init__(self, df: pd.DataFrame, settings: dict, **kwargs):
        super().__init__(df=df, settings=settings, **kwargs)
        
    def construct_chart(self, df: pd.DataFrame | None = None,  **kwargs):
        
        check = super().construct_chart(df=df, **kwargs)
        if not check:
            scatter = px.scatter()
            hover_template = None
        else:
            hover_template = (
                "<b>Sample: %{customdata[1]}</b><br>"
                "Procedure: %{customdata[3]}<br>"
                "Concentration: %{y:,.2f}ng/uL<br>"
                "Date: %{customdata[0]}<extra></extra>"
            )
            scatter = px.scatter(
                data_frame=self.df,
                x='x_pos',
                y="original_sample_conc.",
                custom_data=['submitted_date', 'sample_id', 'original_sample_conc.', 'procedure'],
                color="control_type",
                color_discrete_map={"Positive Control": "red", "Negative Control": "green", "Sample":"orange"}
            )
        # NOTE: For some reason if data is allowed to sort itself it leads to wrong ordering of x axis.
        traces = sorted(scatter.data, key=itemgetter("name"))
        for trace in traces:
            self.add_trace(trace)

        if hover_template is not None:
            self.update_traces(hovertemplate=hover_template)
            self.update_layout(hovermode='closest')

        self.update_yaxes(title_text="Original Sample Concentration (ng/uL)")
        # Map the numeric ticks back to readable dates
        unique_days = self.df[['x_pos', 'procedure']].drop_duplicates()
        self.update_xaxes(
            type='linear',
            tickmode='array',
            tickvals=unique_days['x_pos'].tolist(),
            ticktext=unique_days['procedure'].tolist(),
        )
        self.update_traces(marker={'size': 15})
