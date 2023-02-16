from datetime import date
from PyQt6.QtWidgets import (
    QVBoxLayout, QDialog, QTableView,
    QTextEdit, QPushButton, QScrollArea, 
    QMessageBox, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QAbstractTableModel
from PyQt6.QtGui import QFontMetrics, QAction, QCursor

from backend.db import submissions_to_df, lookup_submission_by_id, delete_submission_by_id
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
import sys
from pathlib import Path
import logging
from .pop_ups import AlertPop, QuestionAsker
from tools import check_is_power_user

logger = logging.getLogger(f"submissions.{__name__}")

if getattr(sys, 'frozen', False):
    loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
else:
    loader_path = Path(__file__).parents[2].joinpath('templates').absolute().__str__()
loader = FileSystemLoader(loader_path)
env = Environment(loader=loader)

class pandasModel(QAbstractTableModel):
    """
    pandas model for inserting summary sheet into gui
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

    def columnCount(self, parnet=None) -> int:
        """
        does what it says

        Args:
            parnet (_type_, optional): _description_. Defaults to None.

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
    def __init__(self, ctx:dict) -> None:
        """
        initialize

        Args:
            ctx (dict): settings passed from gui
        """        
        super().__init__()
        self.ctx = ctx
        self.setData()
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        # self.clicked.connect(self.test)
        self.doubleClicked.connect(self.show_details)
 
    def setData(self) -> None: 
        """
        sets data in model
        """        
        self.data = submissions_to_df(ctx=self.ctx)
        try:
            del self.data['samples']
        except KeyError:
            pass
        try:
            del self.data['reagents']
        except KeyError:
            pass
        self.model = pandasModel(self.data)
        self.setModel(self.model)
        # self.resize(800,600)

    def show_details(self) -> None:
        """
        creates detailed data to show in seperate window
        """        
        index = (self.selectionModel().currentIndex())
        # logger.debug(index)
        value = index.sibling(index.row(),0).data()
        dlg = SubmissionDetails(ctx=self.ctx, id=value)
        # dlg.show()
        if dlg.exec():
            pass


    def contextMenuEvent(self, event):
        self.menu = QMenu(self)
        renameAction = QAction('Delete', self)
        detailsAction = QAction('Details', self)
        # Originally I intended to limit deletions to power users.
        # renameAction.setEnabled(False)
        # if check_is_power_user(ctx=self.ctx):
        #     renameAction.setEnabled(True)
        renameAction.triggered.connect(lambda: self.delete_item(event))
        detailsAction.triggered.connect(lambda: self.show_details())
        self.menu.addAction(detailsAction)
        self.menu.addAction(renameAction)
        # add other required actions
        self.menu.popup(QCursor.pos())


    def delete_item(self, event):
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),0).data()
        logger.debug(index)
        msg = QuestionAsker(title="Delete?", message=f"Are you sure you want to delete {index.sibling(index.row(),1).data()}?\n")
        if msg.exec():
            delete_submission_by_id(ctx=self.ctx, id=value)
        else:
            return
        self.setData()



    
class SubmissionDetails(QDialog):
    """
    a window showing text details of submission
    """    
    def __init__(self, ctx:dict, id:int) -> None:

        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("Submission Details")
        
        # create scrollable interior
        interior = QScrollArea()
        interior.setParent(self)
        # get submision from db
        data = lookup_submission_by_id(ctx=ctx, id=id)
        self.base_dict = data.to_dict()
        logger.debug(f"Base dict: {self.base_dict}")
        # don't want id
        del self.base_dict['id']
        # convert sub objects to dicts
        # self.base_dict['reagents'] = [item.to_sub_dict() for item in data.reagents]
        # self.base_dict['samples'] = [item.to_sub_dict() for item in data.samples]
        # retrieve jinja template
        template = env.get_template("submission_details.txt")
        # render using object dict
        text = template.render(sub=self.base_dict)
        # create text field
        txt_editor = QTextEdit(self)
        txt_editor.setReadOnly(True)
        txt_editor.document().setPlainText(text)
        # resize
        font = txt_editor.document().defaultFont()
        fontMetrics = QFontMetrics(font)
        textSize = fontMetrics.size(0, txt_editor.toPlainText())
        w = textSize.width() + 10
        h = textSize.height() + 10
        txt_editor.setMinimumSize(w, h)
        txt_editor.setMaximumSize(w, h)
        txt_editor.resize(w, h)
        interior.resize(w,900)
        txt_editor.setText(text)
        interior.setWidget(txt_editor)
        self.layout = QVBoxLayout()
        self.setFixedSize(w, 900)
        btn = QPushButton("Export PDF")
        btn.setParent(self)
        btn.setFixedWidth(w)
        btn.clicked.connect(self.export)
        

    # def _create_actions(self):
    #     self.exportAction = QAction("Export", self)
        

    def export(self):
        template = env.get_template("submission_details.html")
        html = template.render(sub=self.base_dict)
        # logger.debug(f"Submission details: {self.base_dict}")
        home_dir = Path(self.ctx["directory_path"]).joinpath(f"Submission_Details_{self.base_dict['Plate Number']}.pdf").resolve().__str__()
        fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".pdf")[0])
        # logger.debug(f"report output name: {fname}")
        # df.to_excel(fname, engine='openpyxl')
        if fname.__str__() == ".":
            logger.debug("Saving pdf was cancelled.")
            return
        try:
            with open(fname, "w+b") as f:
                pisa.CreatePDF(html, dest=f)
        except PermissionError as e:
            logger.error(f"Error saving pdf: {e}")
            msg = QMessageBox()
            msg.setText("Permission Error")
            msg.setInformativeText(f"Looks like {fname.__str__()} is open.\nPlease close it and try again.")
            msg.setWindowTitle("Permission Error")
            msg.exec()
        
