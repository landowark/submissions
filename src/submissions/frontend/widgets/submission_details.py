"""
Webview to show submission and sample details.
"""
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout, 
                             QDialogButtonBox, QTextEdit)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot

from backend.db.models import BasicSubmission, BasicSample
from tools import is_power_user, html_to_pdf
from .functions import select_save_file
from pathlib import Path
import logging
from getpass import getuser
from datetime import datetime
from pprint import pformat

from typing import List
from backend.excel.writer import DocxWriter

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionDetails(QDialog):
    """
    a window showing text details of submission
    """    
    def __init__(self, parent, sub:BasicSubmission|BasicSample) -> None:

        super().__init__(parent)
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent()
        except AttributeError:
            self.app = None
        self.webview = QWebEngineView(parent=self)
        self.webview.setMinimumSize(900, 500)
        self.webview.setMaximumSize(900, 500)
        self.layout = QVBoxLayout()
        self.setFixedSize(900, 500)
        # NOTE: button to export a pdf version
        btn = QPushButton("Export DOCX")
        btn.setFixedWidth(875)
        btn.clicked.connect(self.export)
        self.layout.addWidget(btn)
        self.layout.addWidget(self.webview)
        self.setLayout(self.layout)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        match sub:
            case BasicSubmission():
                self.submission_details(submission=sub)
                self.rsl_plate_num = sub.rsl_plate_num
            case BasicSample():
                self.sample_details(sample=sub)
        self.webview.page().setWebChannel(self.channel)

    @pyqtSlot(str)
    def sample_details(self, sample:str|BasicSample):
        """
        Changes details view to summary of Sample

        Args:
            sample (str): Submitter Id of the sample.
        """
        if isinstance(sample, str):
            sample = BasicSample.query(submitter_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        base_dict, template = sample.get_details_template(base_dict=base_dict)
        html = template.render(sample=base_dict)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.submitter_id}")
        
    @pyqtSlot(str)
    def submission_details(self, submission:str|BasicSubmission):
        """
        Sets details view to summary of Submission.

        Args:
            submission (str | BasicSubmission): Submission of interest.
        """        
        # logger.debug(f"Details for: {submission}")
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_plate_num=submission)
        self.base_dict = submission.to_dict(full_data=True)
        # logger.debug(f"Submission details data:\n{pformat({k:v for k,v in self.base_dict.items() if k == 'reagents'})}")
        # NOTE: don't want id
        self.base_dict = submission.finalize_details(self.base_dict)
        # logger.debug(f"Creating barcode.")
        # logger.debug(f"Making platemap...")
        self.base_dict['platemap'] = BasicSubmission.make_plate_map(sample_list=submission.hitpick_plate())
        self.base_dict, self.template = submission.get_details_template(base_dict=self.base_dict)
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        # logger.debug(f"Submission_details: {pformat(self.base_dict)}")
        self.html = self.template.render(sub=self.base_dict, signing_permission=is_power_user(), css=css)
        self.webview.setHtml(self.html)
        self.setWindowTitle(f"Submission Details - {submission.rsl_plate_num}")

    @pyqtSlot(str)
    def sign_off(self, submission:str|BasicSubmission):
        # logger.debug(f"Signing off on {submission} - ({getuser()})")
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_plate_num=submission)
        submission.signed_by = getuser()
        submission.save()
        self.submission_details(submission=self.rsl_plate_num)

    def export(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """
        writer = DocxWriter(base_dict=self.base_dict)
        fname = select_save_file(obj=self, default_name=self.base_dict['plate_number'], extension="docx")
        writer.save(fname)
        try:
            html_to_pdf(html=self.html, output_file=fname)
        except PermissionError as e:
            logger.error(f"Error saving pdf: {e}")

class SubmissionComment(QDialog):
    """
    a window for adding comment text to a submission
    """    
    def __init__(self, parent, submission:BasicSubmission) -> None:

        super().__init__(parent)
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent
            # logger.debug(f"App: {self.app}")
        except AttributeError:
            pass
        self.submission = submission
        self.setWindowTitle(f"{self.submission.rsl_plate_num} Submission Comment")
        # NOTE: create text field
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
        
    def parse_form(self) -> List[dict]:
        """
        Adds comment to submission object.
        """        
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = {"name":commenter, "time": dt, "text": comment}
        # logger.debug(f"Full comment: {full_comment}")
        return full_comment
