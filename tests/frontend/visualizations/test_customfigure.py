import pytest
import sys
if "C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions" not in sys.path:
    sys.path.append("C:\\Users\\lwark\\Documents\\python\\submissions\\src\\submissions")
import pandas as pd
from datetime import date
from frontend.visualizations import CustomFigure  # Replace 'your_module' with the actual filename
import plotly.graph_objects as go

@pytest.fixture
def sample_data():
    """Returns a dummy DataFrame and settings for testing."""
    df = pd.DataFrame({'a': [1, 2], 'b': [3, 4]})
    settings = {
        'months': 6,
        'start_date': date(2023, 1, 1),
        'end_date': date(2023, 6, 1)
    }
    return df, settings

def test_custom_figure_initialization(sample_data):
    """Verifies that the figure initializes with correct data and layout."""
    df, settings = sample_data
    modes = ['ModeA', 'ModeB']
    
    fig = CustomFigure(df, settings, modes=modes)
    
    # Check if dataframe was stored via object.__setattr__
    assert hasattr(fig, 'df')
    assert fig.df.equals(df)
    
    # Verify layout properties
    assert fig.layout.xaxis.title.text == "Submitted Date (* - Date parsed from fastq file creation date)"
    assert fig.layout.yaxis.title.text == 'ModeA'
    assert fig.layout.showlegend is True

def test_make_plotly_buttons(sample_data):
    """Tests the date-zoom button generator logic."""
    _, settings = sample_data
    # Test for 6 months
    buttons = list(CustomFigure.make_plotly_buttons(months=6))
    
    labels = [b['label'] for b in buttons if 'label' in b]
    assert "1m" in labels
    assert "3m" in labels
    assert any(b.get('step') == 'all' for b in buttons)

def test_make_pyqt_buttons_visibility(sample_data):
    """Tests the visibility toggle logic for PyQt buttons."""
    df, settings = sample_data
    modes = ['Mode1', 'Mode2']
    
    fig = CustomFigure(df, settings, modes=modes)
    # Manually add dummy data traces to test visibility logic
    fig.add_traces([
        go.Scatter(x=[1], y=[1], name="Trace 1"),
        go.Scatter(x=[1], y=[1], name="Trace 2")
    ])
    
    buttons = list(fig.make_pyqt_buttons(modes=modes))
    
    assert len(buttons) == 2
    # First button should show first trace, hide second
    assert buttons[0]['args'][0]['visible'] == [True, False]
    # Second button should hide first trace, show second
    assert buttons[1]['args'][0]['visible'] == [False, True]

def test_html_property(sample_data):
    """Verifies the HTML output contains expected Plotly tags."""
    df, settings = sample_data
    fig = CustomFigure(df, settings, modes=['Test'])
    
    html_output = fig.html
    assert "<html><body>" in html_output
    assert "plotly-graph-div" in html_output or "Plotly.newPlot" in html_output
