from PyQt6.QtWidgets import (QDialog, QScrollArea, QPushButton, QVBoxLayout, QMessageBox,
                             QLabel, QDialogButtonBox, QToolBar, QTextEdit)
from PyQt6.QtGui import QAction, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt
from PyQt6 import QtPrintSupport
from backend.db.models import BasicSubmission
from ..visualizations import make_plate_barcode, make_plate_map, make_plate_map_html
from tools import check_if_app, jinja_template_loading
from .functions import select_save_file
from io import BytesIO
from xhtml2pdf import pisa
import logging, base64
from getpass import getuser
from datetime import datetime
from pprint import pformat


logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

class SubmissionDetails(QDialog):
    """
    a window showing text details of submission
    """    
    def __init__(self, parent, sub:BasicSubmission) -> None:

        super().__init__(parent)
        # self.ctx = ctx
        try:
            self.app = parent.parent().parent().parent().parent().parent().parent()
        except AttributeError:
            self.app = None
        self.setWindowTitle("Submission Details")
        # create scrollable interior
        interior = QScrollArea()
        interior.setParent(self)
        # sub = BasicSubmission.query(id=id)
        self.base_dict = sub.to_dict(full_data=True)
        logger.debug(f"Submission details data:\n{pformat({k:v for k,v in self.base_dict.items() if k != 'samples'})}")
        # don't want id
        del self.base_dict['id']
        logger.debug(f"Creating barcode.")
        if not check_if_app():
            self.base_dict['barcode'] = base64.b64encode(make_plate_barcode(self.base_dict['Plate Number'], width=120, height=30)).decode('utf-8')
        logger.debug(f"Hitpicking plate...")
        self.plate_dicto = sub.hitpick_plate()
        logger.debug(f"Making platemap...")
        self.base_dict['platemap'] = make_plate_map_html(self.plate_dicto)
        self.template = env.get_template("submission_details.html")
        self.html = self.template.render(sub=self.base_dict)
        webview = QWebEngineView()
        webview.setMinimumSize(900, 500)
        webview.setMaximumSize(900, 500)
        webview.setHtml(self.html)
        self.layout = QVBoxLayout()
        interior.resize(900, 500)
        interior.setWidget(webview)
        self.setFixedSize(900, 500)
        # button to export a pdf version
        btn = QPushButton("Export PDF")
        btn.setParent(self)
        btn.setFixedWidth(900)
        btn.clicked.connect(self.export)
        
    def export(self):
        """
        Renders submission to html, then creates and saves .pdf file to user selected file.
        """        
        fname = select_save_file(obj=self, default_name=self.base_dict['Plate Number'], extension="pdf")
        del self.base_dict['platemap']
        export_map = make_plate_map(self.plate_dicto)
        image_io = BytesIO()
        try:
            export_map.save(image_io, 'JPEG')
        except AttributeError:
            logger.error(f"No plate map found")
        self.base_dict['export_map'] = base64.b64encode(image_io.getvalue()).decode('utf-8')
        self.html2 = self.template.render(sub=self.base_dict)
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

class BarcodeWindow(QDialog):

    def __init__(self, rsl_num:str):
        super().__init__()
        # set the title
        self.setWindowTitle("Image")
        self.layout = QVBoxLayout()
        # setting  the geometry of window
        self.setGeometry(0, 0, 400, 300)
        # creating label
        self.label = QLabel()
        self.img = make_plate_barcode(rsl_num)
        self.pixmap = QPixmap()
        self.pixmap.loadFromData(self.img)
        # adding image to label
        self.label.setPixmap(self.pixmap)
        # show all the widgets]
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)
        self._createActions()
        self._createToolBar()
        self._connectActions()
        
    def _createToolBar(self):
        """
        adds items to menu bar
        """    
        toolbar = QToolBar("My main toolbar")
        toolbar.addAction(self.printAction)
        

    def _createActions(self):
        """
        creates actions
        """        
        self.printAction = QAction("&Print", self)


    def _connectActions(self):
        """
        connect menu and tool bar item to functions
        """
        self.printAction.triggered.connect(self.print_barcode)


    def print_barcode(self):
        """
        Sends barcode image to printer.
        """        
        printer = QtPrintSupport.QPrinter()
        dialog = QtPrintSupport.QPrintDialog(printer)
        if dialog.exec():
            self.handle_paint_request(printer, self.pixmap.toImage())


    def handle_paint_request(self, printer:QtPrintSupport.QPrinter, im):
        logger.debug(f"Hello from print handler.")
        painter = QPainter(printer)
        image = QPixmap.fromImage(im)
        painter.drawPixmap(120, -20, image)
        painter.end()
        
class SubmissionComment(QDialog):
    """
    a window for adding comment text to a submission
    """    
    def __init__(self, parent, submission:BasicSubmission) -> None:

        super().__init__(parent)
        # self.ctx = ctx
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
        
    def parse_form(self):
        """
        Adds comment to submission object.
        """        
        commenter = getuser()
        comment = self.txt_editor.toPlainText()
        dt = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
        full_comment = [{"name":commenter, "time": dt, "text": comment}]
        logger.debug(f"Full comment: {full_comment}")
        return full_comment
        