'''
Contains widgets specific to the submission summary and submission details.
'''
from PyQt6.QtWidgets import (
    QVBoxLayout, QDialog, QTableView,
    QTextEdit, QPushButton, QScrollArea, 
    QMessageBox, QFileDialog, QMenu
)
from PyQt6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
from PyQt6.QtGui import QFontMetrics, QAction, QCursor
from backend.db import submissions_to_df, lookup_submission_by_id, delete_submission_by_id
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa
import sys
from pathlib import Path
import logging
from .pop_ups import QuestionAsker

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
        self.setSortingEnabled(True)
        self.doubleClicked.connect(self.show_details)
 
    def setData(self) -> None: 
        """
        sets data in model
        """        
        self.data = submissions_to_df(ctx=self.ctx)
        self.data['id'] = self.data['id'].apply(str)
        self.data['id'] = self.data['id'].str.zfill(3)
        try:
            del self.data['samples']
        except KeyError:
            pass
        try:
            del self.data['reagents']
        except KeyError:
            pass
        proxyModel = QSortFilterProxyModel()
        proxyModel.setSourceModel(pandasModel(self.data))
        # self.model = pandasModel(self.data)
        # self.setModel(self.model)
        self.setModel(proxyModel)
        # self.resize(800,600)

    def show_details(self) -> None:
        """
        creates detailed data to show in seperate window
        """        
        index = (self.selectionModel().currentIndex())
        value = index.sibling(index.row(),0).data()
        dlg = SubmissionDetails(ctx=self.ctx, id=value)
        if dlg.exec():
            pass


    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """        
        self.menu = QMenu(self)
        renameAction = QAction('Delete', self)
        detailsAction = QAction('Details', self)
        renameAction.triggered.connect(lambda: self.delete_item(event))
        detailsAction.triggered.connect(lambda: self.show_details())
        self.menu.addAction(detailsAction)
        self.menu.addAction(renameAction)
        # add other required actions
        self.menu.popup(QCursor.pos())


    def delete_item(self, event):
        """
        Confirms user deletion and sends id to backend for deletion.

        Args:
            event (_type_): _description_
        """        
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
        # don't want id
        del self.base_dict['id']
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
        # button to export a pdf version
        btn = QPushButton("Export PDF")
        btn.setParent(self)
        btn.setFixedWidth(w)
        btn.clicked.connect(self.export)
        

    def export(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """        
        template = env.get_template("submission_details.html")
        html = template.render(sub=self.base_dict)
        home_dir = Path(self.ctx["directory_path"]).joinpath(f"Submission_Details_{self.base_dict['Plate Number']}.pdf").resolve().__str__()
        fname = Path(QFileDialog.getSaveFileName(self, "Save File", home_dir, filter=".pdf")[0])
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
