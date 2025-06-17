import logging
from pathlib import Path
from typing import List
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QGridLayout

from backend.db.models import ClientSubmission
from backend.validators import PydSample, RSLNamer
from tools import get_application_from_parent, jinja_template_loading


env = jinja_template_loading()

logger = logging.getLogger(f"submissions.{__name__}")


class SampleChecker(QDialog):

    def __init__(self, parent, title: str, samples: List[PydSample], clientsubmission: ClientSubmission|None=None):
        super().__init__(parent)
        if clientsubmission:
            self.rsl_plate_number = RSLNamer.construct_new_plate_name(clientsubmission.to_dict())
        else:
            self.rsl_plate_number = clientsubmission
        self.samples = samples
        self.setWindowTitle(title)
        self.app = get_application_from_parent(parent)
        self.webview = QWebEngineView(parent=self)
        self.webview.setMinimumSize(900, 500)
        self.webview.setMaximumWidth(900)
        self.layout = QGridLayout()
        self.layout.addWidget(self.webview, 0, 0, 10, 10)
        # NOTE: setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        # NOTE: Used to maintain javascript functions.
        template = env.get_template("sample_checker.html")
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        try:
            samples = self.formatted_list
        except AttributeError as e:
            logger.error(f"Problem getting sample list: {e}")
            samples = []
        html = template.render(samples=samples, css=css, rsl_plate_number=self.rsl_plate_number)
        self.webview.setHtml(html)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, 11, 9, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(self.layout)
        self.webview.page().setWebChannel(self.channel)

    @pyqtSlot(str, str, str)
    def text_changed(self, submission_rank: str, key: str, new_value: str):
        logger.debug(f"Name: {submission_rank}, Key: {key}, Value: {new_value}")
        try:
            item = next((sample for sample in self.samples if int(submission_rank) == sample.submission_rank))
        except StopIteration:
            logger.error(f"Unable to find sample {submission_rank}")
            return
        item.__setattr__(key, new_value)

    @pyqtSlot(str, bool)
    def enable_sample(self, submission_rank: str, enabled: bool):
        logger.debug(f"Name: {submission_rank}, Enabled: {enabled}")
        try:
            item = next((sample for sample in self.samples if int(submission_rank) == sample.submission_rank))
        except StopIteration:
            logger.error(f"Unable to find sample {submission_rank}")
            return
        item.__setattr__("enabled", enabled)

    @pyqtSlot(str)
    def set_rsl_plate_number(self, rsl_plate_number: str):
        logger.debug(f"RSL plate num: {rsl_plate_number}")
        self.rsl_plate_number = rsl_plate_number

    @property
    def formatted_list(self) -> List[dict]:
        output = []
        for sample in self.samples:
            logger.debug(sample)
            s = sample.improved_dict(dictionaries=False)
            if s['sample_id'] in [item['sample_id'] for item in output]:
                s['color'] = "red"
            else:
                s['color'] = "black"
            output.append(s)
        return output
