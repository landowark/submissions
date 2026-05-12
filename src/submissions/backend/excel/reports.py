"""
Contains functions for generating summary reports
"""
from __future__ import annotations
import re, sys, logging
from pprint import pformat
from pandas import DataFrame, ExcelWriter
from pathlib import Path
from datetime import date
from typing import Tuple, List, TYPE_CHECKING
from backend.db.models import Procedure 
from tools import jinja_template_loading, get_first_blank_df_row, row_map, flatten_list
from PyQt6.QtWidgets import QWidget
from openpyxl.worksheet.worksheet import Worksheet
if TYPE_CHECKING:
    from backend.db.models import ClientSubmission, Results

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
        if not getattr(self, "sheet_name", None):
            self.sheet_name = filename.stem
        self.df.to_excel(self.writer, sheet_name=self.sheet_name)
        self.writer.close()


class ReportMaker(object):

    def __init__(self, start_date: date, end_date: date, organizations: list | None = None):
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.procedures = Procedure.query(start_date=start_date, end_date=end_date, page_size=0)
        if organizations is not None:
            self.procedures = [procedure for procedure in self.procedures if procedure.run.clientsubmission.clientlab.name in organizations]
        self.detailed_df, self.summary_df = self.make_report_xlsx()
        self.html = self.make_report_html(df=self.summary_df)

    def make_report_xlsx(self) -> Tuple[DataFrame, DataFrame]:
        """
        create the dataframe for a report

        Returns:
            DataFrame: output dataframe
        """
        if not self.procedures:
            return DataFrame(), DataFrame()
        df = DataFrame.from_records([item.details_dict for item in self.procedures])
        # NOTE: put procedure with the same lab together
        df = df.sort_values("clientlab")
        # NOTE: aggregate cost and sample count columns
        df2 = df.groupby(["clientlab", "proceduretype"]).agg(
            {'proceduretype': 'count', 'cost': 'sum', 'sample_count': 'sum'})
        df2 = df2.rename(columns={"proceduretype": 'run_count'})
        try:
            df = df.drop('id', axis=1)
        except KeyError:
            pass
        df = df.sort_values(['clientlab', "started_date"])
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
        from backend.db.models import ClientSubmission
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.subs = ClientSubmission.query(start_date=start_date, end_date=end_date,
                                   submissiontype=submission_type, page_size=0)
        records = [self.build_record(sub) for sub in self.subs]
        self.df = DataFrame.from_records(records)
        self.sheet_name = "Turnaround"

    @classmethod
    def build_record(cls, sub: ClientSubmission) -> dict:
        """
        Build a turnaround dictionary from a procedure

        Args:
            sub (ClientSubmission): The procedure to be processed.

        Returns:

        """
        return dict(name=str(sub.submitter_plate_id), days=sub.turnaround_time, submitted_date=sub.submitted_date,
                    completed_date=sub.completed_date, acceptable=sub.met_turnaround_time)


class ConcentrationMaker(ReportArchetype):

    def __init__(self, start_date: date, end_date: date, submission_type: str = "Bacterial Culture",
                 include: List[str] = []):
        from backend.db.models import ClientSubmission
        logger.debug(f"Initializing ConcentrationMaker with start_date={start_date}, end_date={end_date}, submission_type={submission_type}, include={include}")
        self.start_date = start_date
        self.end_date = end_date
        # NOTE: Set page size to zero to override limiting query size.
        self.subs = ClientSubmission.query(start_date=start_date, end_date=end_date,
                                   submissiontype=submission_type, page_size=0)
        
        self.results = []
        for clientsubmission in self.subs:
            for result in clientsubmission.get_procedure_sample_results(include=[s.lower() for s in include]):
                output = self.build_record(result)
                self.results.append(output)
        self.df = DataFrame.from_records(self.results)
        logger.debug(self.df)
        self.sheet_name = "Concentration"

    @classmethod
    def build_record(cls, results: Results) -> dict:
        sample = results.sampleprocedureassociation.sample
        match sample.is_control:
            case 1:
                control_type = "Positive Control"
            case -1:
                control_type = "Negative Control"
            case _:
                control_type = "Sample"
        procedure = results.procedure.name
        output = results.result
        output.update(dict(control_type=control_type, procedure=procedure, sample_id=sample.sample_id, submitted_date=results.procedure.run.clientsubmission.submitted_date))
        return output

class ChartReportMaker(ReportArchetype):

    def __init__(self, df: DataFrame):
        self.df = df
