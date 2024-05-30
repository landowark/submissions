'''
Contains widgets specific to the submission summary and submission details.
'''
import logging
from pprint import pformat
from PyQt6.QtWidgets import QTableView, QMenu
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
from PyQt6.QtGui import QAction, QCursor
from backend.db.models import BasicSubmission
from backend.excel import make_report_html, make_report_xlsx
from tools import Report, Result, row_map, get_first_blank_df_row, html_to_pdf
# from xhtml2pdf import pisa
from .functions import select_save_file, select_open_file
from .misc import ReportDatePicker
import pandas as pd
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(f"submissions.{__name__}")

class pandasModel(QAbstractTableModel):
    """
    pandas model for inserting summary sheet into gui
    NOTE: Copied from Stack Overflow. I have no idea how it actually works.
    """
    def __init__(self, data) -> None:
        QAbstractTableModel.__init__(self)
        self._data = data

    def rowCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of rows in data
        """
        return self._data.shape[0]

    def columnCount(self, parent=None) -> int:
        """
        does what it says

        Args:
            parent (_type_, optional): _description_. Defaults to None.

        Returns:
            int: number of columns in data
        """        
        return self._data.shape[1]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole) -> str|None:
        if index.isValid():
            if role == Qt.ItemDataRole.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._data.columns[col]
        return None
        
class SubmissionsSheet(QTableView):
    """
    presents submission summary to user in tab1
    """    
    def __init__(self, parent) -> None:
        """
        initialize

        Args:
            ctx (dict): settings passed from gui
        """        
        super().__init__(parent)
        self.app = self.parent()
        self.report = Report()
        self.setData()
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self.setSortingEnabled(True)
        self.doubleClicked.connect(lambda x: BasicSubmission.query(id=x.sibling(x.row(), 0).data()).show_details(self))
 
    def setData(self) -> None: 
        """
        sets data in model
        """        
        self.data = BasicSubmission.submissions_to_df()
        try:
            self.data['Id'] = self.data['Id'].apply(str)
            self.data['Id'] = self.data['Id'].str.zfill(3)
        except KeyError as e:
            logger.error(f"Could not alter id to string due to {e}")
        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(pandasModel(self.data))
        self.setModel(proxyModel)
        
    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """        
        # logger.debug(event().__dict__)
        id = self.selectionModel().currentIndex()
        id = id.sibling(id.row(),0).data()
        submission = BasicSubmission.query(id=id)
        self.menu = QMenu(self)
        self.con_actions = submission.custom_context_events()
        for k in self.con_actions.keys():
            # logger.debug(f"Adding {k}")
            action = QAction(k, self)
            action.triggered.connect(lambda _, action_name=k: self.triggered_action(action_name=action_name))
            self.menu.addAction(action)
        # add other required actions
        self.menu.popup(QCursor.pos())

    def triggered_action(self, action_name:str):
        """
        Calls the triggered action from the context menu

        Args:
            action_name (str): name of the action from the menu
        """        
        # logger.debug(f"Action: {action_name}")
        # logger.debug(f"Responding with {self.con_actions[action_name]}")
        func = self.con_actions[action_name]
        func(obj=self)

    def link_extractions(self):
        """
        Pull extraction logs into the db
        """        
        self.link_extractions_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def link_extractions_function(self):
        """
        Link extractions from runlogs to imported submissions

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        fname = select_open_file(self, file_extension="csv")
        with open(fname.__str__(), 'r') as f:
            # split csv on commas
            runs = [col.strip().split(",") for col in f.readlines()]
        count = 0
        for run in runs:
            new_run = dict(
                    start_time=run[0].strip(), 
                    rsl_plate_num=run[1].strip(), 
                    sample_count=run[2].strip(), 
                    status=run[3].strip(),
                    experiment_name=run[4].strip(),
                    end_time=run[5].strip()
                )
            # NOTE: elution columns are item 6 in the comma split list to the end
            for ii in range(6, len(run)):
                new_run[f"column{str(ii-5)}_vol"] = run[ii]
            # NOTE: Lookup imported submissions
            sub = BasicSubmission.query(rsl_plate_num=new_run['rsl_plate_num'])
            # NOTE: If no such submission exists, move onto the next run
            if sub == None:
                continue
            try:
                # logger.debug(f"Found submission: {sub.rsl_plate_num}")
                count += 1
            except AttributeError:
                continue
            sub.set_attribute('extraction_info', new_run)
            sub.save()
        self.report.add_result(Result(msg=f"We added {count} logs to the database.", status='Information'))

    def link_pcr(self):
        """
        Pull pcr logs into the db
        """        
        self.link_pcr_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def link_pcr_function(self):
        """
        Link PCR data from run logs to an imported submission

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        fname = select_open_file(self, file_extension="csv")
        with open(fname.__str__(), 'r') as f:
            # NOTE: split csv rows on comma
            runs = [col.strip().split(",") for col in f.readlines()]
        count = 0
        for run in runs:
            new_run = dict(
                    start_time=run[0].strip(), 
                    rsl_plate_num=run[1].strip(), 
                    biomek_status=run[2].strip(), 
                    quant_status=run[3].strip(),
                    experiment_name=run[4].strip(),
                    end_time=run[5].strip()
                )
            # NOTE: lookup imported submission
            sub = BasicSubmission.query(rsl_number=new_run['rsl_plate_num'])
            # NOTE: if imported submission doesn't exist move on to next run
            if sub == None:
                continue
            # try:
            #     logger.debug(f"Found submission: {sub.rsl_plate_num}")
            # except AttributeError:
            #     continue
            sub.set_attribute('pcr_info', new_run)
            # NOTE: check if pcr_info already exists
            sub.save()
        self.report.add_result(Result(msg=f"We added {count} logs to the database.", status='Information'))
        
    def generate_report(self):
        """
        Make a report
        """        
        self.generate_report_function()
        self.app.report.add_result(self.report)
        self.report = Report()
        self.app.result_reporter()

    def generate_report_function(self):
        """
        Generate a summary of activities for a time period

        Args:
            obj (QMainWindow): original app window

        Returns:
            Tuple[QMainWindow, dict]: Collection of new main app window and result dict
        """    
        report = Report()
        # NOTE: ask for date ranges
        dlg = ReportDatePicker()
        if dlg.exec():
            info = dlg.parse_form()
            # logger.debug(f"Report info: {info}")
            # NOTE: find submissions based on date range
            subs = BasicSubmission.query(start_date=info['start_date'], end_date=info['end_date'])
            # NOTE: convert each object to dict
            records = [item.to_dict(report=True) for item in subs]
            logger.debug(f"Records: {pformat(records)}")
            # NOTE: make dataframe from record dictionaries
            detailed_df, summary_df = make_report_xlsx(records=records)
            html = make_report_html(df=summary_df, start_date=info['start_date'], end_date=info['end_date'])
            # NOTE: get save location of report
            fname = select_save_file(obj=self, default_name=f"Submissions_Report_{info['start_date']}-{info['end_date']}.pdf", extension="pdf")
            html_to_pdf(html=html, output_file=fname)
            writer = pd.ExcelWriter(fname.with_suffix(".xlsx"), engine='openpyxl')
            summary_df.to_excel(writer, sheet_name="Report")
            detailed_df.to_excel(writer, sheet_name="Details", index=False)
            worksheet: Worksheet = writer.sheets['Report']
            for idx, col in enumerate(summary_df, start=1):  # loop through all columns
                series = summary_df[col]
                max_len = max((
                    series.astype(str).map(len).max(),  # len of largest item
                    len(str(series.name))  # len of column name/header
                    )) + 20  # adding a little extra space
                try:
                    # NOTE: Convert idx to letter
                    col_letter = chr(ord('@') + idx)
                    worksheet.column_dimensions[col_letter].width = max_len
                except ValueError:
                    pass
            blank_row = get_first_blank_df_row(summary_df) + 1
            # logger.debug(f"Blank row index = {blank_row}")
            for col in range(3,6):
                col_letter = row_map[col]
                worksheet.cell(row=blank_row, column=col, value=f"=SUM({col_letter}2:{col_letter}{str(blank_row-1)})")
            for cell in worksheet['D']:
                if cell.row > 1:
                    cell.style = 'Currency'
            writer.close()
        self.report.add_result(report)
