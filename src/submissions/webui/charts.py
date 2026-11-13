"""
Charts and reports for the web UI. Ports the Qt InfoPane tabs: PCR Controls, Concentrations,
Turnaround Times and Cost Report.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import base64
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
import webview

TITLES = {"irida":"Irida Controls", "pcr": "PCR Controls", "concentrations": "Concentrations", "turnaround": "Turnaround Times", "cost": "Cost Report"}
# NOTE: Results type behind each control-chart tab (InfoPane.results_type in the Qt app).
RESULTS_TYPES = {"pcr": "Diomni PCR", "concentrations": "Qubit"}

PRINT_BAR = """
<div id="print-bar" style="padding: 6px 0 10px;"><button type="button" onclick="window.print()">Save PDF / Print</button></div>
<style>@media print { #print-bar { display: none; } }</style>
"""


def _dates(filters: dict) -> tuple[datetime, datetime]:
    start = datetime.combine(date.fromisoformat(filters["start_date"]), datetime.min.time())
    end = datetime.combine(date.fromisoformat(filters["end_date"]), datetime.max.time())
    return start, end


def _months(start: datetime, end: datetime) -> int:
    # NOTE: Same as InfoPane.diff_month.
    return abs((start.year - end.year) * 12 + start.month - end.month)

def _names(result) -> list[str]:
    """
    Names from a BaseClass.query() result, which is a single object (not a list) on exactly one match.
    """
    if result is None:
        return []
    if not isinstance(result, list):
        result = [result]
    return [item.name for item in result]

def filter_options(name: str) -> dict:
    """
    Default filters and their choices for a tab.
    """
    from backend.db.models import SubmissionType, ClientLab
    today = date.today()
    options = dict(start_date=(today - timedelta(days=180)).isoformat(), end_date=today.isoformat())
    if name in RESULTS_TYPES:
        options["submission_types"] = [st.name for st in SubmissionType.find_by_resultstype(RESULTS_TYPES[name])]
        options["control_types"] = [dict(name="Positive", checked=True), dict(name="Negative", checked=True),
                                    dict(name="Samples", checked=False)]
    elif name == "turnaround":
        options["turnaround_types"] = ["All"] + _names(SubmissionType.query())
    elif name == "cost":
        options["clientlabs"] = _names(ClientLab.query())
    elif name == "irida":
        from backend.irida import load_projects
        try:
            options["projects"] = [""] + list(load_projects().keys())
        except ValueError as e:
            options["projects"] = [""]
            options["error"] = str(e)
    return options

def _maker(name: str, filters: dict):
    """
    Builds the tab's report maker from its filters.

    :return: The report maker and the chart settings.
    """
    from backend.excel.reports import PCRMaker, ConcentrationMaker, TurnaroundMaker, ReportMaker
    from backend.db.models import SubmissionType
    start, end = _dates(filters)
    if name in RESULTS_TYPES:
        submission_types = filters.get("submission_types")
        if submission_types is None:
            submission_types = _names(SubmissionType.query())
        settings = dict(start_date=start, end_date=end, include=filters.get("include", []),
                        submission_types=submission_types, months=_months(start, end))
        maker_class = PCRMaker if name == "pcr" else ConcentrationMaker
        return maker_class(**settings), settings
    if name == "turnaround":
        submission_type = None if filters.get("submission_type", "All") == "All" else filters["submission_type"]
        return (TurnaroundMaker(start_date=start, end_date=end, submission_types=submission_type),
                dict(start_date=start, end_date=end))
    if name == "cost":
        return ReportMaker(start_date=start, end_date=end, organizations=filters.get("clientlabs", [])), {}
    if name == "irida":
        from backend.excel.reports import ChartReportMaker
        fig = _kraken_figure(filters)
        if fig is None:
            raise ValueError("No data to save for the selected project and dates.")
        return ChartReportMaker(df=fig.df), {}
    raise ValueError(f"Unknown chart: {name}")

_irida_cache: dict = {}

def _kraken_figure(filters: dict):
    """
    Pulls (or reuses) the IRIDA data for the filters and builds the Kraken chart, as KrakenViewer.chart_maker_function does.
    """
    from tools import ctx
    from backend.irida import connection, load_projects, grab_data, kraken_dataframe
    from backend.visualizations import KrakenFigure
    metadata_only = bool(filters.get("metadata_only", True))
    key = (filters["project"], filters["start_date"], filters["end_date"], metadata_only)
    start, end = _dates(filters)
    if key not in _irida_cache:
        url, token = connection(ctx)
        data = grab_data(url, token, load_projects()[filters["project"]], start, end, metadata_only=metadata_only)
        _irida_cache.clear()
        _irida_cache[key] = kraken_dataframe(data, metadata_only=metadata_only)
    df = _irida_cache[key]
    if df.empty:
        return None
    settings = dict(project=filters["project"], start_date=start, end_date=end, months=_months(start, end),
                    species_or_genus="Species" if metadata_only else "Genus")
    # NOTE: KrakenFigure adds columns to its dataframe, so give it a copy of the cached one.
    return KrakenFigure(df=df.copy(), settings=settings)

def chart(name: str, filters: dict) -> dict:
    """
    :return: {figure: plotly JSON}, {html, has_data} for the cost report, or {message} when there's nothing to show.
    """
    if name == "irida":
        if not filters.get("project"):
            return dict(message="Choose a project.")
        try:
            fig = _kraken_figure(filters)
        except Exception as e:
            logger.exception(f"Couldn't load IRIDA Next data: {e}")
            return dict(message=f"Couldn't load data from IRIDA Next: {e}")
        if fig is None:
            return dict(message="No data available for the selected project and dates.")
        return dict(figure=fig.to_json())
    from backend.visualizations import PCRFigure, ConcentrationsChart, TurnaroundChart
    from backend.db.models import SubmissionType
    try:
        maker, settings = _maker(name, filters)
    except (AttributeError, TypeError) as e:
        logger.exception(f"Couldn't build {name} report: {e}")
        return dict(message="No data available for the selected date range and filters.")
    if name == "cost":
        return dict(html=maker.html, has_data=bool(maker.procedures))
    if maker.df.empty:
        return dict(message="No data available for the selected date range and filters.")
    match name:
        case "pcr":
            fig = PCRFigure(df=maker.df, settings=settings)
        case "concentrations":
            fig = ConcentrationsChart(df=maker.df, settings=settings)
        case _:
            threshold = None
            if filters.get("submission_type", "All") != "All":
                subtype = SubmissionType.query(name=filters["submission_type"])
                if subtype and subtype.turnaround_time:
                    threshold = subtype.turnaround_time.days + 0.5
            start, end = _dates(filters)
            fig = TurnaroundChart(df=maker.df, settings=settings, modes=[], threshold=threshold, months=_months(start, end))
    return dict(figure=fig.to_json())  

def save_data(name: str, filters: dict, choose_save_file: Callable[[str, str], str | None]) -> dict:
    maker, _ = _maker(name, filters)
    start, end = _dates(filters)
    path = choose_save_file(f"{TITLES[name]} Report {start:%Y%m%d} - {end:%Y%m%d}", "xlsx")
    if not path:
        return dict(ok=False, message="Save cancelled.")
    maker.write_report(path)
    return dict(ok=True, message=f"Saved {path}")


def save_png(name: str, filters: dict, data_url: str, choose_save_file: Callable[[str, str], str | None]) -> dict:
    start, end = _dates(filters)
    path = choose_save_file(f"{TITLES[name]} {start:%Y%m%d} - {end:%Y%m%d}", "png")
    if not path:
        return dict(ok=False, message="Save cancelled.")
    Path(path).write_bytes(base64.b64decode(data_url.partition(",")[2]))
    return dict(ok=True, message=f"Saved {path}")


def open_report_window(filters: dict) -> None:
    """
    Opens the cost report in its own window so it can be printed / saved as PDF.
    """
    maker, _ = _maker("cost", filters)
    html = maker.html
    html = html.replace("<body>", "<body>" + PRINT_BAR, 1) if "<body>" in html else PRINT_BAR + html
    webview.create_window("Cost Report", html=html, width=1000, height=800)
