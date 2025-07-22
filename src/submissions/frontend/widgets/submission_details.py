"""
Webview to show procedure and sample details.
"""
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot
from jinja2 import TemplateNotFound
from backend.db.models import Run, Sample, Reagent, KitType, Equipment, Process, Tips
from tools import is_power_user, jinja_template_loading, timezone, get_application_from_parent, list_str_comparator
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
    a window showing text details of procedure
    """

    def __init__(self, parent, sub: Run | Sample | Reagent) -> None:

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
        # NOTE: Used to maintain javascript functions.
        self.object_details(object=sub)
        self.webview.page().setWebChannel(self.channel)

    def object_details(self, object):
        details = object.clean_details_dict(object.details_dict())
        template = object.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        key = object.__class__.__name__.lower()
        d = {key: details}
        logger.debug(f"Using details: {pformat(d)}")
        html = template.render(**d, css=[css])
        self.webview.setHtml(html)
        self.setWindowTitle(f"{object.__class__.__name__} Details - {object.name}")
        with open(f"{object.__class__.__name__}_details_rendered.html", "w") as f:
            # f.write(html)
            pass


    def activate_export(self) -> None:
        """
        Determines if export pdf should be active.

        Returns:
            None
        """
        title = self.webview.title()
        self.setWindowTitle(title)
        if list_str_comparator(title, ['ClientSubmission', "Run", "Procedure"], mode="starts_with"):
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
    def equipment_details(self, equipment: str | Equipment):
        logger.debug(f"Equipment details")
        if isinstance(equipment, str):
            equipment = Equipment.query(name=equipment)
        base_dict = equipment.to_sub_dict(full_data=True)
        template = equipment.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(equipment=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Equipment Details - {equipment.name}")

    @pyqtSlot(str)
    def process_details(self, process: str | Process):
        logger.debug(f"Equipment details")
        if isinstance(process, str):
            process = Process.query(name=process)
        base_dict = process.to_sub_dict(full_data=True)
        template = process.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(process=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Process Details - {process.name}")

    @pyqtSlot(str)
    def tips_details(self, tips: str | Tips):
        logger.debug(f"Equipment details: {tips}")
        if isinstance(tips, str):
            tips = Tips.query(lot=tips)
        base_dict = tips.to_sub_dict(full_data=True)
        template = tips.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(tips=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Process Details - {tips.name}")

    @pyqtSlot(str)
    def sample_details(self, sample: str | Sample):
        """
        Changes details view to summary of Sample

        Args:
            sample (str): Submitter Id of the sample.
        """
        logger.debug(f"Sample details.")
        if isinstance(sample, str):
            sample = Sample.query(sample_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        exclude = ['procedure', 'excluded', 'colour', 'tooltip']
        base_dict['excluded'] = exclude
        template = sample.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(sample=base_dict, css=css)
        # with open(f"{sample.sample_id}.html", 'w') as f:
        #     f.write(html)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.sample_id}")

    @pyqtSlot(str, str)
    def reagent_details(self, reagent: str | Reagent, kit: str | KitType):
        """
        Changes details view to summary of Reagent

        Args:
            kit (str | KitType): Name of kittype.
            reagent (str | Reagent): Lot number of the reagent
        """
        logger.debug(f"Reagent details.")
        if isinstance(reagent, str):
            reagent = Reagent.query(lot=reagent)
        if isinstance(kit, str):
            self.kit = KitType.query(name=kit)
        base_dict = reagent.to_sub_dict(kittype=self.kit, full_data=True)
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
    def run_details(self, run: str | Run):
        """
        Sets details view to summary of Submission.

        Args:
            run (str | BasicRun): Submission of interest.
        """
        logger.debug(f"Run details.")
        if isinstance(run, str):
            run = Run.query(name=run)
        self.rsl_plate_number = run.rsl_plate_number
        self.base_dict = run.to_dict(full_data=True)
        # NOTE: don't want id
        self.base_dict['platemap'] = run.make_plate_map(sample_list=run.hitpicked)
        self.base_dict['excluded'] = run.get_default_info("details_ignore")
        self.template = run.details_template
        template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        # logger.debug(f"Base dictionary of procedure {self.name}: {pformat(self.base_dict)}")
        self.html = self.template.render(sub=self.base_dict, permission=is_power_user(), css=css)
        self.webview.setHtml(self.html)


    @pyqtSlot(str)
    def sign_off(self, run: str | Run) -> None:
        """
        Allows power user to signify a procedure is complete.

        Args:
            run (str | BasicRun): Submission to be completed

        Returns:
            None
        """
        logger.info(f"Signing off on {run} - ({getuser()})")
        if isinstance(run, str):
            run = Run.query(name=run)
        run.signed_by = getuser()
        run.completed_date = datetime.now()
        run.completed_date.replace(tzinfo=timezone)
        run.save()
        self.run_details(run=self.rsl_plate_number)

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

    def __init__(self, parent, submission: Run) -> None:
        logger.debug(parent)
        super().__init__(parent)
        self.app = get_application_from_parent(parent)
        self.submission = submission
        self.setWindowTitle(f"{self.submission.rsl_plate_number} Submission Comment")
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
        Adds comment to procedure object.
        """
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        if comment in ["", None]:
            return None
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = {"name": commenter, "time": dt, "text": comment}
        return full_comment
