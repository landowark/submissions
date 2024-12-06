"""
Webview to show submission and sample details.
"""
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot
from jinja2 import TemplateNotFound
from backend.db.models import BasicSubmission, BasicSample, Reagent, KitType
from tools import is_power_user, jinja_template_loading, timezone
from .functions import select_save_file
from .misc import save_pdf
from pathlib import Path
import logging
from getpass import getuser
from datetime import datetime
from pprint import pformat
from typing import List


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
        self.webview.setMaximumWidth(900)
        self.webview.loadFinished.connect(self.activate_export)
        self.layout = QGridLayout()
        # NOTE: button to export a pdf version
        self.btn = QPushButton("Export PDF")
        self.btn.setFixedWidth(775)
        self.btn.clicked.connect(self.save_pdf)
        self.back = QPushButton("Back")
        self.back.setFixedWidth(100)
        # self.back.clicked.connect(self.back_function)
        self.back.clicked.connect(self.webview.back)
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

    # def back_function(self):
    #     self.webview.back()

    def activate_export(self):
        title = self.webview.title()
        self.setWindowTitle(title)
        if "Submission" in title:
            self.btn.setEnabled(True)
            self.export_plate = title.split(" ")[-1]
            # logger.debug(f"Updating export plate to: {self.export_plate}")
        else:
            self.btn.setEnabled(False)
        try:
            check = self.webview.history().items()[0].title()
        except IndexError as e:
            check = title
        if title == check:
            # logger.debug("Disabling back button")
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
        # logger.debug(f"Details: {sample}")
        if isinstance(sample, str):
            sample = BasicSample.query(submitter_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        exclude = ['submissions', 'excluded', 'colour', 'tooltip']
        base_dict['excluded'] = exclude
        template = sample.get_details_template()
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(sample=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.submitter_id}")

    @pyqtSlot(str, str)
    def reagent_details(self, reagent: str | Reagent, kit: str | KitType):
        if isinstance(reagent, str):
            reagent = Reagent.query(lot=reagent)
        if isinstance(kit, str):
            self.kit = KitType.query(name=kit)
        base_dict = reagent.to_sub_dict(extraction_kit=self.kit, full_data=True)
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
        html = template.render(reagent=base_dict, permission=is_power_user(), css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Reagent Details - {reagent.name} - {reagent.lot}")

    @pyqtSlot(str, str, str)
    def update_reagent(self, old_lot: str, new_lot: str, expiry: str):
        expiry = datetime.strptime(expiry, "%Y-%m-%d")
        reagent = Reagent.query(lot=old_lot)
        if reagent:
            reagent.lot = new_lot
            reagent.expiry = expiry
            reagent.save()
            self.reagent_details(reagent=reagent, kit=self.kit)
        else:
            logger.error(f"Reagent with lot {old_lot} not found.")

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
        self.html = self.template.render(sub=self.base_dict, permission=is_power_user(), css=css)
        self.webview.setHtml(self.html)

    @pyqtSlot(str)
    def sign_off(self, submission: str | BasicSubmission):
        logger.debug(f"Signing off on {submission} - ({getuser()})")
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_plate_num=submission)
        submission.signed_by = getuser()
        submission.completed_date = datetime.now()
        submission.completed_date.replace(tzinfo=timezone)
        submission.save()
        self.submission_details(submission=self.rsl_plate_num)

    def save_pdf(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """
        fname = select_save_file(obj=self, default_name=self.export_plate, extension="pdf")
        save_pdf(obj=self.webview, filename=fname)

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
