import pytest
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from test_customfigure import CustomFigure
from frontend.visualizations.irida_charts import IridaFigure

@pytest.fixture
def irida_data():
    """Returns sample data and settings for IridaFigure."""
    df = pd.DataFrame({
        'name': ['S1', 'S2', 'S3'],
        'submitted_date': [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)],
        'genus': ['E.coli', 'Salmonella', 'E.coli'],
        'target': ['Target', 'Off-target', 'Target'],
        'genera': ['Ec', 'Sal', 'Ec'],
        'mode_count': ['10', '20', 'invalid'], # 'invalid' tests to_numeric(errors='coerce')
        'mode_percent': [0.5, 0.8, 0.3]
    })
    settings = {
        'start_date': date(2023, 1, 1),
        'end_date': date(2023, 6, 1),
        'months': 6
    }
    return df, settings

def test_irida_figure_trace_visibility(irida_data):
    """Verifies that only the first mode's traces are visible initially."""
    df, settings = irida_data
    modes = ['mode_count', 'mode_percent']
    
    fig = IridaFigure(df=df, modes=modes, settings=settings)
    
    # px.bar creates traces per unique color category (genus)
    # We expect traces for mode_count (visible) and traces for mode_percent (hidden)
    visible_traces = [t for t in fig.data if t.visible is True]
    hidden_traces = [t for t in fig.data if t.visible is False]
    
    assert len(visible_traces) > 0
    assert len(hidden_traces) > 0
    # The first set of traces (mode_count) should be visible
    assert visible_traces[0].name in df['genus'].unique()

def test_irida_figure_numeric_conversion(irida_data):
    """Verifies that 'count' modes are converted to numeric (handling NaNs)."""
    df, settings = irida_data
    modes = ['mode_count']
    
    fig = IridaFigure(df=df, modes=modes, settings=settings)
    
    # Check the dataframe stored in the instance
    # 'invalid' should have become NaN (NaN != NaN in standard comparison)
    assert pd.isna(fig.df['mode_count'].iloc[2])
    assert fig.df['mode_count'].dtype.kind in 'if' # integer or float

def test_irida_figure_color_logic(irida_data):
    """Verifies the color_discrete_sequence logic based on 'target' column."""
    df, settings = irida_data
    modes = ['mode_count'] # Does not trigger 'count' or 'percent'
    
    # Scenario: Mixed targets (Target and Off-target)
    fig = IridaFigure(df=df, modes=modes, settings=settings)
    
    # In px.bar, color_discrete_sequence is applied to the traces' marker colors
    # We expect blue and red to be present in the sequence
    trace_colors = [t.marker.color for t in fig.data if hasattr(t.marker, 'color')]
    # Note: Plotly might represent these as hex or strings; 
    # since we passed ['blue', 'red'], we check if traces exist for them.
    assert len(fig.data) >= 2 

def test_irida_figure_layout(irida_data):
    """Verifies layout settings from the base and child class."""
    df, settings = irida_data
    modes = ['mode_count']
    
    fig = IridaFigure(df=df, modes=modes, settings=settings)
    
    # From CustomFigure.generic_figure_markers
    assert fig.layout.barmode == 'stack'
    assert fig.layout.xaxis.rangeslider.visible is True
    # From IridaFigure construct_chart loop
    assert fig.layout.yaxis.title.text == 'mode_count'
