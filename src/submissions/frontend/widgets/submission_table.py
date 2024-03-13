'''
Contains widgets specific to the submission summary and submission details.
'''
import logging, json
from pprint import pformat
from PyQt6.QtWidgets import QTableView, QMenu
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
from PyQt6.QtGui import QAction, QCursor
from backend.db.models import BasicSubmission
from backend.excel import make_report_html, make_report_xlsx
from tools import Report, Result, row_map, get_first_blank_df_row
from xhtml2pdf import pisa
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
            self.data['id'] = self.data['id'].apply(str)
            self.data['id'] = self.data['id'].str.zfill(3)
        except KeyError:
            pass
        
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
            logger.debug(f"Adding {k}")
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
        logger.debug(f"Action: {action_name}")
        logger.debug(f"Responding with {self.con_actions[action_name]}")
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
            # elution columns are item 6 in the comma split list to the end
            for ii in range(6, len(run)):
                new_run[f"column{str(ii-5)}_vol"] = run[ii]
            # Lookup imported submissions
            # sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=new_run['rsl_plate_num'])
            # sub = lookup_submissions(ctx=obj.ctx, rsl_number=new_run['rsl_plate_num'])
            sub = BasicSubmission.query(rsl_number=new_run['rsl_plate_num'])
            # If no such submission exists, move onto the next run
            if sub == None:
                continue
            try:
                logger.debug(f"Found submission: {sub.rsl_plate_num}")
                count += 1
            except AttributeError:
                continue
            if sub.extraction_info != None:
                existing = json.loads(sub.extraction_info)
            else:
                existing = None
            # Check if the new info already exists in the imported submission
            try:
                if json.dumps(new_run) in sub.extraction_info:
                    logger.debug(f"Looks like we already have that info.")
                    continue
            except TypeError:
                pass
            # Update or create the extraction info
            if existing != None:
                try:
                    logger.debug(f"Updating {type(existing)}: {existing} with {type(new_run)}: {new_run}")
                    existing.append(new_run)
                    logger.debug(f"Setting: {existing}")
                    sub.extraction_info = json.dumps(existing)
                except TypeError:
                    logger.error(f"Error updating!")
                    sub.extraction_info = json.dumps([new_run])
                logger.debug(f"Final ext info for {sub.rsl_plate_num}: {sub.extraction_info}")
            else:
                sub.extraction_info = json.dumps([new_run])        
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
            # split csv rows on comma
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
            # lookup imported submission
            # sub = lookup_submission_by_rsl_num(ctx=obj.ctx, rsl_num=new_run['rsl_plate_num'])
            # sub = lookup_submissions(ctx=obj.ctx, rsl_number=new_run['rsl_plate_num'])
            sub = BasicSubmission.query(rsl_number=new_run['rsl_plate_num'])
            # if imported submission doesn't exist move on to next run
            if sub == None:
                continue
            try:
                logger.debug(f"Found submission: {sub.rsl_plate_num}")
            except AttributeError:
                continue
            # check if pcr_info already exists
            if hasattr(sub, 'pcr_info') and sub.pcr_info != None:
                existing = json.loads(sub.pcr_info)
            else:
                existing = None
            # check if this entry already exists in imported submission
            try:
                if json.dumps(new_run) in sub.pcr_info:
                    logger.debug(f"Looks like we already have that info.")
                    continue
                else:
                    count += 1
            except TypeError:
                logger.error(f"No json to dump")
            if existing != None:
                try:
                    logger.debug(f"Updating {type(existing)}: {existing} with {type(new_run)}: {new_run}")
                    existing.append(new_run)
                    logger.debug(f"Setting: {existing}")
                    sub.pcr_info = json.dumps(existing)
                except TypeError:
                    logger.error(f"Error updating!")
                    sub.pcr_info = json.dumps([new_run])
                logger.debug(f"Final ext info for {sub.rsl_plate_num}: {sub.pcr_info}")
            else:
                sub.pcr_info = json.dumps([new_run])        
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
        # ask for date ranges
        dlg = ReportDatePicker()
        if dlg.exec():
            info = dlg.parse_form()
            logger.debug(f"Report info: {info}")
            # find submissions based on date range
            subs = BasicSubmission.query(start_date=info['start_date'], end_date=info['end_date'])
            # convert each object to dict
            records = [item.report_dict() for item in subs]
            logger.debug(f"Records: {pformat(records)}")
            # make dataframe from record dictionaries
            detailed_df, summary_df = make_report_xlsx(records=records)
            html = make_report_html(df=summary_df, start_date=info['start_date'], end_date=info['end_date'])
            # get save location of report
            fname = select_save_file(obj=self, default_name=f"Submissions_Report_{info['start_date']}-{info['end_date']}.pdf", extension="pdf")
            with open(fname, "w+b") as f:
                pisa.CreatePDF(html, dest=f)
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
                    # worksheet.column_dimensions[get_column_letter(idx=idx)].width = max_len
                    # Convert idx to letter
                    col_letter = chr(ord('@') + idx)
                    worksheet.column_dimensions[col_letter].width = max_len
                except ValueError:
                    pass
            blank_row = get_first_blank_df_row(summary_df) + 1
            logger.debug(f"Blank row index = {blank_row}")
            for col in range(3,6):
                col_letter = row_map[col]
                worksheet.cell(row=blank_row, column=col, value=f"=SUM({col_letter}2:{col_letter}{str(blank_row-1)})")
            for cell in worksheet['D']:
                if cell.row > 1:
                    cell.style = 'Currency'
            writer.close()
        self.report.add_result(report)
