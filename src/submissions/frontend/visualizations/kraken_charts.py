"""
Functions for constructing irida control graphs using plotly.
"""
from pprint import pformat
import logging, plotly.express as px, pandas as pd
from typing import Literal
from . import CustomFigure

logger = logging.getLogger(f"submissions.{__name__}")


class KrakenFigure(CustomFigure):

    def __init__(self, df: pd.DataFrame, settings: dict, **kwargs):
        
        df['dt_internal'] = pd.to_datetime(df["submitted_date"]).dt.normalize()
        start = pd.to_datetime(settings['start_date']).normalize()
        end = pd.to_datetime(settings['end_date']).normalize()
        

        # 2. Robust Jitter Calculation
        # We group by the date and rank the meta.id to ensure each unique sample 
        # on that day gets a unique integer offset (0, 1, 2...)
        target_col = 'new_est_reads' if 'new_est_reads' in df.columns else 'kraken_assigned_reads'
        df[target_col] = pd.to_numeric(df[target_col], errors='coerce').fillna(0)

        df['day_num'] = (df['dt_internal'] - start).dt.days
        sample_ranks = df.groupby('dt_internal')['meta.id'].transform(lambda x: x.astype('category').cat.codes)
        
        # Multiply by a fixed spacing factor (4.5 as per your previous logic)
        df['jitter'] = sample_ranks * 4.5
        
        # This is our new numeric X-axis
        df['x_pos'] = df['day_num'] + df['jitter']

        sample_totals = df.groupby('meta.id')[target_col].transform('sum')
        df['relative_fraction'] = (df[target_col] / sample_totals).fillna(0)
        
        super().__init__(df=df, settings=settings, **kwargs)
        object.__setattr__(self, 'df', df)
        self.construct_chart(df=df, start_date=start, end_date=end)

    def construct_datasets_and_hovers(self, mode: Literal["count", "percent"]):
        data = []
        hovers = []
        for s in self.df['name'].unique().tolist():
            # Filter for the specific species
            subset = self.df[self.df['name'] == s]

            hover_str = (
                f"<b>{self.species_or_genus}: {s}</b><br>"
                f"Reads: %{{customdata[2]:,.0f}}<br>"
                f"Share: %{{customdata[3]:.1%}}"
                "<extra></extra>"
            )
            match mode:
                case "count":
                    data.append(subset['new_est_reads'].tolist())
                case "percent":
                    data.append(subset['relative_fraction'].tolist())
            hovers.append(hover_str)
            
        return data, hovers



    def make_pyqt_buttons(self, **kwargs):

        # species_list = self.df['name'].unique().tolist()
        
        # 1. Prepare lists for each species trace
        
        count_data, count_hovers = self.construct_datasets_and_hovers(mode="count")
        percent_data, percent_hovers = self.construct_datasets_and_hovers(mode="percent")

        return [
            dict(
                label="Count",
                method="update",
                args=[
                    {"y": count_data, "hovertemplate": count_hovers}, 
                    {"yaxis": {"title": "Assigned Reads", "tickformat": ""}}
                ]
            ),
            dict(
                label="Percent",
                method="update",
                args=[
                    {"y": percent_data, "hovertemplate": percent_hovers}, 
                    {"yaxis": {"title": "Percent of Total Reads", "tickformat": ".1%"}}
                ]
            )
        ]



    def construct_chart(self, df: pd.DataFrame, start_date, end_date, **kwargs):
        """
        Creates a plotly chart for control from a pandas dataframe

        Args:
            end_date ():
            start_date ():
            df (pd.DataFrame): input dataframe of control
            ytitle (str | None, optional): title on the y-axis. Defaults to None.

        Returns:
            Figure: output stacked bar chart.
        """
        df['display_name'] = df['meta.id'].astype(str) + " | " + df["submitted_date"].astype(str)
        _, hover_templates = self.construct_datasets_and_hovers(mode="count")
        # This prevents stacking and ensures bars have a visible "category" width
        # Build the chart using 'adjusted_date'
        bar = px.bar(
            df, 
            x="x_pos", 
            y="new_est_reads", 
            color="name", # Species name for the stacks
            hover_data={"submitted_date": True, "meta.id": True, "name": True, "x_pos":False},
            # title="Reads by Date (Split Samples)",
            custom_data=['submitted_date', 'meta.id', 'new_est_reads', 'relative_fraction'],
            barmode="stack",
            # Custom data allows the range selector to see the actual dates
        )
        self.add_traces(bar.data)

        # 3. Apply the custom hover templates to each trace
        # Plotly maps one template per trace (species). 
        # Since self.add_traces adds them in order, we loop through and assign.
        for i, trace in enumerate(self.data):
            if i < len(hover_templates):
                trace.hovertemplate = hover_templates[i]
        # 2. Add layout updates directly to the figure (self)
        self.update_layout(barmode='stack')
        # Fix the width so bars don't touch
        self.update_traces(width=4) 

        # Map the numeric ticks back to readable dates
        unique_days = df[['x_pos', 'display_name']]#.drop_duplicates()
        self.update_xaxes(
            type='linear',
            tickmode='array',
            tickvals=unique_days['x_pos'],
            ticktext=unique_days['display_name'],
            range=[-1, (pd.to_datetime(end_date) - pd.to_datetime(start_date)).days + 1]
        )

        