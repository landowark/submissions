from PyQt6.QtWidgets import (QDialog, QScrollArea, QPushButton, QVBoxLayout, QMessageBox,
                             QDialogButtonBox, QTextEdit)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, pyqtSlot

from backend.db.models import BasicSubmission, BasicSample
from tools import check_if_app
from .functions import select_save_file
from io import BytesIO
from tempfile import TemporaryFile, TemporaryDirectory
from pathlib import Path
from xhtml2pdf import pisa
import logging, base64
from getpass import getuser
from datetime import datetime
from pprint import pformat
from html2image import Html2Image
from PIL import Image
from typing import List


logger = logging.getLogger(f"submissions.{__name__}")

class SubmissionDetails(QDialog):
    """
    a window showing text details of submission
    """    
    def __init__(self, parent, sub:BasicSubmission) -> None:

        super().__init__(parent)
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent()
        except AttributeError:
            self.app = None
        self.setWindowTitle(f"Submission Details - {sub.rsl_plate_num}")
        # create scrollable interior
        interior = QScrollArea()
        interior.setParent(self)
        self.base_dict = sub.to_dict(full_data=True)
        logger.debug(f"Submission details data:\n{pformat({k:v for k,v in self.base_dict.items() if k != 'samples'})}")
        # don't want id
        del self.base_dict['id']
        logger.debug(f"Creating barcode.")
        if not check_if_app():
            self.base_dict['barcode'] = base64.b64encode(sub.make_plate_barcode(width=120, height=30)).decode('utf-8')
        logger.debug(f"Making platemap...")
        self.base_dict['platemap'] = sub.make_plate_map()
        self.base_dict, self.template = sub.get_details_template(base_dict=self.base_dict)
        self.html = self.template.render(sub=self.base_dict)
        self.webview = QWebEngineView(parent=self)
        self.webview.setMinimumSize(900, 500)
        self.webview.setMaximumSize(900, 500)
        self.webview.setHtml(self.html)
        self.layout = QVBoxLayout()
        interior.resize(900, 500)
        interior.setWidget(self.webview)
        self.setFixedSize(900, 500)
        # button to export a pdf version
        btn = QPushButton("Export PDF")
        btn.setParent(self)
        btn.setFixedWidth(900)
        btn.clicked.connect(self.export)
        # setup channel
        self.channel = QWebChannel()
        self.channel.registerObject('backend', self)
        self.webview.page().setWebChannel(self.channel)

    @pyqtSlot(str)
    def sample_details(self, sample):
        # print(f"{string} is in row {row}, column {column}")
        # self.webview.setHtml(f"<html><body><br><br>{sample}</body></html>")
        sample = BasicSample.query(submitter_id=sample)
        base_dict = sample.to_sub_dict(full_data=True)
        base_dict, template = sample.get_details_template(base_dict=base_dict)
        html = template.render(sample=base_dict)
        self.webview.setHtml(html)
        # sample.show_details(obj=self)

    def export(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """        
        fname = select_save_file(obj=self, default_name=self.base_dict['Plate Number'], extension="pdf")
        image_io = BytesIO()
        temp_dir = Path(TemporaryDirectory().name)
        hti = Html2Image(output_path=temp_dir, size=(1200, 750))
        temp_file = Path(TemporaryFile(dir=temp_dir, suffix=".png").name)
        screenshot = hti.screenshot(self.base_dict['platemap'], save_as=temp_file.name)
        export_map = Image.open(screenshot[0])
        export_map = export_map.convert('RGB')
        try:
            export_map.save(image_io, 'JPEG')
        except AttributeError:
            logger.error(f"No plate map found")
        self.base_dict['export_map'] = base64.b64encode(image_io.getvalue()).decode('utf-8')
        del self.base_dict['platemap']
        self.html2 = self.template.render(sub=self.base_dict)
        with open("test.html", "w") as fw:
            fw.write(self.html2)
        try:
            with open(fname, "w+b") as f:
                pisa.CreatePDF(self.html2, dest=f)
        except PermissionError as e:
            logger.error(f"Error saving pdf: {e}")
            msg = QMessageBox()
            msg.setText("Permission Error")
            msg.setInformativeText(f"Looks like {fname.__str__()} is open.\nPlease close it and try again.")
            msg.setWindowTitle("Permission Error")
            msg.exec()
        
class SubmissionComment(QDialog):
    """
    a window for adding comment text to a submission
    """    
    def __init__(self, parent, submission:BasicSubmission) -> None:

        super().__init__(parent)
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent
            print(f"App: {self.app}")
        except AttributeError:
            pass
        self.submission = submission
        self.setWindowTitle(f"{self.submission.rsl_plate_num} Submission Comment")
        # create text field
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
        full_comment = [{"name":commenter, "time": dt, "text": comment}]
        logger.debug(f"Full comment: {full_comment}")
        return full_comment

