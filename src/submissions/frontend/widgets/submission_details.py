"""
Webview to show submission and sample details.
"""
from PyQt6.QtGui import QColor, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot, QMarginsF
from jinja2 import TemplateNotFound

from backend.db.models import BasicSubmission, BasicSample, Reagent, KitType
from tools import is_power_user, html_to_pdf, jinja_template_loading
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

    def __init__(self, parent, sub: BasicSubmission | BasicSample | Reagent) -> None:

        super().__init__(parent)
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent()
        except AttributeError:
            self.app = None
        self.webview = QWebEngineView(parent=self)
        self.webview.setMinimumSize(900, 500)
        self.webview.setMaximumSize(900, 700)
        self.webview.loadFinished.connect(self.activate_export)
        self.layout = QGridLayout()
        # self.setFixedSize(900, 500)
        # NOTE: button to export a pdf version
        self.btn = QPushButton("Export PDF")
        self.btn.setFixedWidth(775)
        self.btn.clicked.connect(self.export)
        self.back = QPushButton("Back")
        self.back.setFixedWidth(100)
        self.back.clicked.connect(self.back_function)
        self.layout.addWidget(self.back, 0, 0, 1, 1)
        self.layout.addWidget(self.btn, 0, 1, 1, 9)
        self.layout.addWidget(self.webview, 1, 0, 10, 10)
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
            case Reagent():
                self.reagent_details(reagent=sub)
        self.webview.page().setWebChannel(self.channel)

    def back_function(self):
        self.webview.back()

    # @pyqtSlot(bool)
    def activate_export(self):
        title = self.webview.title()
        self.setWindowTitle(title)
        if "Submission" in title:
            self.btn.setEnabled(True)
            self.export_plate = title.split(" ")[-1]
            logger.debug(f"Updating export plate to: {self.export_plate}")
        else:
            self.btn.setEnabled(False)
        if title == self.webview.history().items()[0].title():
            logger.debug("Disabling back button")
            self.back.setEnabled(False)
        else:
            self.back.setEnabled(True)

    @pyqtSlot(str)
    def sample_details(self, sample: str | BasicSample):
        """
        Changes details view to summary of Sample

        Args:
            sample (str): Submitter Id of the sample.
        """
        logger.debug(f"Details: {sample}")
        if isinstance(sample, str):
            sample = BasicSample.query(submitter_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        exclude = ['submissions', 'excluded', 'colour', 'tooltip']
        # try:
        #     base_dict['excluded'] += exclude
        # except KeyError:
        base_dict['excluded'] = exclude
        template = sample.get_details_template()
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(sample=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.submitter_id}")

    @pyqtSlot(str, str)
    def reagent_details(self, reagent: str | Reagent, kit: str | KitType):
        if isinstance(reagent, str):
            reagent = Reagent.query(lot_number=reagent)
        if isinstance(kit, str):
            kit = KitType.query(name=kit)
        base_dict = reagent.to_sub_dict(extraction_kit=kit, full_data=True)
        env = jinja_template_loading()
        temp_name = "reagent_details.html"
        # logger.debug(f"Returning template: {temp_name}")
        try:
            template = env.get_template(temp_name)
        except TemplateNotFound as e:
            logger.error(f"Couldn't find template due to {e}")
            return
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(reagent=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Reagent Details - {reagent.name} - {reagent.lot}")
        # self.btn.setEnabled(False)

    @pyqtSlot(str)
    def submission_details(self, submission: str | BasicSubmission):
        """
        Sets details view to summary of Submission.

        Args:
            submission (str | BasicSubmission): Submission of interest.
        """
        # logger.debug(f"Details for: {submission}")
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_plate_num=submission)
        self.rsl_plate_num = submission.rsl_plate_num
        self.base_dict = submission.to_dict(full_data=True)
        # logger.debug(f"Submission details data:\n{pformat({k:v for k,v in self.base_dict.items() if k == 'reagents'})}")
        # NOTE: don't want id
        self.base_dict = submission.finalize_details(self.base_dict)
        # logger.debug(f"Creating barcode.")
        # logger.debug(f"Making platemap...")
        self.base_dict['platemap'] = submission.make_plate_map(sample_list=submission.hitpick_plate())
        self.base_dict['excluded'] = submission.get_default_info("details_ignore")
        self.base_dict, self.template = submission.get_details_template(base_dict=self.base_dict)
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        # logger.debug(f"Submission_details: {pformat(self.base_dict)}")
        # logger.debug(f"User is power user: {is_power_user()}")
        self.html = self.template.render(sub=self.base_dict, signing_permission=is_power_user(), css=css)
        # with open("test.html", "w") as f:
        #     f.write(self.html)
        self.webview.setHtml(self.html)

    @pyqtSlot(str)
    def sign_off(self, submission: str | BasicSubmission):
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
        fname = select_save_file(obj=self, default_name=self.export_plate, extension="pdf")
        page_layout = QPageLayout()
        page_layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        page_layout.setOrientation(QPageLayout.Orientation.Portrait)
        page_layout.setMargins(QMarginsF(25, 25, 25, 25))
        self.webview.page().printToPdf(fname.with_suffix(".pdf").__str__(), page_layout)

class SubmissionComment(QDialog):
    """
    a window for adding comment text to a submission
    """

    def __init__(self, parent, submission: BasicSubmission) -> None:

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

    def parse_form(self) -> List[dict]:
        """
        Adds comment to submission object.
        """
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        if comment in ["", None]:
            return None
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = {"name": commenter, "time": dt, "text": comment}
        # logger.debug(f"Full comment: {full_comment}")
        return full_comment
