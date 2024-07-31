'''
Contains functions for generating summary reports
'''
from pandas import DataFrame, ExcelWriter
import logging, re
from pathlib import Path
from datetime import date, timedelta
from typing import List, Tuple, Any
from backend.db.models import BasicSubmission
from tools import jinja_template_loading, html_to_pdf, get_first_blank_df_row, \
    row_map
from PyQt6.QtWidgets import QWidget
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()


class ReportMaker(object):

    def __init__(self, start_date: date, end_date: date):
        self.start_date = start_date
        self.end_date = end_date
        self.subs = BasicSubmission.query(start_date=start_date, end_date=end_date)
        self.detailed_df, self.summary_df = self.make_report_xlsx()
        self.html = self.make_report_html(df=self.summary_df)

    def make_report_xlsx(self) -> Tuple[DataFrame, DataFrame]:
        """
        create the dataframe for a report

        Returns:
            DataFrame: output dataframe
        """
        df = DataFrame.from_records([item.to_dict(report=True) for item in self.subs])
        # NOTE: put submissions with the same lab together
        df = df.sort_values("submitting_lab")
        # NOTE: aggregate cost and sample count columns
        df2 = df.groupby(["submitting_lab", "extraction_kit"]).agg(
            {'extraction_kit': 'count', 'cost': 'sum', 'sample_count': 'sum'})
        df2 = df2.rename(columns={"extraction_kit": 'run_count'})
        # logger.debug(f"Output daftaframe for xlsx: {df2.columns}")
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
        # logger.debug(f"Report DataFrame: {df}")
        for ii, row in enumerate(df.iterrows()):
            # logger.debug(f"Row {ii}: {row}")
            lab = row[0][0]
            # logger.debug(type(row))
            # logger.debug(f"Old lab: {old_lab}, Current lab: {lab}")
            # logger.debug(f"Name: {row[0][1]}")
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
        # logger.debug(output)
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
        # NOTE: html_to_pdf doesn't function without a PyQt6 app
        if isinstance(obj, QWidget):
            logger.info(f"We're in PyQt environment, writing PDF to: {filename}")
            html_to_pdf(html=self.html, output_file=filename)
        else:
            logger.info("Not in PyQt. Skipping PDF writing.")
        # logger.debug("Finished writing.")
        self.writer = ExcelWriter(filename.with_suffix(".xlsx"), engine='openpyxl')
        self.summary_df.to_excel(self.writer, sheet_name="Report")
        self.detailed_df.to_excel(self.writer, sheet_name="Details", index=False)
        self.fix_up_xl()
        # logger.debug(f"Writing report to: {filename}")
        self.writer.close()

    def fix_up_xl(self):
        """
        Handles formatting of xl file.
        """        
        # logger.debug(f"Updating worksheet")
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
        # logger.debug(f"Blank row index = {blank_row}")
        for col in range(3, 6):
            col_letter = row_map[col]
            worksheet.cell(row=blank_row, column=col, value=f"=SUM({col_letter}2:{col_letter}{str(blank_row - 1)})")
        for cell in worksheet['D']:
            if cell.row > 1:
                cell.style = 'Currency'


