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
from tools import is_power_user, jinja_template_loading, timezone, get_application_from_parent
from .functions import select_save_file, save_pdf
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
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setMinimumSize(900, 500)
        self.webview.setMaximumWidth(900)
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
        match sub:
            case BasicSubmission():
                self.submission_details(submission=sub)
                self.rsl_plate_num = sub.rsl_plate_num
            case BasicSample():
                self.sample_details(sample=sub)
            case Reagent():
                self.reagent_details(reagent=sub)
        # NOTE: Used to maintain javascript functions.
        self.webview.page().setWebChannel(self.channel)

    def activate_export(self) -> None:
        """
        Determines if export pdf should be active.

        Returns:
            None
        """
        title = self.webview.title()
        self.setWindowTitle(title)
        if "Submission" in title:
            self.btn.setEnabled(True)
            self.export_plate = title.split(" ")[-1]
        else:
            self.btn.setEnabled(False)
        try:
            check = self.webview.history().items()[0].title()
        except IndexError as e:
            check = title
        if title == check:
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
        logger.debug(f"Sample details.")
        if isinstance(sample, str):
            sample = BasicSample.query(submitter_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        exclude = ['submissions', 'excluded', 'colour', 'tooltip']
        base_dict['excluded'] = exclude
        template = sample.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(sample=base_dict, css=css)
        with open(f"{sample.submitter_id}.html", 'w') as f:
            f.write(html)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.submitter_id}")

    @pyqtSlot(str, str)
    def reagent_details(self, reagent: str | Reagent, kit: str | KitType):
        """
        Changes details view to summary of Reagent

        Args:
            kit (str | KitType): Name of kit.
            reagent (str | Reagent): Lot number of the reagent
        """
        logger.debug(f"Reagent details.")
        if isinstance(reagent, str):
            reagent = Reagent.query(lot=reagent)
        if isinstance(kit, str):
            self.kit = KitType.query(name=kit)
        base_dict = reagent.to_sub_dict(extraction_kit=self.kit, full_data=True)
        env = jinja_template_loading()
        temp_name = "reagent_details.html"
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
        """
        Designed to allow editing reagent in details view (depreciated)

        Args:
            old_lot ():
            new_lot ():
            expiry ():

        Returns:

        """
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
        logger.debug(f"Submission details.")
        if isinstance(submission, str):
            submission = BasicSubmission.query(rsl_plate_num=submission)
        self.rsl_plate_num = submission.rsl_plate_num
        self.base_dict = submission.to_dict(full_data=True)
        # NOTE: don't want id
        self.base_dict['platemap'] = submission.make_plate_map(sample_list=submission.hitpicked)
        self.base_dict['excluded'] = submission.get_default_info("details_ignore")
        self.base_dict, self.template = submission.get_details_template(base_dict=self.base_dict)
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        # logger.debug(f"Base dictionary of submission {self.rsl_plate_num}: {pformat(self.base_dict)}")
        self.html = self.template.render(sub=self.base_dict, permission=is_power_user(), css=css)
        self.webview.setHtml(self.html)

    @pyqtSlot(str)
    def sign_off(self, submission: str | BasicSubmission) -> None:
        """
        Allows power user to signify a submission is complete.

        Args:
            submission (str | BasicSubmission): Submission to be completed

        Returns:
            None
        """
        logger.info(f"Signing off on {submission} - ({getuser()})")
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
        self.app = get_application_from_parent(parent)
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
        return full_comment
