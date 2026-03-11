import pytest
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from test_customfigure import CustomFigure
from frontend.visualizations.pcr_charts import PCRFigure

@pytest.fixture
def pcr_data():
    """Returns sample data and settings for PCRFigure."""
    df = pd.DataFrame({
        'name': ['Sample 1', 'Sample 2', 'Sample 3'],
        'submitted_date': [date(2023, 1, 1), date(2023, 1, 2), date(2023, 1, 3)],
        'target': ['Target A', 'Target B', 'Target A'],
        'ct': [25.5, 30.2, 22.1],
        'reagent_lot': ['Lot001', 'Lot001', 'Lot002']
    })
    settings = {
        'start_date': date(2023, 1, 1),
        'end_date': date(2023, 6, 1),
        'months': 6
    }
    return df, settings

def test_pcr_figure_trace_creation(pcr_data):
    """Verifies that traces are created for each unique target."""
    df, settings = pcr_data
    modes = ['PCR']
    
    fig = PCRFigure(df=df, modes=modes, settings=settings)
    
    # px.scatter with color="target" creates one trace per unique target
    unique_targets = df['target'].unique()
    assert len(fig.data) == len(unique_targets)
    
    # Check if trace names match the targets
    trace_names = [trace.name for trace in fig.data]
    for target in unique_targets:
        assert target in trace_names

def test_pcr_figure_marker_size(pcr_data):
    """Verifies that marker size is updated to 15 for all traces."""
    df, settings = pcr_data
    fig = PCRFigure(df=df, modes=['PCR'], settings=settings)
    
    assert len(fig.data) > 0
    for trace in fig.data:
        assert trace.marker.size == 15

def test_pcr_figure_hover_data(pcr_data):
    """Verifies that hover template contains expected data keys."""
    df, settings = pcr_data
    fig = PCRFigure(df=df, modes=['PCR'], settings=settings)
    
    # Check first trace hovertemplate for required fields
    hovertemplate = fig.data[0].hovertemplate
    assert "name" in hovertemplate
    assert "reagent_lot" in hovertemplate
    assert "ct" in hovertemplate

def test_pcr_figure_empty_data_handling(pcr_data):
    """Verifies the try-except block handles data errors by creating an empty scatter."""
    _, settings = pcr_data
    # Empty dataframe might trigger a ValueError depending on Plotly version/config
    empty_df = pd.DataFrame() 
    
    fig = PCRFigure(df=empty_df, modes=['PCR'], settings=settings)
    
    # If the try/except caught a ValueError, it adds traces from px.scatter() (which is 0 traces)
    # The figure should still exist and not crash the test
    assert isinstance(fig, PCRFigure)

def test_pcr_figure_inheritance(pcr_data):
    """Ensures parent CustomFigure layout logic is applied."""
    df, settings = pcr_data
    fig = PCRFigure(df=df, modes=['PCR'], settings=settings)
    
    # Check layout set in CustomFigure.generic_figure_markers
    assert fig.layout.xaxis.rangeslider.visible is True
    assert fig.layout.showlegend is True
