"""
Contains all operations for creating charts, graphs and visual effects.
"""
from datetime import timedelta, date
from typing import Generator
from pandas import DataFrame
import plotly
import pandas as pd, logging
from plotly.graph_objects import Figure
from tools import divide_chunks

logger = logging.getLogger(f"submissions.{__name__}")


class CustomFigure(Figure):

    def __init__(self, df: pd.DataFrame, settings: dict, ytitle: str | None = None, **kwargs):
        super().__init__()
        for k, v in settings.items():
            object.__setattr__(self, k, v)
        months = int(settings.get('months', 6))
        df['dt_internal'] = pd.to_datetime(df["submitted_date"]).dt.normalize()
        # Set dataframe on the instance using object.__setattr__ because
        # plotly.graph_objects.Figure implements a custom __setattr__ which
        # can raise AttributeError for arbitrary attribute names. Using the
        # base object setattr bypasses that and stores the dataframe safely.
        object.__setattr__(self, 'df', df)
        
        self.data = []
        
        # self.update_xaxes(range=[settings['start_date'] - timedelta(days=1), settings['end_date']])
        self.generic_figure_markers(ytitle=ytitle, months=months)

    def generic_figure_markers(self, ytitle: str | None = None, months: int = 6):
        """
        Adds standard layout to figure.

        Args:
            fig (Figure): Input figure.
            ytitle (str, optional): Title for the y-axis. Defaults to None.

        Returns:
            Figure: Output figure with updated titles, rangeslider, buttons.
        """
        self.update_layout(
            xaxis_title="Submitted Date (* - Date parsed from fastq file creation date)",
            yaxis_title=ytitle,
            showlegend=True,
            barmode='stack',
            updatemenus=[
                dict(
                    type="buttons",
                    direction="right",
                    x=0.7,
                    y=1.2,
                    showactive=True,
                    buttons=[button for button in self.make_pyqt_buttons()],
                )
            ]
        )
        self.update_xaxes(
            type='category',
            tickmode='array',
            rangeslider_visible=True,
            range=[self.df['dt_internal'].min(), self.df['dt_internal'].max()],
            rangeselector=dict(
                buttons = [button for button in self.make_plotly_buttons(months=months)]
            )
        )
        self.update_yaxes(autorange=True)
        assert isinstance(self, CustomFigure)

    @classmethod
    def make_plotly_buttons(cls, months: int = 6) -> Generator[dict, None, None]:
        """
        Creates html buttons to zoom in on date areas

        Args:
            months (int, optional): Number of months of data given. Defaults to 6.

        Yields:
            Generator[dict, None, None]: Button details.
        """
        rng = [1]
        if months > 2:
            rng += [iii for iii in range(3, months, 3)]
        buttons = [dict(count=iii, label=f"{iii}m", step="month", stepmode="backward") for iii in rng]
        if months > date.today().month:
            buttons += [dict(count=1, label="YTD", step="year", stepmode="todate")]
        buttons += [dict(step="all")]
        for button in buttons:
            yield button

    def make_pyqt_buttons(self, modes: list=[]) -> Generator[dict, None, None]:
        """
        Creates list of buttons with one for each mode to be used in showing/hiding mode traces.

        Args:
            modes (list): list of modes used by main clientsubmissionparser.
            fig_len (int): number of traces in the figure

        Returns:
            Generator[dict, None, None]: list of buttons.
        """
        # NOTE: self.data is set in the child instances.
        fig_len = len(self.data)
        if len(modes) > 1:
            for ii, mode in enumerate(modes):
                # NOTE: What I need to do is create a list of bools with the same length as the fig.data
                mode_vis = [True] * fig_len
                # NOTE: And break it into {len(modes)} chunks
                mode_vis = list(divide_chunks(mode_vis, len(modes)))
                # NOTE: Then, for each chunk, if the chunk index isn't equal to the index of the current mode, set to false
                for jj, _ in enumerate(mode_vis):
                    if jj != ii:
                        mode_vis[jj] = [not elem for elem in mode_vis[jj]]
                # NOTE: Finally, flatten list.
                mode_vis = [item for sublist in mode_vis for item in sublist]
                # NOTE: Now, yield button to add to list
                yield dict(label=mode, method="update", args=[
                    {"visible": mode_vis},
                    {"yaxis.title.text": mode},
                ])

    @property
    def html(self) -> str:
        """
        Creates final html code from plotly

        Returns:
            str: html string
        """
        html = f'<html><body>'
        if self is not None:
            # NOTE: Just cannot get this load from string to freaking work.
            html += plotly.offline.plot(self, output_type='div', include_plotlyjs="cdn")
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        return html
    
class ResultsFigure(CustomFigure):
    
    def __init__(self, df: pd.DataFrame, settings: dict, **kwargs):
        
        super().__init__(df, settings, **kwargs)
        object.__setattr__(self, 'start', pd.to_datetime(settings['start_date']).normalize())
        object.__setattr__(self, 'end', pd.to_datetime(settings['end_date']).normalize())
        # self.start = pd.to_datetime(settings['start_date']).normalize()
        # self.end = pd.to_datetime(settings['end_date']).normalize()
        self.df['day_num'] = (self.df['dt_internal'] - self.start).dt.days
        sample_ranks = df.groupby('dt_internal')['procedure'].transform(lambda x: x.astype('category').cat.codes)
        
        # Multiply by a fixed spacing factor (4.5 as per your previous logic)
        self.df['jitter'] = sample_ranks * 4.5

        # This is our new numeric X-axis
        self.df['x_pos'] = self.df['day_num'] + self.df['jitter']
        self.construct_chart(df=self.df, **kwargs)
        self.update_layout(showlegend=False)

    def construct_chart(self, df: pd.DataFrame | None = None,  **kwargs):
        """
        Constructs the chart by adding traces to the figure. To be implemented by child classes.

        Args:
            df (pd.DataFrame | None, optional): Dataframe to use in constructing chart. Defaults to None.
            **kwargs: Additional arguments for constructing chart.

        Returns:
            None
        """
        if df is not None:
            object.__setattr__(self, 'df', df)
        try:
            self.df = self.df[self.df["sample_id"].notnull()]
            self.df = self.df.sort_values(['submitted_date', 'procedure'], ascending=[True, True]).reset_index(
                drop=True)
            self.df = self.df.reset_index().rename(columns={"index": "idx"})
            return True
        except (ValueError, AttributeError, KeyError) as e:
            logger.error(f"Error creating scatter plot: {e}")
            return False


from .kraken_charts import KrakenFigure
from .pcr_charts import PCRFigure
from .concentrations_chart import ConcentrationsChart
from .turnaround_chart import TurnaroundChart
