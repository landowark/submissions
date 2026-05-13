"""
Functions for constructing irida control graphs using plotly.
"""
from operator import itemgetter
from pprint import pformat
from . import ResultsFigure
import logging, plotly.express as px, pandas as pd

logger = logging.getLogger(f"submissions.{__name__}")


class PCRFigure(ResultsFigure):

    # def __init__(self, df: pd.DataFrame, settings: dict, **kwargs):
    #     df['dt_internal'] = pd.to_datetime(df["submitted_date"]).dt.normalize()
    #     start = pd.to_datetime(settings['start_date']).normalize()
    #     end = pd.to_datetime(settings['end_date']).normalize()
    #     super().__init__(df=df, settings=settings, **kwargs)
    #     self.df = df
    #     self.construct_chart(df=df)

    def construct_chart(self, df: pd.DataFrame, **kwargs):
        check = super().construct_chart(df=df, **kwargs)
        if not check:
            scatter = px.scatter()
            hover_template = None
        else:
            hover_template = (
                "<b>Sample: %{customdata[1]}</b><br>"
                "Target: %{customdata[2]}<br>"
                "Procedure: %{customdata[3]}<br>"
                "CQ Value: %{y:,.2f}<br>"
                "Date: %{customdata[0]}<extra></extra>"
            )
            scatter = px.scatter(
                data_frame=self.df, 
                x='x_pos', 
                y="cq",
                custom_data=['submitted_date', 'sample_id', 'path', 'procedure'],
                color="control_type",
                color_discrete_map={"Positive Control": "red", "Negative Control": "green", "Sample":"orange"}
            )
        self.add_traces(scatter.data)
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
