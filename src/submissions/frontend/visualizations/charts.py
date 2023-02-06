import plotly.express as px
import pandas as pd
from pathlib import Path
from plotly.graph_objects import Figure
import logging
from backend.excel import get_unique_values_in_df_column

logger = logging.getLogger(f"submissions.{__name__}")


def create_charts(ctx:dict, df:pd.DataFrame, ytitle:str|None=None) -> Figure:
    """
    Constructs figures based on parsed pandas dataframe.

    Args:
        settings (dict): settings passed down from gui
        df (pd.DataFrame): input dataframe
        group_name (str): controltype

    Returns:
        Figure: plotly figure
    """    
    from backend.excel import drop_reruns_from_df
    # converts starred genera to normal and splits off list of starred
    genera = []
    if df.empty:
        return None
    for item in df['genus'].to_list():
        try:
            if item[-1] == "*":
                genera.append(item[-1])    
            else:
                genera.append("")
        except IndexError:
            genera.append("")
    df['genus'] = df['genus'].replace({'\*':''}, regex=True)
    df['genera'] = genera
    df = df.dropna()
    # remove original runs, using reruns if applicable
    df = drop_reruns_from_df(ctx=ctx, df=df)
    # sort by and exclude from
    sorts = ['submitted_date', "target", "genus"]
    exclude = ['name', 'genera']
    modes = [item for item in df.columns if item not in sorts and item not in exclude and "_hashes" not in item]
    # Set descending for any columns that have "{mode}" in the header.
    ascending = [False if item == "target" else True for item in sorts]
    df = df.sort_values(by=sorts, ascending=ascending)
    # actual chart construction is done by
    fig = construct_chart(ctx=ctx, df=df, modes=modes, ytitle=ytitle)
    return fig
    


def generic_figure_markers(fig:Figure, modes:list=[], ytitle:str|None=None) -> Figure:
    """
    Adds standard layout to figure.

    Args:
        fig (Figure): Input figure.
        modes (list, optional): List of modes included in figure. Defaults to [].

    Returns:
        Figure: Output figure with updated titles, rangeslider, buttons.
    """
    if modes != []:
        ytitle = modes[0]
    # Creating visibles list for each mode.
    fig.update_layout(
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
                buttons=make_buttons(modes=modes, fig_len=len(fig.data)),
            )
        ]
    )
    fig.update_xaxes(
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
    # logger.debug(f"Returning figure {fig}")
    assert type(fig) == Figure
    return fig


def make_buttons(modes:list, fig_len:int) -> list:
    """
    Creates list of buttons with one for each mode to be used in showing/hiding mode traces.

    Args:
        modes (list): list of modes used by main parser.
        fig_len (int): number of traces in the figure

    Returns:
        list: list of buttons.
    """
    buttons = []
    if len(modes) > 1:
        for ii, mode in enumerate(modes):
            # What I need to do is create a list of bools with the same length as the fig.data
            mode_vis = [True] * fig_len
            # And break it into {len(modes)} chunks
            mode_vis = list(divide_chunks(mode_vis, len(modes)))
            # Then, for each chunk, if the chunk index isn't equal to the index of the current mode, set to false
            for jj, sublist in enumerate(mode_vis):
                if jj != ii:
                    mode_vis[jj] = [not elem for elem in mode_vis[jj]]
            # Finally, flatten list.
            mode_vis = [item for sublist in mode_vis for item in sublist]
            # Now, make button to add to list
            buttons.append(dict(label=mode, method="update", args=[
                                {"visible": mode_vis},
                                {"yaxis.title.text": mode},
                            ]
                        ))
    return buttons

def output_figures(settings:dict, figs:list, group_name:str):
    """
    Writes plotly figure to html file.

    Args:
        settings (dict): settings passed down from click
        fig (Figure): input figure object
        group_name (str): controltype
    """
    with open(Path(settings['folder']['output']).joinpath(f'{group_name}.html'), "w") as f:
        for fig in figs:
            try:
                f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
            except AttributeError:
                logger.error(f"The following figure was a string: {fig}")

# Below are the individual construction functions. They must be named "construct_{mode}_chart" and 
# take only json_in and mode to hook into the main processor.

def construct_chart(ctx:dict, df:pd.DataFrame, modes:list, ytitle:str|None=None) -> Figure:
    fig = Figure()

    for ii, mode in enumerate(modes):
        if "count" in mode:
            df[mode] = pd.to_numeric(df[mode],errors='coerce')
            color = "genus"
            color_discrete_sequence=None
        elif 'percent' in mode:
            color = "genus"
            color_discrete_sequence=None
        else:
            color = "target"
            # print(get_unique_values_in_df_column(df, 'target'))
            match get_unique_values_in_df_column(df, 'target'):
                case ['Target']:
                    color_discrete_sequence=["blue"]
                case ['Off-target']:
                    color_discrete_sequence=['red']
                case _:
                    color_discrete_sequence=['blue', 'red']
        bar = px.bar(df, x="submitted_date", 
            y=mode, 
            color=color, 
            title=mode,
            barmode='stack', 
            hover_data=["genus", "name", "target", mode], 
            text="genera",
            color_discrete_sequence=color_discrete_sequence
        )
        bar.update_traces(visible = ii == 0)
        fig.add_traces(bar.data)
    # sys.exit(f"number of traces={len(fig.data)}")
    return generic_figure_markers(fig=fig, modes=modes, ytitle=ytitle)



def construct_refseq_chart(settings:dict, df:pd.DataFrame, group_name:str, mode:str) -> Figure:
    """
    Constructs intial refseq chart for both contains and matches (depreciated).

    Args:
        settings (dict): settings passed down from click.
        df (pd.DataFrame): dataframe containing all sample data for the group.
        group_name (str): name of the group being processed.
        mode (str): contains or matches, overwritten by hardcoding, so don't think about it too hard.

    Returns:
        Figure: initial figure with contains and matches traces.
    """    
    # This overwrites the mode from the signature, might get confusing.
    fig = Figure()
    modes = ['contains', 'matches']
    for ii, mode in enumerate(modes): 
        bar = px.bar(df, x="submitted_date", 
            y=f"{mode}_ratio", 
            color="target", 
            title=f"{group_name}_{mode}", 
            barmode='stack', 
            hover_data=["genus", "name", f"{mode}_hashes"], 
            text="genera"
        )
        bar.update_traces(visible = ii == 0)
        # Plotly express returns a full figure, so we have to use the data from that figure only.
        fig.add_traces(bar.data)
    # sys.exit(f"number of traces={len(fig.data)}")
    return generic_figure_markers(fig=fig, modes=modes)


def construct_kraken_chart(settings:dict, df:pd.DataFrame, group_name:str, mode:str) -> Figure:
    """
    Constructs intial refseq chart for each mode in the kraken config settings. (depreciated)

    Args:
        settings (dict): settings passed down from click.
        df (pd.DataFrame): dataframe containing all sample data for the group.
        group_name (str): name of the group being processed.
        mode (str): kraken modes retrieved from config file by setup.

    Returns:
        Figure: initial figure with traces for modes
    """    
    df[f'{mode}_count'] = pd.to_numeric(df[f'{mode}_count'],errors='coerce')
    # The actual percentage from kraken was off due to exclusion of NaN, recalculating.
    df[f'{mode}_percent'] = 100 * df[f'{mode}_count'] / df.groupby('submitted_date')[f'{mode}_count'].transform('sum')
    modes = settings['modes'][mode]
    # This overwrites the mode from the signature, might get confusing.
    fig = Figure()
    for ii, entry in enumerate(modes):         
        bar = px.bar(df, x="submitted_date", 
            y=entry,
            color="genus",
            title=f"{group_name}_{entry}", 
            barmode="stack", 
            hover_data=["genus", "name", "target"],
            text="genera",
        )
        bar.update_traces(visible = ii == 0)
        fig.add_traces(bar.data)
    return generic_figure_markers(fig=fig, modes=modes)


def divide_chunks(input_list:list, chunk_count:int):
    """
    Divides a list into {chunk_count} equal parts

    Args:
        input_list (list): Initials list
        chunk_count (int): size of each chunk

    Returns:
        tuple: tuple containing sublists.
    """    
    k, m = divmod(len(input_list), chunk_count)
    return (input_list[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(chunk_count))

########This must be at bottom of module###########

function_map = {}
for item in dict(locals().items()):
    try:
        if dict(locals().items())[item].__module__ == __name__:
            try:
                function_map[item] = dict(locals().items())[item]
            except KeyError:
                pass
    except AttributeError:
        pass
###################################################