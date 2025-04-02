"""
Contains functions for generating summary reports
"""
import itertools
import sys
from pprint import pformat
from pandas import DataFrame, ExcelWriter
import logging
from pathlib import Path
from datetime import date
from typing import Tuple
from backend.db.models import BasicSubmission, IridaControl
from tools import jinja_template_loading, get_first_blank_df_row, row_map
from PyQt6.QtWidgets import QWidget
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()


class ReportArchetype(object):
    """
    Made for children to inherit 'write_report", etc.
    """

    def write_report(self, filename: Path | str, obj: QWidget | None = None):
        """
        Writes info to files.

        Args:
            filename (Path | str): Basename of output file
            obj (QWidget | None, optional): Parent object. Defaults to None.
        """
        if isinstance(filename, str):
            filename = Path(filename)
        filename = filename.absolute()
        self.writer = ExcelWriter(filename.with_suffix(".xlsx"), engine='openpyxl')
        self.df.index += 1
        self.df.to_excel(self.writer, sheet_name=self.sheet_name)
        self.writer.close()


class ReportMaker(object):

    def __init__(self, start_date: date, end_date: date, organizations: list | None = None):
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.subs = BasicSubmission.query(start_date=start_date, end_date=end_date, page_size=0)
        if organizations is not None:
            self.subs = [sub for sub in self.subs if sub.submitting_lab.name in organizations]
        self.detailed_df, self.summary_df = self.make_report_xlsx()
        self.html = self.make_report_html(df=self.summary_df)

    def make_report_xlsx(self) -> Tuple[DataFrame, DataFrame]:
        """
        create the dataframe for a report

        Returns:
            DataFrame: output dataframe
        """
        if not self.subs:
            return DataFrame(), DataFrame()
        df = DataFrame.from_records([item.to_dict(report=True) for item in self.subs])
        # NOTE: put submissions with the same lab together
        df = df.sort_values("submitting_lab")
        # NOTE: aggregate cost and sample count columns
        df2 = df.groupby(["submitting_lab", "extraction_kit"]).agg(
            {'extraction_kit': 'count', 'cost': 'sum', 'sample_count': 'sum'})
        df2 = df2.rename(columns={"extraction_kit": 'run_count'})
        df = df.drop('id', axis=1)
        df = df.sort_values(['submitting_lab', "submitted_date"])
        return df, df2

    def make_report_html(self, df: DataFrame) -> str:

        """
        generates html from the report dataframe

        Args:
            df (DataFrame): input dataframe generated from 'make_report_xlsx' above
            start_date (date): starting date of the report period
            end_date (date): ending date of the report period

        Returns:
            str: html string
        """
        old_lab = ""
        output = []
        for row in df.iterrows():
            lab = row[0][0]
            data = [item for item in row[1]]
            kit = dict(name=row[0][1], cost=data[1], run_count=int(data[0]), sample_count=int(data[2]))
            # NOTE: if this is the same lab as before add together
            if lab == old_lab:
                output[-1]['kits'].append(kit)
                output[-1]['total_cost'] += kit['cost']
                output[-1]['total_samples'] += kit['sample_count']
                output[-1]['total_runs'] += kit['run_count']
            # NOTE: if not the same lab, make a new one
            else:
                adder = dict(lab=lab, kits=[kit], total_cost=kit['cost'], total_samples=kit['sample_count'],
                             total_runs=kit['run_count'])
                output.append(adder)
            old_lab = lab
        dicto = {'start_date': self.start_date, 'end_date': self.end_date, 'labs': output}
        temp = env.get_template('summary_report.html')
        html = temp.render(input=dicto)
        return html

    def write_report(self, filename: Path | str, obj: QWidget | None = None):
        """
        Writes info to files.

        Args:
            filename (Path | str): Basename of output file
            obj (QWidget | None, optional): Parent object. Defaults to None.
        """
        if isinstance(filename, str):
            filename = Path(filename)
        filename = filename.absolute()
        self.writer = ExcelWriter(filename.with_suffix(".xlsx"), engine='openpyxl')
        self.summary_df.to_excel(self.writer, sheet_name="Report")
        self.detailed_df.to_excel(self.writer, sheet_name="Details", index=False)
        self.fix_up_xl()
        self.writer.close()

    def fix_up_xl(self):
        """
        Handles formatting of xl file, mediocrely.
        """
        worksheet: Worksheet = self.writer.sheets['Report']
        for idx, col in enumerate(self.summary_df, start=1):  # NOTE: loop through all columns
            series = self.summary_df[col]
            max_len = max((
                series.astype(str).map(len).max(),  # NOTE: len of largest item
                len(str(series.name))  # NOTE: len of column name/header
            )) + 20  # NOTE: adding a little extra space
            try:
                # NOTE: Convert idx to letter
                col_letter = chr(ord('@') + idx)
                worksheet.column_dimensions[col_letter].width = max_len
            except ValueError as e:
                logger.error(f"Couldn't resize column {col} due to {e}")
        blank_row = get_first_blank_df_row(self.summary_df) + 1
        for col in range(3, 6):
            col_letter = row_map[col]
            worksheet.cell(row=blank_row, column=col, value=f"=SUM({col_letter}2:{col_letter}{str(blank_row - 1)})")
        for cell in worksheet['D']:
            if cell.row > 1:
                cell.style = 'Currency'


class TurnaroundMaker(ReportArchetype):

    def __init__(self, start_date: date, end_date: date, submission_type: str):
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.subs = BasicSubmission.query(start_date=start_date, end_date=end_date,
                                          submission_type_name=submission_type, page_size=0)
        records = [self.build_record(sub) for sub in self.subs]
        self.df = DataFrame.from_records(records)
        self.sheet_name = "Turnaround"

    @classmethod
    def build_record(cls, sub: BasicSubmission) -> dict:
        """
        Build a turnaround dictionary from a submission

        Args:
            sub (BasicSubmission): The submission to be processed.

        Returns:

        """
        if 'pytest' not in sys.modules:
            from tools import ctx
        else:
            from test_settings import ctx
        days = sub.turnaround_time
        try:
            tat = sub.get_default_info("turnaround_time")
        except (AttributeError, KeyError):
            tat = None
        if not tat:
            tat = ctx.TaT_threshold
        try:
            tat_ok = days <= tat
        except TypeError:
            return {}
        return dict(name=str(sub.rsl_plate_num), days=days, submitted_date=sub.submitted_date,
                    completed_date=sub.completed_date, acceptable=tat_ok)


class ConcentrationMaker(ReportArchetype):

    def __init__(self, start_date: date, end_date: date, submission_type: str = "Bacterial Culture",
                 controls_only: bool = True):
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.subs = BasicSubmission.query(start_date=start_date, end_date=end_date,
                                          submission_type_name=submission_type, page_size=0)
        # self.known_controls = list(itertools.chain.from_iterable([sub.controls for sub in self.subs]))
        self.samples = list(itertools.chain.from_iterable([sub.get_provisional_controls(controls_only=controls_only) for sub in self.subs]))
        self.records = [self.build_record(sample) for sample in self.samples]
        self.df = DataFrame.from_records(self.records)
        self.sheet_name = "Concentration"

    @classmethod
    def build_record(cls, control) -> dict:

        positive = not control.submitter_id.lower().startswith("en")
        try:
            concentration = float(control.concentration)
        except (TypeError, ValueError):
            concentration = 0.0
        return dict(name=control.submitter_id,
                    submission=str(control.submission), concentration=concentration,
                    submitted_date=control.submitted_date, positive=positive)


class ChartReportMaker(ReportArchetype):

    def __init__(self, df: DataFrame, sheet_name):
        self.df = df
        self.sheet_name = sheet_name
