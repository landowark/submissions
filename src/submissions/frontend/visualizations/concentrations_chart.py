"""
Construct BC control concentration charts
"""
from pprint import pformat
from . import CustomFigure
import logging, sys, plotly.express as px
import pandas as pd
from operator import itemgetter

logger = logging.getLogger(f"submissions.{__name__}")


class ConcentrationsChart(CustomFigure):

    def __init__(self, df: pd.DataFrame, modes: list, settings: dict, **kwargs):
        df['dt_internal'] = pd.to_datetime(df["submitted_date"]).dt.normalize()
        start = pd.to_datetime(settings['start_date']).normalize()
        end = pd.to_datetime(settings['end_date']).normalize()

        # 2. Robust Jitter Calculation
        # We group by the date and rank the meta.id to ensure each unique sample 
        # on that day gets a unique integer offset (0, 1, 2...)
        
        df["original_sample_conc."] = pd.to_numeric(df["original_sample_conc."], errors='coerce').fillna(0)

        df['day_num'] = (df['dt_internal'] - start).dt.days
        sample_ranks = df.groupby('dt_internal')['procedure'].transform(lambda x: x.astype('category').cat.codes)
        
        # Multiply by a fixed spacing factor (4.5 as per your previous logic)
        df['jitter'] = sample_ranks * 4.5

        # This is our new numeric X-axis
        df['x_pos'] = df['day_num'] + df['jitter']
       
        super().__init__(df=df, modes=modes, settings=settings, **kwargs)
        # object.__setattr__(self, 'df', df)
        self.construct_chart(start_date=start, end_date=end)
        self.update_layout(showlegend=False)

    def construct_chart(self, start_date, end_date, df: pd.DataFrame | None = None,  **kwargs):
        if df:
            object.__setattr__(self, 'df', df)
        try:
            self.df = self.df[self.df["sample_id"].notnull()]
            self.df = self.df.sort_values(['submitted_date', 'procedure'], ascending=[True, True]).reset_index(
                drop=True)
            self.df = self.df.reset_index().rename(columns={"index": "idx"})
            hover_template = (
                
                "<b>Sample: %{customdata[1]}</b><br>"
                "Procedure: %{customdata[3]}<br>"
                "Concentration: %{customdata[2]:,.2f}ng/uL<br>"
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
        except (ValueError, AttributeError, KeyError) as e:
            logger.error(f"Error creating scatter plot: {e}")
            scatter = px.scatter()
            hover_template = None
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
