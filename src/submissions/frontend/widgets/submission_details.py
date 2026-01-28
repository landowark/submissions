"""
Webview to show procedure and sample details.
"""
from __future__ import annotations

import json, sys, logging
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot
from jinja2 import TemplateNotFound
from backend.db.models import Reagent, ProcedureType, Equipment, Process, Tips
from tools import is_power_user, jinja_template_loading, render_details_template, timezone, get_application_from_parent, list_str_comparator
from .functions import select_save_file, save_pdf
from . import CustomWebEnginePage
from pathlib import Path
from getpass import getuser
from datetime import datetime
from pprint import pformat
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.db.models import Run, Sample, ClientSubmission, Procedure


logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionDetails(QDialog):
    """
    a window showing text details of procedure
    """

    def __init__(self, parent, object_: ClientSubmission | Run | Procedure | Sample | Reagent, **kwargs) -> None:

        super().__init__(parent, **kwargs)
        self.object_ = object_
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        custom_page = CustomWebEnginePage(self.webview)
        self.webview.setPage(custom_page)
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
        self.object_details(object_=self.object_)
        # self.webview.page().setWebChannel(self.channel)

    def object_details(self, object_):
        from backend.db.models import ClientSubmission, Run, Procedure
        # logger.debug(f"Incoming object: {object_}")
        # match object_:
        #     case ClientSubmission():
        #         expand = [{"run":['procedure']}, "sample"]
        #     case Run():
        #         expand = ['procedure', 'sample']
        #     case _:
        #         expand = []
        # details = object_.details_dict_expand_fields(fields=expand)
        # details = object_.clean_details_for_render(details)
        # template = object_.details_template
        # template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        # with open(template_path.joinpath("css", "styles.css"), "r") as f:
        #     css = f.read()
        # key = object_.__class__.__name__.lower()
        # d = {object_.__class__.__name__.lower(): details}
        # html = template.render(**d, css=[css])
        # html = render_details_template(template, **d)
        html = object_.to_html()
        self.webview.setHtml("<h1>TEST</h1><script>console.log('running');</script>")
        self.setWindowTitle(f"{object_.__class__.__name__} Details - {object_.name}")
        
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
        if isinstance(equipment, str):
            equipment = Equipment.query(name=equipment)
        base_dict = equipment.details_dict
        template = equipment.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(equipment=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Equipment Details - {equipment.name}")

    @pyqtSlot(str)
    def process_details(self, process: str | Process):
        if isinstance(process, str):
            process = Process.query(name=process)
        base_dict = process.details_dict
        template = process.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(process=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Process Details - {process.name}")

    @pyqtSlot(str)
    def tips_details(self, tips: str | Tips):
        if isinstance(tips, str):
            tips = Tips.query(lot=tips)
        base_dict = tips.details_dict
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
        from backend.db.models import Sample
        if isinstance(sample, str):
            sample = Sample.query(sample_id=sample)
        base_dict = sample.details_dict
        exclude = ['procedure', 'excluded', 'colour', 'tooltip']
        base_dict['excluded'] = exclude
        template = sample.details_template
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(sample=base_dict, css=css)
        self.webview.setHtml(html)
        self.setWindowTitle(f"Sample Details - {sample.sample_id}")

    @pyqtSlot(str, str)
    def reagent_details(self, reagent: str | Reagent, proceduretype: str | ProcedureType):
        """
        Changes details view to summary of Reagent

        Args:
            kit (str | KitType): Name of kittype.
            reagent (str | Reagent): Lot number of the reagent
        """
        if isinstance(reagent, str):
            reagent = Reagent.query(lot=reagent)
        if isinstance(proceduretype, str):
            self.proceduretype = ProcedureType.query(name=proceduretype)
        # base_dict = reagent.to_sub_dict(proceduretype=self.proceduretype, full_data=True)
        # base_dict = reagent.details_dict(proceduretype=self.proceduretype, full_data=True)
        base_dict = reagent.details_dict
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
        from backend.db.models import Run
        if isinstance(run, str):
            run = Run.query(name=run)
        self.rsl_plate_number = run.rsl_plate_number
        # self.base_dict = run.to_dict(full_data=True)
        self.base_dict = run.details_dict
        # NOTE: don't want id
        self.base_dict['platemap'] = run.make_plate_map(sample_list=run.hitpicked)
        self.base_dict['excluded'] = run.get_default_info("details_ignore")
        # self.template = run.details_template
        # template_path = Path(self.template.environment.loader.__getattribute__("searchpath")[0])
        # with open(template_path.joinpath("css", "styles.css"), "r") as f:
        #     css = f.read()
        # self.html = self.template.render(sub=self.base_dict, permission=is_power_user(), css=css)
        self.html = render_details_template("submission_details", run=self.base_dict)
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
        from backend.db.models import Run
        logger.info(f"Signing off on {run} - ({getuser()})")
        if isinstance(run, str):
            run = Run.query(name=run)
        run.signed_by = getuser()
        run.completed_date = datetime.now()
        run.completed_date.replace(tzinfo=timezone)
        run.save()
        self.object_details(object_=run)

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

    def parse_form(self) -> dict:
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
