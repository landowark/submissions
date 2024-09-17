"""
Functions for constructing controls graphs using plotly.
"""
import plotly
import plotly.express as px
import pandas as pd
from plotly.graph_objects import Figure
import logging
from tools import get_unique_values_in_df_column, divide_chunks
from frontend.widgets.functions import select_save_file

logger = logging.getLogger(f"submissions.{__name__}")


class CustomFigure(Figure):

    def __init__(self, df: pd.DataFrame, modes: list, ytitle: str | None = None):
        super().__init__()
        self.construct_chart(df=df, modes=modes)
        self.generic_figure_markers(modes=modes, ytitle=ytitle)

    def construct_chart(self, df: pd.DataFrame, modes: list):
        """
        Creates a plotly chart for controls from a pandas dataframe

        Args:
            df (pd.DataFrame): input dataframe of controls
            modes (list): analysis modes to construct charts for
            ytitle (str | None, optional): title on the y-axis. Defaults to None.

        Returns:
            Figure: output stacked bar chart.
        """
        # fig = Figure()
        for ii, mode in enumerate(modes):
            if "count" in mode:
                df[mode] = pd.to_numeric(df[mode], errors='coerce')
                color = "genus"
                color_discrete_sequence = None
            elif 'percent' in mode:
                color = "genus"
                color_discrete_sequence = None
            else:
                color = "target"
                match get_unique_values_in_df_column(df, 'target'):
                    case ['Target']:
                        color_discrete_sequence = ["blue"]
                    case ['Off-target']:
                        color_discrete_sequence = ['red']
                    case _:
                        color_discrete_sequence = ['blue', 'red']
            bar = px.bar(df,
                         x="submitted_date",
                         y=mode,
                         color=color,
                         title=mode,
                         barmode='stack',
                         hover_data=["genus", "name", "target", mode],
                         text="genera",
                         color_discrete_sequence=color_discrete_sequence
                         )
            bar.update_traces(visible=ii == 0)
            self.add_traces(bar.data)
        # return generic_figure_markers(modes=modes, ytitle=ytitle)

    def generic_figure_markers(self, modes: list = [], ytitle: str | None = None):
        """
        Adds standard layout to figure.

        Args:
            fig (Figure): Input figure.
            modes (list, optional): List of modes included in figure. Defaults to [].
            ytitle (str, optional): Title for the y-axis. Defaults to None.

        Returns:
            Figure: Output figure with updated titles, rangeslider, buttons.
        """
        if modes:
            ytitle = modes[0]
        # Creating visibles list for each mode.
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
                    buttons=[button for button in self.make_buttons(modes=modes)],
                )
            ]
        )
        self.update_xaxes(
            rangeslider_visible=True,
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=3, label="3m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            )
        )
        assert isinstance(self, Figure)
        # return fig

    def make_buttons(self, modes: list) -> list:
        """
        Creates list of buttons with one for each mode to be used in showing/hiding mode traces.

        Args:
            modes (list): list of modes used by main parser.
            fig_len (int): number of traces in the figure

        Returns:
            list: list of buttons.
        """
        fig_len = len(self.data)
        if len(modes) > 1:
            for ii, mode in enumerate(modes):
                # NOTE: What I need to do is create a list of bools with the same length as the fig.data
                mode_vis = [True] * fig_len
                # NOTE: And break it into {len(modes)} chunks
                mode_vis = list(divide_chunks(mode_vis, len(modes)))
                # NOTE: Then, for each chunk, if the chunk index isn't equal to the index of the current mode, set to false
                for jj, sublist in enumerate(mode_vis):
                    if jj != ii:
                        mode_vis[jj] = [not elem for elem in mode_vis[jj]]
                # NOTE: Finally, flatten list.
                mode_vis = [item for sublist in mode_vis for item in sublist]
                # NOTE: Now, yield button to add to list
                yield dict(label=mode, method="update", args=[
                    {"visible": mode_vis},
                    {"yaxis.title.text": mode},
                ])

    def save_figure(self, group_name: str = "plotly_output"):
        """
        Writes plotly figure to html file.

        Args:
            figs ():
            settings (dict): settings passed down from click
            fig (Figure): input figure object
            group_name (str): controltype
        """
        output = select_save_file(None, default_name=group_name, extension="html")
        with open(output, "w") as f:
            try:
                f.write(self.to_html())
            except AttributeError:
                logger.error(f"The following figure was a string: {self}")

    def to_html(self) -> str:
        """
        Creates final html code from plotly

        Args:
            figure (Figure): input figure

        Returns:
            str: html string
        """
        html = '<html><body>'
        if self is not None:
            html += plotly.offline.plot(self, output_type='div',
                                        include_plotlyjs='cdn')  #, image = 'png', auto_open=True, image_filename='plot_image')
        else:
            html += "<h1>No data was retrieved for the given parameters.</h1>"
        html += '</body></html>'
        return html
