"""
The report builders behind the chart tabs.

Each of these classes runs a query, walks the resulting objects, and folds them
into a DataFrame. They are the busiest consumers of the model layer's computed
properties, which makes them a good integration check -- and they are also where
model bugs have surfaced as an application that will not start, because
``TurnaroundTime.__init__`` builds its report during ``App`` construction.

The dates are pinned to the fixture's own span rather than to ``date.today()`` so
these tests do not quietly stop covering anything as the seeded data ages.
"""
from __future__ import annotations

from datetime import timedelta

import pytest


@pytest.fixture()
def span(graph):
    """The date range the seeded submissions actually occupy, with a margin."""
    dates = [s.submitted_date for s in graph["submissions"] if s.submitted_date]
    assert dates, "fixture produced no submitted dates"
    return min(dates).date() - timedelta(days=1), max(dates).date() + timedelta(days=30)


def test_report_maker_builds(graph, span):
    """The cost report over the seeded procedures."""
    from backend.excel.reports import ReportMaker

    start, end = span
    report = ReportMaker(start_date=start, end_date=end)
    assert report.procedures, "no procedures found in the seeded range"
    assert report.detailed_df is not None
    assert report.summary_df is not None


def test_report_maker_html(graph, span):
    """The summary report renders to HTML for the Cost Report pane."""
    from backend.excel.reports import ReportMaker

    start, end = span
    assert ReportMaker(start_date=start, end_date=end).html.strip()


def test_report_maker_filters_by_organization(graph, span):
    """Passing an organization narrows the procedure list rather than emptying it."""
    from backend.excel.reports import ReportMaker

    start, end = span
    lab_name = graph["labs"][0].name

    everything = ReportMaker(start_date=start, end_date=end)
    filtered = ReportMaker(start_date=start, end_date=end, organizations=[lab_name])

    assert len(filtered.procedures) <= len(everything.procedures)
    for procedure in filtered.procedures:
        assert procedure.run.clientsubmission.clientlab.name == lab_name


def test_turnaround_maker_builds(graph, span):
    """
    The turnaround report, which is built during ``App`` construction.

    Two separate model bugs have made this raise -- ``max()`` over unfiltered
    ``None``s, and a relationship referenced by the wrong name -- and both times
    the symptom was that the whole application failed to open.
    """
    from backend.excel.reports import TurnaroundMaker

    start, end = span
    report = TurnaroundMaker(start_date=start, end_date=end, submission_types=None)
    assert report.df is not None


def test_turnaround_maker_with_unsigned_incomplete_runs(graph, span):
    """
    Build the turnaround report against the worst realistic data.

    Every run signed, no completion dates anywhere: the exact shape that made
    ``Run.completed_date`` raise.
    """
    from backend.excel.reports import TurnaroundMaker

    for run in graph["runs"]:
        run._completed_date = None
        run._signed_by = "tester"
        for procedure in run.procedure:
            procedure._completed_date = None
    graph["session"].commit()

    start, end = span
    report = TurnaroundMaker(start_date=start, end_date=end, submission_types=None)
    assert report.df is not None


@pytest.mark.parametrize("maker_name", ["ConcentrationMaker", "PCRMaker"])
def test_results_makers_build(graph, span, maker_name):
    """
    The instrument-results reports.

    These legitimately produce an empty frame when the seeded results carry no
    matching columns; what they must not do is raise.
    """
    import backend.excel.reports as reports

    maker = getattr(reports, maker_name)
    start, end = span
    report = maker(start_date=start, end_date=end, submission_types=None,
                   include=["Positive", "Negative", "Samples"])
    assert report.df is not None


@pytest.mark.xfail(
    strict=True,
    reason="BaseClass.execute_query returns None (not []) when a query matches "
           "nothing, and the report builders iterate the result directly: "
           "reports.py:166 'for sub in self.subs' and reports.py:50 "
           "'for procedure in self.procedures'. A date range containing no "
           "submissions therefore raises TypeError. The date pickers default to "
           "the last 180 days, so a fresh install or a quiet period hits this -- "
           "and because TurnaroundTime builds its report during App.__init__, it "
           "stops the application from opening. Delete this xfail when fixed.",
)
def test_report_makers_tolerate_an_empty_range(graph):
    """
    A date range containing no submissions must produce an empty report, not an
    exception.
    """
    from datetime import date

    from backend.excel.reports import ReportMaker, TurnaroundMaker

    start = date(1990, 1, 1)
    end = date(1990, 12, 31)

    assert not ReportMaker(start_date=start, end_date=end).procedures
    assert TurnaroundMaker(start_date=start, end_date=end,
                           submission_types=None).df is not None


@pytest.mark.xfail(
    strict=True,
    reason="Same root cause as test_report_makers_tolerate_an_empty_range: "
           "ReportMaker.procedures is None rather than [] when nothing matches, "
           "so the organization filter comprehension at reports.py:50 raises.",
)
def test_report_maker_organization_filter_on_an_empty_range(graph):
    """Filtering by organization over an empty range must not raise."""
    from datetime import date

    from backend.excel.reports import ReportMaker

    report = ReportMaker(start_date=date(1990, 1, 1), end_date=date(1990, 12, 31),
                         organizations=[graph["labs"][0].name])
    assert not report.procedures
