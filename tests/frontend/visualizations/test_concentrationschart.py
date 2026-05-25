import pytest
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from test_customfigure import CustomFigure
from frontend.visualizations.concentrations_chart import ConcentrationsChart
  # Replace with actual filename

@pytest.fixture
def concentration_data():
    """Returns sample data specifically structured for ConcentrationChart."""
    df = pd.DataFrame({
        'name': ['Sample A', 'Sample B', 'Sample C', 'Sample D'],
        'procedure': ['Proc 1', 'Proc 2', 'Proc 1', 'Proc 3'],
        'concentration': [10.5, None, 20.0, 5.2],  # Note the None value
        'submitted_date': [date(2023, 1, 2), date(2023, 1, 1), date(2023, 1, 1), date(2023, 1, 3)],
        'positive': ['positive', 'negative', 'sample', 'positive']
    })
    settings = {
        'months': 6,
        'start_date': date(2023, 1, 1),
        'end_date': date(2023, 6, 1)
    }
    return df, settings

def test_concentrations_chart_filtering(concentration_data):
    """Verifies that null concentrations are dropped and data is sorted."""
    df, settings = concentration_data
    modes = ['Main']
    
    chart = ConcentrationsChart(df=df, modes=modes, settings=settings)
    
    # 1. Check Filtering: Sample B had concentration None and should be gone
    assert len(chart.df) == 3
    assert None not in chart.df.concentration.values
    
    # 2. Check Sorting: Sorted by date then procedure
    # Expected order after sort: Sample C (Jan 1), Sample A (Jan 2), Sample D (Jan 3)
    assert chart.df.iloc[0]['name'] == 'Sample C'
    assert chart.df.iloc[2]['name'] == 'Sample D'

def test_concentrations_chart_traces(concentration_data):
    """Verifies that traces are created with the correct colors and markers."""
    df, settings = concentration_data
    chart = ConcentrationsChart(df=df, modes=['Main'], settings=settings)
    
    # Verify traces exist (px.scatter creates traces per color/category)
    assert len(chart.data) > 0
    
    # Verify marker size update from construct_chart
    for trace in chart.data:
        assert trace.marker.size == 15

def test_concentrations_chart_axes(concentration_data):
    """Verifies axis configuration (tick labels and non-negative y-axis)."""
    df, settings = concentration_data
    chart = ConcentrationsChart(df=df, modes=['Main'], settings=settings)
    
    # Check y-axis range mode
    assert chart.layout.yaxis.rangemode == "nonnegative"
    
    # Check x-axis tickmode and values
    assert chart.layout.xaxis.tickmode == 'array'
    # The tickvals should match the 'procedure' column of the filtered dataframe
    expected_ticks = chart.df['procedure'].tolist()
    assert list(chart.layout.xaxis.tickvals) == expected_ticks

def test_concentrations_chart_empty_data(concentration_data):
    """Ensures the chart handles empty or invalid dataframes gracefully."""
    _, settings = concentration_data
    empty_df = pd.DataFrame(columns=['name', 'procedure', 'concentration', 'positive'])
    
    # Should not raise an exception
    chart = ConcentrationsChart(df=empty_df, modes=['Main'], settings=settings)
    
    assert len(chart.data) == 1
    assert chart.layout.xaxis.tickvals == ()
