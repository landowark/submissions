'''
Contains widgets specific to the submission summary and submission details.
'''
import base64
from datetime import datetime
from io import BytesIO
import pprint
from PyQt6 import QtPrintSupport
from PyQt6.QtWidgets import (
    QVBoxLayout, QDialog, QTableView,
    QTextEdit, QPushButton, QScrollArea, 
    QMessageBox, QFileDialog, QMenu, QLabel,
    QDialogButtonBox, QToolBar
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
from PyQt6.QtGui import QAction, QCursor, QPixmap, QPainter
from backend.db.functions import submissions_to_df
from backend.db.models import BasicSubmission
from backend.excel import make_hitpicks, make_report_html, make_report_xlsx
from tools import check_if_app, Settings, Report, Result
from tools import jinja_template_loading
from xhtml2pdf import pisa
from pathlib import Path
import logging
from .pop_ups import QuestionAsker, AlertPop
from ..visualizations import make_plate_barcode, make_plate_map, make_plate_map_html
from .functions import select_save_file, select_open_file
from .misc import ReportDatePicker
import pandas as pd
from getpass import getuser
import json

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

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
        # self.ctx = ctx
        self.report = Report()
        self.setData()
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        self.setSortingEnabled(True)
        
        self.doubleClicked.connect(self.show_details)
 
    def setData(self) -> None: 
        """
        sets data in model
        """        
        self.data = submissions_to_df()
        try:
            self.data['id'] = self.data['id'].apply(str)
            self.data['id'] = self.data['id'].str.zfill(3)
        except KeyError:
            pass
        
        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(pandasModel(self.data))
        self.setModel(proxyModel)
        
    def show_details(self) -> None:
        """
        creates detailed data to show in seperate window
        """        
        logger.debug(f"Sheet.app: {self.app}")
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),0).data()
        dlg = SubmissionDetails(parent=self, id=value)
        if dlg.exec():
            pass  

    def create_barcode(self) -> None:
        """
        Generates a window for displaying barcode
        """        
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),1).data()
        logger.debug(f"Selected value: {value}")
        dlg = BarcodeWindow(value)
        if dlg.exec():
            dlg.print_barcode()

    def add_comment(self) -> None:
        """
        Generates a text editor window.
        """        
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),1).data()
        logger.debug(f"Selected value: {value}")
        dlg = SubmissionComment(ctx=self.ctx, rsl=value)
        if dlg.exec():
            dlg.add_comment()

    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """        
        self.menu = QMenu(self)
        renameAction = QAction('Delete', self)
        detailsAction = QAction('Details', self)
        barcodeAction = QAction("Print Barcode", self)
        commentAction = QAction("Add Comment", self)
        hitpickAction = QAction("Hitpicks", self)
        renameAction.triggered.connect(lambda: self.delete_item(event))
        detailsAction.triggered.connect(lambda: self.show_details())
        barcodeAction.triggered.connect(lambda: self.create_barcode())
        commentAction.triggered.connect(lambda: self.add_comment())
        hitpickAction.triggered.connect(lambda: self.hit_pick())
        self.menu.addAction(detailsAction)
        self.menu.addAction(renameAction)
        self.menu.addAction(barcodeAction)
        self.menu.addAction(commentAction)
        self.menu.addAction(hitpickAction)
        # add other required actions
        self.menu.popup(QCursor.pos())

    def delete_item(self, event):
        """
        Confirms user deletion and sends id to backend for deletion.

        Args:
            event (_type_): the item of interest
        """        
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),0).data()
        logger.debug(index)
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {index.sibling(index.row(),1).data()}?\n")
        if msg.exec():
            # delete_submission(id=value)
            BasicSubmission.query(id=value).delete()
        else:
            return
        self.setData()

    def hit_pick(self):
        """
        Extract positive samples from submissions with PCR results and export to csv.
        NOTE: For this to work for arbitrary samples, positive samples must have 'positive' in their name
        """        
        # Get all selected rows
        indices = self.selectionModel().selectedIndexes()
        # convert to id numbers
        indices = [index.sibling(index.row(), 0).data() for index in indices]
        # biomek can handle 4 plates maximum
        if len(indices) > 4:
            logger.error(f"Error: Had to truncate number of plates to 4.")
            indices = indices[:4]
        # lookup ids in the database
        # subs = [lookup_submissions(ctx=self.ctx, id=id) for id in indices]
        subs = [BasicSubmission.query(id=id) for id in indices]
        # full list of samples
        dicto = []
        # list to contain plate images
        images = []
        for iii, sub in enumerate(subs):
            # second check to make sure there aren't too many plates
            if iii > 3: 
                logger.error(f"Error: Had to truncate number of plates to 4.")
                continue
            plate_dicto = sub.hitpick_plate(plate_number=iii+1)
            if plate_dicto == None:
                continue
            image = make_plate_map(plate_dicto)
            images.append(image)
            for item in plate_dicto:
                if len(dicto) < 94:
                    dicto.append(item)
                else:
                    logger.error(f"We had to truncate the number of samples to 94.")
        logger.debug(f"We found {len(dicto)} to hitpick")
        # convert all samples to dataframe
        df = make_hitpicks(dicto)
        df = df[df.positive != False]
        logger.debug(f"Size of the dataframe: {df.shape[0]}")
        msg = AlertPop(message=f"We found {df.shape[0]} samples to hitpick", status="INFORMATION")
        msg.exec()
        if df.size == 0:
            return
        date = datetime.strftime(datetime.today(), "%Y-%m-%d")
        # ask for filename and save as csv.
        home_dir = Path(self.ctx.directory_path).joinpath(f"Hitpicks_{date}.csv").resolve().__str__()
        fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".csv")[0])
        if fname.__str__() == ".":
            logger.debug("Saving csv was cancelled.")
            return
        df.to_csv(fname.__str__(), index=False)
        # show plate maps
        for image in images:
            try:
                image.show()
            except Exception as e:
                logger.error(f"Could not show image: {e}.")

    def link_extractions(self):
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
            worksheet = writer.sheets['Report']
            for idx, col in enumerate(summary_df):  # loop through all columns
                series = summary_df[col]
                max_len = max((
                    series.astype(str).map(len).max(),  # len of largest item
                    len(str(series.name))  # len of column name/header
                    )) + 20  # adding a little extra space
                try:
                    worksheet.column_dimensions[get_column_letter(idx)].width = max_len 
                except ValueError:
                    pass
            for cell in worksheet['D']:
                if cell.row > 1:
                    cell.style = 'Currency'
            writer.close()
        self.report.add_result(report)
        
class SubmissionDetails(QDialog):
    """
    a window showing text details of submission
    """    
    def __init__(self, parent, id:int) -> None:

        super().__init__(parent)
        # self.ctx = ctx
        self.setWindowTitle("Submission Details")
        # create scrollable interior
        interior = QScrollArea()
        interior.setParent(self)
        # get submision from db
        # sub = lookup_submissions(ctx=ctx, id=id)
        sub = BasicSubmission.query(id=id)
        logger.debug(f"Submission details data:\n{pprint.pformat(sub.to_dict())}")
        self.base_dict = sub.to_dict(full_data=True)
        # don't want id
        del self.base_dict['id']
        logger.debug(f"Creating barcode.")
        if not check_if_app():
            self.base_dict['barcode'] = base64.b64encode(make_plate_barcode(self.base_dict['Plate Number'], width=120, height=30)).decode('utf-8')
        logger.debug(f"Hitpicking plate...")
        self.plate_dicto = sub.hitpick_plate()
        logger.debug(f"Making platemap...")
        self.base_dict['platemap'] = make_plate_map_html(self.plate_dicto)
        # logger.debug(f"Platemap: {self.base_dict['platemap']}")
        # logger.debug(f"platemap: {platemap}")
        # image_io = BytesIO()
        # try:
        #     platemap.save(image_io, 'JPEG')
        # except AttributeError:
        #     logger.error(f"No plate map found for {sub.rsl_plate_num}")
        # self.base_dict['platemap'] = base64.b64encode(image_io.getvalue()).decode('utf-8')
        self.template = env.get_template("submission_details.html")
        self.html = self.template.render(sub=self.base_dict)
        webview = QWebEngineView()
        webview.setMinimumSize(900, 500)
        webview.setMaximumSize(900, 500)
        webview.setHtml(self.html)
        self.layout = QVBoxLayout()
        interior.resize(900, 500)
        interior.setWidget(webview)
        self.setFixedSize(900, 500)
        # button to export a pdf version
        btn = QPushButton("Export PDF")
        btn.setParent(self)
        btn.setFixedWidth(900)
        btn.clicked.connect(self.export)
        
    def export(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """        
        # try:
        #     home_dir = Path(self.ctx.directory_path).joinpath(f"Submission_Details_{self.base_dict['Plate Number']}.pdf").resolve().__str__()
        # except FileNotFoundError:
        #     home_dir = Path.home().resolve().__str__()
        # fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".pdf")[0])
        # if fname.__str__() == ".":
        #     logger.debug("Saving pdf was cancelled.")
        #     return
        fname = select_save_file(obj=self, default_name=self.base_dict['Plate Number'], extension="pdf")
        del self.base_dict['platemap']
        export_map = make_plate_map(self.plate_dicto)
        image_io = BytesIO()
        try:
            export_map.save(image_io, 'JPEG')
        except AttributeError:
            logger.error(f"No plate map found")
        self.base_dict['export_map'] = base64.b64encode(image_io.getvalue()).decode('utf-8')
        self.html2 = self.template.render(sub=self.base_dict)
        try:
            with open(fname, "w+b") as f:
                pisa.CreatePDF(self.html2, dest=f)
        except PermissionError as e:
            logger.error(f"Error saving pdf: {e}")
            msg = QMessageBox()
            msg.setText("Permission Error")
            msg.setInformativeText(f"Looks like {fname.__str__()} is open.\nPlease close it and try again.")
            msg.setWindowTitle("Permission Error")
            msg.exec()

class BarcodeWindow(QDialog):

    def __init__(self, rsl_num:str):
        super().__init__()
        # set the title
        self.setWindowTitle("Image")
        self.layout = QVBoxLayout()
        # setting  the geometry of window
        self.setGeometry(0, 0, 400, 300)
        # creating label
        self.label = QLabel()
        self.img = make_plate_barcode(rsl_num)
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(self.img)
        # adding image to label
        self.label.setPixmap(self.pixmap)
        # show all the widgets]
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)
        self._createActions()
        self._createToolBar()
        self._connectActions()
        


    def _createToolBar(self):
        """
        adds items to menu bar
        """    
        toolbar = QToolBar("My main toolbar")
        toolbar.addAction(self.printAction)
        

    def _createActions(self):
        """
        creates actions
        """        
        self.printAction = QAction("&Print", self)


    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.printAction.triggered.connect(self.print_barcode)


    def print_barcode(self):
        """
        Sends barcode image to printer.
        """        
        printer = QtPrintSupport.QPrinter()
        dialog = QtPrintSupport.QPrintDialog(printer)
        if dialog.exec():
            self.handle_paint_request(printer, self.pixmap.toImage())


    def handle_paint_request(self, printer:QtPrintSupport.QPrinter, im):
        logger.debug(f"Hello from print handler.")
        painter = QPainter(printer)
        image = QPixmap.fromImage(im)
        painter.drawPixmap(120, -20, image)
        painter.end()
        
class SubmissionComment(QDialog):
    """
    a window for adding comment text to a submission
    """    
    def __init__(self, ctx:Settings, rsl:str) -> None:

        super().__init__()
        self.ctx = ctx
        self.rsl = rsl
        self.setWindowTitle(f"{self.rsl} Submission Comment")
        # create text field
        self.txt_editor = QTextEdit(self)
        self.txt_editor.setReadOnly(False)
        self.txt_editor.setText("Add Comment")
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        self.setFixedSize(400, 300)
        self.layout.addWidget(self.txt_editor)
        self.layout.addWidget(self.buttonBox, alignment=Qt.AlignmentFlag.AlignBottom)
        self.setLayout(self.layout)
        
    def add_comment(self):
        """
        Adds comment to submission object.
        """        
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = {"name":commenter, "time": dt, "text": comment}
        logger.debug(f"Full comment: {full_comment}")
        # sub = lookup_submission_by_rsl_num(ctx = self.ctx, rsl_num=self.rsl)
        # sub = lookup_submissions(ctx = self.ctx, rsl_number=self.rsl)
        sub = BasicSubmission.query(rsl_number=self.rsl)
        try:
            sub.comment.append(full_comment)
        except AttributeError:
            sub.comment = [full_comment]
        logger.debug(sub.__dict__)
        self.ctx.database_session.add(sub)
        self.ctx.database_session.commit()

        