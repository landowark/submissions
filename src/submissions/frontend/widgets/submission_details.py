"""
Webview to show procedure and sample details.
"""
from __future__ import annotations

import sys, logging
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot
from backend.db import models
from tools import timezone, get_application_from_parent, list_str_comparator
from .functions import select_save_file, save_pdf
from . import CustomWebEnginePage
from getpass import getuser
from datetime import datetime
from pprint import pformat


logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionDetails(QDialog):
    """
    a window showing text details of procedure
    """

    def __init__(self, parent, object_: 
                 models.ClientSubmission | 
                 models.Run | 
                 models.Procedure |
                 models. Sample |
                 models.Reagent, **kwargs) -> None:

        super().__init__(parent, **kwargs)
        
        self.object_ = object_
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
        self.webview.setMinimumSize(900, 500)
        # self.webview.setMaximumWidth(900)
        # NOTE: Decide if exporting should be allowed.
        self.webview.loadFinished.connect(self.activate_export)
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.btn = QPushButton("Export PDF")
        self.btn.setFixedWidth(775)
        self.btn.clicked.connect(self.save_pdf)
        self.back = QPushButton("Back")
        self.back.setFixedWidth(100)
        self.back.clicked.connect(self.webview.back)
        self.layout.addWidget(self.back, 0, 0, 1, 1)
        self.layout.addWidget(self.btn, 0, 1, 1, 9)
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
        self.setLayout(self.layout)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.page().setWebChannel(self.channel)
        # NOTE: Used to maintain javascript functions.
        
        self.object_details(object_=self.object_)

    def object_details(self, object_):
        logger.debug(f"Object type: {object_.__class__.__name__}")
        html = object_.to_html()
        self.webview.setHtml(html)
        self.setWindowTitle(f"{object_.__class__.__name__} Details - {object_.name}")
        
    def activate_export(self) -> None:
        """
        Determines if export pdf should be active.

        Returns:
            None
        """
        title = self.webview.title()
        self.setWindowTitle(title)
        if list_str_comparator(title, ['ClientSubmission', "Run", "Procedure", "Sample"], mode="starts_with"):
            self.btn.setEnabled(True)
        else:
            self.btn.setEnabled(False)
        self.export_plate = title
        try:
            check = self.webview.history().items()[0].title()
        except IndexError as e:
            check = title
        if title == check:
            self.back.setEnabled(False)
        else:
            self.back.setEnabled(True)

    @pyqtSlot(str)
    def sign_off(self, run: str | models.Run) -> None:
        """
        Allows power user to signify a procedure is complete.

        Args:
            run (str | BasicRun): Submission to be completed

        Returns:
            None
        """
        logger.info(f"Signing off on {run} - ({getuser()})")
        if isinstance(run, str):
            run = models.Run.query(name=run)
        run.signed_by = getuser()
        run.completed_date = datetime.now()
        run.completed_date.replace(tzinfo=timezone)
        run.save()
        self.object_details(object_=run.to_pydantic())

    @pyqtSlot(str, str)
    def show_sub_details(self, sub_name: str, sub_type: str) -> None:
        """
        Shows details of object in details view when called from javascript.

        Args:
            sub_type (str): Type name of object to show 
            sub_name (str): Name to query for object to show
        """
        
        clss = models.BaseClass.find_subclasses(class_name=sub_type)
        if clss:
            if isinstance(clss, list):
                clss = clss[0]
            obj = clss.query(name=sub_name, limit=1)
            if obj:
                if isinstance(obj, list):
                    obj = obj[0]
                pyd = obj.to_pydantic()
                self.object_details(object_=pyd)
            else:
                logger.error(f"{sub_type} with name {sub_name} not found.")

    def save_pdf(self):
        """
        Renders procedure to html, then creates and saves .pdf file to user selected file.
        """
        fname = select_save_file(obj=self, default_name=self.export_plate, extension="pdf")
        save_pdf(obj=self.webview, filename=fname)


class SubmissionComment(QDialog):
    """
    a window for adding comment text to a procedure
    """

    def __init__(self, parent, submission) -> None:
        super().__init__(parent)
        self.app = get_application_from_parent(parent)
        self.submission = submission
        self.setWindowTitle(f"{self.submission.name} Submission Comment")
        # NOTE: create text field
        self.txt_editor = QTextEdit(self)
        self.txt_editor.setReadOnly(False)
        self.txt_editor.setPlaceholderText("Write your comment here.")
        self.txt_editor.setStyleSheet("background-color: rgb(255, 255, 255);")
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout = QVBoxLayout()
        self.setFixedSize(400, 300)
        self.layout.addWidget(self.txt_editor)
        self.layout.addWidget(self.buttonBox, alignment=Qt.AlignmentFlag.AlignBottom)
        self.setLayout(self.layout)

    def parse_form(self) -> dict:
        """
        Adds comment to procedure object.
        """
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        if comment in ["", None]:
            return None
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = {"user": commenter, "time": dt, "text": comment}
        return full_comment

__all__ = ["SubmissionDetails", "SubmissionComment"]