import pytest
import pandas as pd
from datetime import date
from test_customfigure import CustomFigure
from frontend.visualizations.turnaround_chart import TurnaroundChart

@pytest.fixture
def turnaround_data():
    """Returns sample data and settings for TurnaroundChart."""
    df = pd.DataFrame({
        'name': ['Sample C', 'Sample A', 'Sample B', 'Sample D'],
        'submitted_date': [date(2023, 1, 2), date(2023, 1, 1), date(2023, 1, 1), date(2023, 1, 3)],
        'days': [2.5, 1.0, None, 4.0],  # Sample B should be filtered out
        'acceptable': [True, True, False, False],
        'completed_date': [date(2023, 1, 4), date(2023, 1, 2), None, date(2023, 1, 7)]
    })
    settings = {
        'start_date': date(2023, 1, 1),
        'end_date': date(2023, 6, 1),
        'months': 6
    }
    return df, settings

def test_turnaround_chart_filtering_and_sorting(turnaround_data):
    """Verifies that null days are removed and data is sorted by date then name."""
    df, settings = turnaround_data
    chart = TurnaroundChart(df=df, modes=['TAT'], settings=settings)
    
    # 1. Check Filtering: Sample B (None) should be gone
    assert len(chart.df) == 3
    assert 'Sample B' not in chart.df['name'].values
    
    # 2. Check Sorting: Sample A (Jan 1) should be first, then C (Jan 2), then D (Jan 3)
    assert chart.df.iloc[0]['name'] == 'Sample A'
    assert chart.df.iloc[1]['name'] == 'Sample C'
    assert chart.df.iloc[2]['name'] == 'Sample D'
    
    # 3. Check idx: Ensure index was reset and renamed correctly
    assert chart.df.iloc[0]['idx'] == 0
    assert chart.df.iloc[2]['idx'] == 2

def test_turnaround_chart_threshold_line(turnaround_data):
    """Verifies the addition of a horizontal threshold line."""
    df, settings = turnaround_data
    threshold_value = 3.5
    
    # Chart with threshold
    chart = TurnaroundChart(df=df, modes=['TAT'], settings=settings, threshold=threshold_value)
    
    # Plotly stores hlines in layout.shapes
    assert len(chart.layout.shapes) == 1
    assert chart.layout.shapes[0].y0 == threshold_value
    assert chart.layout.shapes[0].y1 == threshold_value

def test_turnaround_chart_xaxis_ticks(turnaround_data):
    """Verifies that x-axis ticks match the sample names after filtering."""
    df, settings = turnaround_data
    chart = TurnaroundChart(df=df, modes=['TAT'], settings=settings)
    
    # The ticklabels should match the names in sorted order
    expected_labels = ['Sample A', 'Sample C', 'Sample D']
    assert list(chart.layout.xaxis.ticktext) == expected_labels
    assert list(chart.layout.xaxis.tickvals) == [0, 1, 2]

def test_turnaround_chart_marker_and_legend(turnaround_data):
    """Verifies marker size and that the legend is hidden."""
    df, settings = turnaround_data
    chart = TurnaroundChart(df=df, modes=['TAT'], settings=settings)
    
    # Verify traces have size 15
    for trace in chart.data:
        assert trace.marker.size == 15
        
    # Verify legend is explicitly hidden
    assert chart.layout.showlegend is False

def test_turnaround_chart_empty_data(turnaround_data):
    """Verifies handling of dataframes with missing 'days' column."""
    _, settings = turnaround_data
    bad_df = pd.DataFrame({'name': ['Test']}) # Missing 'days' and 'submitted_date'
    
    # Should not crash due to try/except block
    chart = TurnaroundChart(df=bad_df, modes=['TAT'], settings=settings)
    assert len(chart.data) == 0 or chart.data[0].x is None
