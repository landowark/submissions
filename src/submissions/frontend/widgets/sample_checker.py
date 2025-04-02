
import logging
from pathlib import Path
from typing import List, Generator

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QDialog, QPushButton, QVBoxLayout,
                             QDialogButtonBox, QTextEdit, QGridLayout)

from backend.validators import PydSubmission
from tools import get_application_from_parent, jinja_template_loading

env = jinja_template_loading()

logger = logging.getLogger(f"submissions.{__name__}")

class SampleChecker(QDialog):

    def __init__(self, parent, title:str, pyd: PydSubmission):
        super().__init__(parent)
        self.pyd = pyd
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
        # self.webview.page().setWebChannel(self.channel)
        template = env.get_template("sample_checker.html")
        template_path = Path(template.environment.loader.__getattribute__("searchpath")[0])
        with open(template_path.joinpath("css", "styles.css"), "r") as f:
            css = f.read()
        html = template.render(samples=self.formatted_list, css=css)
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
        match key:
            case "row" | "column":
                value = [new_value]
            case _:
                value = new_value
        try:
            item = next((sample for sample in self.pyd.samples if int(submission_rank) in sample.submission_rank))
        except StopIteration:
            logger.error(f"Unable to find sample {submission_rank}")
            return
        item.__setattr__(key, value)

    @property
    def formatted_list(self) -> List[dict]:
        output = []
        for sample in self.pyd.sample_list:
            if sample['submitter_id'] in [item['submitter_id'] for item in output]:
                sample['color'] = "red"
            else:
                sample['color'] = "black"
            output.append(sample)
        return output




