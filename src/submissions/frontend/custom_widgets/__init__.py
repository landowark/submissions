from datetime import date
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog, 
    QDialogButtonBox, QDateEdit, QSizePolicy, QWidget,
    QGridLayout, QPushButton, QSpinBox,
    QScrollBar, QHBoxLayout,
    QMessageBox
)
from PyQt6.QtCore import Qt, QDate, QSize
# from PyQt6.QtGui import QFontMetrics, QAction

from backend.db import get_all_reagenttype_names, lookup_all_sample_types, create_kit_from_yaml
from jinja2 import Environment, FileSystemLoader
import sys
from pathlib import Path
import logging

logger = logging.getLogger(f"submissions.{__name__}")

if getattr(sys, 'frozen', False):
    loader_path = Path(sys._MEIPASS).joinpath("files", "templates")
else:
    loader_path = Path(__file__).parents[2].joinpath('templates').absolute().__str__()
loader = FileSystemLoader(loader_path)
env = Environment(loader=loader)


class AddReagentForm(QDialog):
    """
    dialog to add gather info about new reagent
    """    
    def __init__(self, ctx:dict, reagent_lot:str|None, reagent_type:str|None, expiry:date|None=None) -> None:
        super().__init__()

        if reagent_lot == None:
            reagent_lot = ""

        self.setWindowTitle("Add Reagent")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # get lot info
        lot_input = QLineEdit()
        lot_input.setText(reagent_lot)
        # get expiry info
        exp_input = QDateEdit(calendarPopup=True)
        if expiry == None:
            exp_input.setDate(QDate.currentDate())
        else:
            exp_input.setDate(expiry)
        # get reagent type info
        type_input = QComboBox()
        type_input.addItems([item.replace("_", " ").title() for item in get_all_reagenttype_names(ctx=ctx)])
        logger.debug(f"Trying to find index of {reagent_type}")
        # convert input to user friendly string?
        try:
            reagent_type = reagent_type.replace("_", " ").title()
        except AttributeError:
            reagent_type = None
        # set parsed reagent type to top of list
        index = type_input.findText(reagent_type, Qt.MatchFlag.MatchEndsWith)
        if index >= 0:
            type_input.setCurrentIndex(index)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Lot"))
        self.layout.addWidget(lot_input)
        self.layout.addWidget(QLabel("Expiry"))
        self.layout.addWidget(exp_input)
        self.layout.addWidget(QLabel("Type"))
        self.layout.addWidget(type_input)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class ReportDatePicker(QDialog):
    """
    custom dialog to ask for report start/stop dates
    """    
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Select Report Date Range")
        # make confirm/reject buttons
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # widgets to ask for dates 
        start_date = QDateEdit(calendarPopup=True)
        start_date.setDate(QDate.currentDate())
        end_date = QDateEdit(calendarPopup=True)
        end_date.setDate(QDate.currentDate())
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(end_date)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


class KitAdder(QWidget):
    """
    dialog to get information to add kit
    """    
    def __init__(self, parent_ctx:dict) -> None:
        super().__init__()
        self.ctx = parent_ctx
        self.grid = QGridLayout()
        self.setLayout(self.grid)
        # insert submit button at top
        self.submit_btn = QPushButton("Submit")
        self.grid.addWidget(self.submit_btn,0,0,1,1)
        # need to exclude ordinary users to mitigate garbage database entries
        # self.grid.addWidget(QLabel("Password:"),1,0)
        # self.grid.addWidget(QLineEdit(),1,1)
        self.grid.addWidget(QLabel("Kit Name:"),2,0)
        self.grid.addWidget(QLineEdit(),2,1)
        self.grid.addWidget(QLabel("Used For Sample Type:"),3,0)
        used_for = QComboBox()
        # Insert all existing sample types
        used_for.addItems(lookup_all_sample_types(ctx=parent_ctx))
        used_for.setEditable(True)
        self.grid.addWidget(used_for,3,1)
        # set cost per run
        self.grid.addWidget(QLabel("Constant cost per full plate (plates, work hours, etc.):"),4,0)
        cost = QSpinBox()
        cost.setMinimum(0)
        cost.setMaximum(9999)
        self.grid.addWidget(cost,4,1)
        self.grid.addWidget(QLabel("Mutable cost per full plate (tips, reagents, etc.):"),5,0)
        cost = QSpinBox()
        cost.setMinimum(0)
        cost.setMaximum(9999)
        self.grid.addWidget(cost,5,1)
        # button to add additional reagent types
        self.add_RT_btn = QPushButton("Add Reagent Type")
        self.grid.addWidget(self.add_RT_btn)
        self.add_RT_btn.clicked.connect(self.add_RT)
        self.submit_btn.clicked.connect(self.submit)

    def add_RT(self) -> None:
        """
        insert new reagent type row
        """        
        maxrow = self.grid.rowCount()
        self.grid.addWidget(ReagentTypeForm(parent_ctx=self.ctx), maxrow + 1,0,1,2)


    def submit(self) -> None:
        """
        send kit to database
        """        
        # get form info
        labels, values, reagents = self.extract_form_info(self)
        info = {item[0]:item[1] for item in zip(labels, values)}
        logger.debug(info)
        yml_type = {}
        try:
            yml_type['password'] = info['password']
        except KeyError:
            pass
        used = info['used_for_sample_type'].replace(" ", "_").lower()
        yml_type[used] = {}
        yml_type[used]['kits'] = {}
        yml_type[used]['kits'][info['kit_name']] = {}
        yml_type[used]['kits'][info['kit_name']]['constant_cost'] = info["Constant cost per full plate (plates, work hours, etc.)"]
        yml_type[used]['kits'][info['kit_name']]['mutable_cost'] = info["Mutable cost per full plate (tips, reagents, etc.)"]
        yml_type[used]['kits'][info['kit_name']]['reagenttypes'] = reagents
        logger.debug(yml_type)
        # send to kit constructor
        result = create_kit_from_yaml(ctx=self.ctx, exp=yml_type)
        # result = create_kit_from_yaml(ctx=self.ctx, exp=exp)
        msg = QMessageBox()
        # msg.setIcon(QMessageBox.critical)
        match result['code']:
            case 0:
                msg.setText("Kit added")
                msg.setInformativeText(result['message'])
                msg.setWindowTitle("Kit added")
            case 1:
                msg.setText("Permission Error")
                msg.setInformativeText(result['message'])
                msg.setWindowTitle("Permission Error")
        msg.exec()

    def extract_form_info(self, object):
        """
        retrieves arbitrary number of labels, values from form

        Args:
            object (_type_): the object to extract info from

        Returns:
            _type_: _description_
        """
        labels = []
        values = []
        reagents = {}
        for item in object.findChildren(QWidget):
            logger.debug(item.parentWidget())
            # if not isinstance(item.parentWidget(), ReagentTypeForm):
            match item:
                case QLabel():
                    labels.append(item.text().replace(" ", "_").strip(":").lower())
                case QLineEdit():
                    # ad hoc check to prevent double reporting of qdatedit under lineedit for some reason
                    if not isinstance(prev_item, QDateEdit) and not isinstance(prev_item, QComboBox) and not isinstance(prev_item, QSpinBox) and not isinstance(prev_item, QScrollBar):
                        logger.debug(f"Previous: {prev_item}")
                        logger.debug(f"Item: {item}, {item.text()}")
                        values.append(item.text().strip())
                case QComboBox():
                    values.append(item.currentText().strip())
                case QDateEdit():
                    values.append(item.date().toPyDate())
                case QSpinBox():
                    values.append(item.value())
                case ReagentTypeForm():
                    re_labels, re_values, _ = self.extract_form_info(item) 
                    reagent = {item[0]:item[1] for item in zip(re_labels, re_values)}
                    logger.debug(reagent)
                    # reagent = {reagent['name:']:{'eol':reagent['extension_of_life_(months):']}}
                    reagents[reagent["name_(*exactly*_as_it_appears_in_the_excel_submission_form)"].strip()] = {'eol_ext':int(reagent['extension_of_life_(months)'])}
            prev_item = item
        return labels, values, reagents



class ReagentTypeForm(QWidget):
    """
    custom widget to add information about a new reagenttype
    """    
    def __init__(self, parent_ctx:dict) -> None:
        super().__init__()
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel("Name (*Exactly* as it appears in the excel submission form):"),0,0)
        reagent_getter = QComboBox()
        # lookup all reagent type names from db
        reagent_getter.addItems(get_all_reagenttype_names(ctx=parent_ctx))
        reagent_getter.setEditable(True)
        grid.addWidget(reagent_getter,0,1)
        grid.addWidget(QLabel("Extension of Life (months):"),0,2)
        # get extension of life
        eol = QSpinBox()
        eol.setMinimum(0)
        grid.addWidget(eol, 0,3)


class ControlsDatePicker(QWidget):
    """
    custom widget to pick start and end dates for controls graphs
    """    
    def __init__(self) -> None:
        super().__init__()

        self.start_date = QDateEdit(calendarPopup=True)
        # start date is three month prior to end date by default
        # edit: 2 month, but the variable name is the same cause I'm lazy
        threemonthsago = QDate.currentDate().addDays(-60)
        self.start_date.setDate(threemonthsago)
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setDate(QDate.currentDate())
        self.layout = QHBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(self.start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(self.end_date)
        
        self.setLayout(self.layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(80,20)  
