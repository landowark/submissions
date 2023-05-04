'''
Contains miscellaneous widgets for frontend functions
'''
from datetime import date
import typing
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog, 
    QDialogButtonBox, QDateEdit, QSizePolicy, QWidget,
    QGridLayout, QPushButton, QSpinBox, QDoubleSpinBox,
    QHBoxLayout,
)
from PyQt6.QtCore import Qt, QDate, QSize
# from submissions.backend.db.functions import lookup_kittype_by_use
# from submissions.backend.db import lookup_regent_by_type_name_and_kit_name
from tools import check_not_nan
from ..all_window_functions import extract_form_info
from backend.db import get_all_reagenttype_names, lookup_all_sample_types, create_kit_from_yaml, lookup_regent_by_type_name, lookup_kittype_by_use#, lookup_regent_by_type_name_and_kit_name
from backend.excel.parser import SheetParser
from jinja2 import Environment, FileSystemLoader
import sys
from pathlib import Path
import logging
import numpy as np
from .pop_ups import AlertPop

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
        # widget to get lot info
        lot_input = QLineEdit()
        lot_input.setObjectName("lot")
        lot_input.setText(reagent_lot)
        # widget to get expiry info
        exp_input = QDateEdit(calendarPopup=True)
        exp_input.setObjectName('expiry')
        # if expiry is not passed in from gui, use today
        if expiry == None:
            exp_input.setDate(QDate.currentDate())
        else:
            exp_input.setDate(expiry)
        # widget to get reagent type info
        type_input = QComboBox()
        type_input.setObjectName('type')
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
        self.layout.addWidget(QLabel("Lot:"))
        self.layout.addWidget(lot_input)
        self.layout.addWidget(QLabel("Expiry:\n(use exact date on reagent.\nEOL will be calculated from kit automatically)"))
        self.layout.addWidget(exp_input)
        self.layout.addWidget(QLabel("Type:"))
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
        start_date.setObjectName("start_date")
        start_date.setDate(QDate.currentDate())
        end_date = QDateEdit(calendarPopup=True)
        end_date.setObjectName("end_date")
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
        self.grid.addWidget(QLabel("Kit Name:"),2,0)
        # widget to get kit name
        kit_name = QLineEdit()
        kit_name.setObjectName("kit_name")
        self.grid.addWidget(kit_name,2,1)
        self.grid.addWidget(QLabel("Used For Sample Type:"),3,0)
        # widget to get uses of kit
        used_for = QComboBox()
        used_for.setObjectName("used_for")
        # Insert all existing sample types
        used_for.addItems(lookup_all_sample_types(ctx=parent_ctx))
        used_for.setEditable(True)
        self.grid.addWidget(used_for,3,1)
        # set cost per run
        self.grid.addWidget(QLabel("Constant cost per full plate (plates, work hours, etc.):"),4,0)
        # widget to get constant cost
        const_cost = QDoubleSpinBox() #QSpinBox()
        const_cost.setObjectName("const_cost")
        const_cost.setMinimum(0)
        const_cost.setMaximum(9999)
        self.grid.addWidget(const_cost,4,1)
        self.grid.addWidget(QLabel("Cost per column (multidrop reagents, etc.):"),5,0)
        # widget to get mutable costs per column
        mut_cost_col = QDoubleSpinBox() #QSpinBox()
        mut_cost_col.setObjectName("mut_cost_col")
        mut_cost_col.setMinimum(0)
        mut_cost_col.setMaximum(9999)
        self.grid.addWidget(mut_cost_col,5,1)
        self.grid.addWidget(QLabel("Cost per sample (tips, reagents, etc.):"),6,0)
        # widget to get mutable costs per column
        mut_cost_samp = QDoubleSpinBox() #QSpinBox()
        mut_cost_samp.setObjectName("mut_cost_samp")
        mut_cost_samp.setMinimum(0)
        mut_cost_samp.setMaximum(9999)
        self.grid.addWidget(mut_cost_samp,6,1)
        # button to add additional reagent types
        self.add_RT_btn = QPushButton("Add Reagent Type")
        self.grid.addWidget(self.add_RT_btn)
        self.add_RT_btn.clicked.connect(self.add_RT)
        self.submit_btn.clicked.connect(self.submit)

    def add_RT(self) -> None:
        """
        insert new reagent type row
        """        
        # get bottommost row
        maxrow = self.grid.rowCount()
        reg_form = ReagentTypeForm(parent_ctx=self.ctx)
        reg_form.setObjectName(f"ReagentForm_{maxrow}")
        self.grid.addWidget(reg_form, maxrow + 1,0,1,2)


    def submit(self) -> None:
        """
        send kit to database
        """        
        # get form info
        info, reagents = extract_form_info(self)
        logger.debug(f"kit info: {info}")
        yml_type = {}
        try:
            yml_type['password'] = info['password']
        except KeyError:
            pass
        used = info['used_for'].replace(" ", "_").lower()
        yml_type[used] = {}
        yml_type[used]['kits'] = {}
        yml_type[used]['kits'][info['kit_name']] = {}
        yml_type[used]['kits'][info['kit_name']]['constant_cost'] = info["const_cost"]
        yml_type[used]['kits'][info['kit_name']]['mutable_cost_column'] = info["mut_cost_col"]
        yml_type[used]['kits'][info['kit_name']]['mutable_cost_sample'] = info["mut_cost_samp"]
        yml_type[used]['kits'][info['kit_name']]['reagenttypes'] = reagents
        logger.debug(yml_type)
        # send to kit constructor
        result = create_kit_from_yaml(ctx=self.ctx, exp=yml_type)
        msg = AlertPop(message=result['message'], status=result['status'])
        msg.exec()

    # def extract_form_info(self, object):
    #     """
    #     retrieves arbitrary number of labels, values from form

    #     Args:
    #         object (_type_): the object to extract info from

    #     Returns:
    #         _type_: _description_
    #     """
    #     labels = []
    #     values = []
    #     reagents = {}
    #     for item in object.findChildren(QWidget):
    #         logger.debug(item.parentWidget())
    #         # if not isinstance(item.parentWidget(), ReagentTypeForm):
    #         match item:
    #             case QLabel():
    #                 labels.append(item.text().replace(" ", "_").strip(":").lower())
    #             case QLineEdit():
    #                 # ad hoc check to prevent double reporting of qdatedit under lineedit for some reason
    #                 if not isinstance(prev_item, QDateEdit) and not isinstance(prev_item, QComboBox) and not isinstance(prev_item, QSpinBox) and not isinstance(prev_item, QScrollBar):
    #                     logger.debug(f"Previous: {prev_item}")
    #                     logger.debug(f"Item: {item}, {item.text()}")
    #                     values.append(item.text().strip())
    #             case QComboBox():
    #                 values.append(item.currentText().strip())
    #             case QDateEdit():
    #                 values.append(item.date().toPyDate())
    #             case QSpinBox():
    #                 values.append(item.value())
    #             case ReagentTypeForm():
    #                 re_labels, re_values, _ = self.extract_form_info(item) 
    #                 reagent = {item[0]:item[1] for item in zip(re_labels, re_values)}
    #                 logger.debug(reagent)
    #                 # reagent = {reagent['name:']:{'eol':reagent['extension_of_life_(months):']}}
    #                 reagents[reagent["name_(*exactly*_as_it_appears_in_the_excel_submission_form)"].strip()] = {'eol_ext':int(reagent['extension_of_life_(months)'])}
    #         prev_item = item
    #     return labels, values, reagents

class ReagentTypeForm(QWidget):
    """
    custom widget to add information about a new reagenttype
    """    
    def __init__(self, parent_ctx:dict) -> None:
        super().__init__()
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel("Name (*Exactly* as it appears in the excel submission form):"),0,0)
        # Widget to get reagent info
        reagent_getter = QComboBox()
        reagent_getter.setObjectName("name")
        # lookup all reagent type names from db
        reagent_getter.addItems(get_all_reagenttype_names(ctx=parent_ctx))
        reagent_getter.setEditable(True)
        grid.addWidget(reagent_getter,0,1)
        grid.addWidget(QLabel("Extension of Life (months):"),0,2)
        # widget toget extension of life
        eol = QSpinBox()
        eol.setObjectName('eol')
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
        # NOTE: 2 month, but the variable name is the same cause I'm lazy
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


class ImportReagent(QComboBox):

    def __init__(self, ctx:dict, item:str, prsr:SheetParser|None=None):
        super().__init__()
        self.setEditable(True)
        # Ensure that all reagenttypes have a name that matches the items in the excel parser
        query_var = item.replace("lot_", "")
        if prsr != None:
            logger.debug(f"Import Reagent is looking at: {prsr.sub[item]} for {item}")
        else:
            logger.debug(f"Import Reagent is going to retrieve all reagents for {item}")
        logger.debug(f"Query for: {query_var}")
        if prsr != None:
            if isinstance(prsr.sub[item], np.float64):
                logger.debug(f"{prsr.sub[item]['lot']} is a numpy float!")
                try:
                    prsr.sub[item] = int(prsr.sub[item]['lot'])
                except ValueError:
                    pass
        # query for reagents using type name from sheet and kit from sheet
        logger.debug(f"Attempting lookup of reagents by type: {query_var}")
        # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
        relevant_reagents = [item.__str__() for item in lookup_regent_by_type_name(ctx=ctx, type_name=query_var)]#, kit_name=prsr.sub['extraction_kit'])]
        # relevant_reagents = [item.__str__() for item in lookup_regent_by_type_name_and_kit_name(ctx=ctx, type_name=query_var, kit_name=prsr.sub['extraction_kit'])]
        output_reg = []
        for reagent in relevant_reagents:
            # extract strings from any sets.
            if isinstance(reagent, set):
                for thing in reagent:
                    output_reg.append(thing)
            elif isinstance(reagent, str):
                output_reg.append(reagent)
        relevant_reagents = output_reg
        # if reagent in sheet is not found insert it into the front of relevant reagents so it shows 
        if prsr != None:
            logger.debug(f"Relevant reagents for {prsr.sub[item]}: {relevant_reagents}")
            if str(prsr.sub[item]['lot']) not in relevant_reagents:
                if check_not_nan(prsr.sub[item]['lot']):
                    relevant_reagents.insert(0, str(prsr.sub[item]['lot']))
            else:
                if len(relevant_reagents) > 1:
                    logger.debug(f"Found {prsr.sub[item]['lot']} in relevant reagents: {relevant_reagents}. Moving to front of list.")
                    idx = relevant_reagents.index(str(prsr.sub[item]['lot']))
                    logger.debug(f"The index we got for {prsr.sub[item]['lot']} in {relevant_reagents} was {idx}")
                    moved_reag = relevant_reagents.pop(idx)
                    relevant_reagents.insert(0, moved_reag)
                else:
                    logger.debug(f"Found {prsr.sub[item]['lot']} in relevant reagents: {relevant_reagents}. But no need to move due to short list.")
        logger.debug(f"New relevant reagents: {relevant_reagents}")
        self.setObjectName(f"lot_{item}")
        self.addItems(relevant_reagents)
        
