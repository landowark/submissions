'''
Contains miscellaneous widgets for frontend functions
'''
from datetime import date
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog, 
    QDialogButtonBox, QDateEdit, QSizePolicy, QWidget,
    QGridLayout, QPushButton, QSpinBox, QDoubleSpinBox,
    QHBoxLayout
)
from PyQt6.QtCore import Qt, QDate, QSize
from tools import check_not_nan, jinja_template_loading, Settings
from ..all_window_functions import extract_form_info
from backend.db import construct_kit_from_yaml, \
    lookup_reagent_types, lookup_reagents, lookup_submission_type, lookup_reagenttype_kittype_association
import logging
import numpy as np
from .pop_ups import AlertPop
from backend.pydant import PydReagent

logger = logging.getLogger(f"submissions.{__name__}")

env = jinja_template_loading()

class AddReagentForm(QDialog):
    """
    dialog to add gather info about new reagent
    """    
    def __init__(self, ctx:dict, reagent_lot:str|None=None, reagent_type:str|None=None, expiry:date|None=None, reagent_name:str|None=None) -> None:
        super().__init__()
        self.ctx = ctx
        if reagent_lot == None:
            reagent_lot = reagent_type

        self.setWindowTitle("Add Reagent")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # widget to get lot info
        self.name_input = QComboBox()
        self.name_input.setObjectName("name")
        self.name_input.setEditable(True)
        self.name_input.setCurrentText(reagent_name)
        # self.name_input.setText(reagent_name)
        self.lot_input = QLineEdit()
        self.lot_input.setObjectName("lot")
        self.lot_input.setText(reagent_lot)
        # widget to get expiry info
        self.exp_input = QDateEdit(calendarPopup=True)
        self.exp_input.setObjectName('expiry')
        # if expiry is not passed in from gui, use today
        if expiry == None:
            self.exp_input.setDate(QDate.currentDate())
        else:
            self.exp_input.setDate(expiry)
        # widget to get reagent type info
        self.type_input = QComboBox()
        self.type_input.setObjectName('type')
        self.type_input.addItems([item.name for item in lookup_reagent_types(ctx=ctx)])
        logger.debug(f"Trying to find index of {reagent_type}")
        # convert input to user friendly string?
        try:
            reagent_type = reagent_type.replace("_", " ").title()
        except AttributeError:
            reagent_type = None
        # set parsed reagent type to top of list
        index = self.type_input.findText(reagent_type, Qt.MatchFlag.MatchEndsWith)
        if index >= 0:
            self.type_input.setCurrentIndex(index)
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Name:"))
        self.layout.addWidget(self.name_input)
        self.layout.addWidget(QLabel("Lot:"))
        self.layout.addWidget(self.lot_input)
        self.layout.addWidget(QLabel("Expiry:\n(use exact date on reagent.\nEOL will be calculated from kit automatically)"))
        self.layout.addWidget(self.exp_input)
        self.layout.addWidget(QLabel("Type:"))
        self.layout.addWidget(self.type_input)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)
        self.type_input.currentTextChanged.connect(self.update_names)

    def update_names(self):
        """
        Updates reagent names form field with examples from reagent type
        """        
        logger.debug(self.type_input.currentText())
        self.name_input.clear()
        lookup = lookup_reagents(ctx=self.ctx, reagent_type=self.type_input.currentText())
        self.name_input.addItems(list(set([item.name for item in lookup])))

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
        self.start_date = QDateEdit(calendarPopup=True)
        self.start_date.setObjectName("start_date")
        self.start_date.setDate(QDate.currentDate())
        self.end_date = QDateEdit(calendarPopup=True)
        self.end_date.setObjectName("end_date")
        self.end_date.setDate(QDate.currentDate())
        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("Start Date"))
        self.layout.addWidget(self.start_date)
        self.layout.addWidget(QLabel("End Date"))
        self.layout.addWidget(self.end_date)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

class KitAdder(QWidget):
    """
    dialog to get information to add kit
    """    
    def __init__(self, parent_ctx:Settings) -> None:
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
        # used_for.addItems(lookup_all_sample_types(ctx=parent_ctx))
        used_for.addItems([item.name for item in lookup_submission_type(ctx=parent_ctx)])
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
        used = info['used_for']
        yml_type[used] = {}
        yml_type[used]['kits'] = {}
        yml_type[used]['kits'][info['kit_name']] = {}
        yml_type[used]['kits'][info['kit_name']]['constant_cost'] = info["const_cost"]
        yml_type[used]['kits'][info['kit_name']]['mutable_cost_column'] = info["mut_cost_col"]
        yml_type[used]['kits'][info['kit_name']]['mutable_cost_sample'] = info["mut_cost_samp"]
        yml_type[used]['kits'][info['kit_name']]['reagenttypes'] = reagents
        logger.debug(yml_type)
        # send to kit constructor
        result = construct_kit_from_yaml(ctx=self.ctx, exp=yml_type)
        msg = AlertPop(message=result['message'], status=result['status'])
        msg.exec()
        self.__init__(self.ctx)

class ReagentTypeForm(QWidget):
    """
    custom widget to add information about a new reagenttype
    """    
    def __init__(self, ctx:dict) -> None:
        super().__init__()
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel("Name (*Exactly* as it appears in the excel submission form):"),0,0)
        # Widget to get reagent info
        self.reagent_getter = QComboBox()
        self.reagent_getter.setObjectName("name")
        # lookup all reagent type names from db
        lookup = lookup_reagent_types(ctx=ctx)
        logger.debug(f"Looked up ReagentType names: {lookup}")
        self.reagent_getter.addItems([item.__str__() for item in lookup])
        self.reagent_getter.setEditable(True)
        grid.addWidget(self.reagent_getter,0,1)
        grid.addWidget(QLabel("Extension of Life (months):"),0,2)
        # widget to get extension of life
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
        # start date is two months prior to end date by default
        twomonthsago = QDate.currentDate().addDays(-60)
        self.start_date.setDate(twomonthsago)
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

    def __init__(self, ctx:Settings, reagent:dict|PydReagent, extraction_kit:str):
        super().__init__()
        self.setEditable(True)
        if isinstance(reagent, dict):
            reagent = PydReagent(**reagent)
        # Ensure that all reagenttypes have a name that matches the items in the excel parser
        query_var = reagent.type
        logger.debug(f"Import Reagent is looking at: {reagent.lot} for {query_var}")
        if isinstance(reagent.lot, np.float64):
            logger.debug(f"{reagent.lot} is a numpy float!")
            try:
                reagent.lot = int(reagent.lot)
            except ValueError:
                pass
        # query for reagents using type name from sheet and kit from sheet
        logger.debug(f"Attempting lookup of reagents by type: {query_var}")
        # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
        lookup = lookup_reagents(ctx=ctx, reagent_type=query_var)
        relevant_reagents = [item.__str__() for item in lookup]
        output_reg = []
        for rel_reagent in relevant_reagents:
            # extract strings from any sets.
            if isinstance(rel_reagent, set):
                for thing in rel_reagent:
                    output_reg.append(thing)
            elif isinstance(rel_reagent, str):
                output_reg.append(rel_reagent)
        relevant_reagents = output_reg
        # if reagent in sheet is not found insert it into the front of relevant reagents so it shows 
        logger.debug(f"Relevant reagents for {reagent.lot}: {relevant_reagents}")
        if str(reagent.lot) not in relevant_reagents:
            if check_not_nan(reagent.lot):
                relevant_reagents.insert(0, str(reagent.lot))
            else:
                # TODO: look up the last used reagent of this type in the database
                looked_up_rt = lookup_reagenttype_kittype_association(ctx=ctx, reagent_type=reagent.type, kit_type=extraction_kit)
                looked_up_reg = lookup_reagents(ctx=ctx, lot_number=looked_up_rt.last_used)
                logger.debug(f"Because there was no reagent listed for {reagent}, we will insert the last lot used: {looked_up_reg}")
                if looked_up_reg != None:
                    relevant_reagents.remove(str(looked_up_reg.lot))
                    relevant_reagents.insert(0, str(looked_up_reg.lot))
        else:
            if len(relevant_reagents) > 1:
                logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. Moving to front of list.")
                idx = relevant_reagents.index(str(reagent.lot))
                logger.debug(f"The index we got for {reagent.lot} in {relevant_reagents} was {idx}")
                moved_reag = relevant_reagents.pop(idx)
                relevant_reagents.insert(0, moved_reag)
            else:
                logger.debug(f"Found {reagent.lot} in relevant reagents: {relevant_reagents}. But no need to move due to short list.")
        logger.debug(f"New relevant reagents: {relevant_reagents}")
        self.setObjectName(f"lot_{reagent.type}")
        self.addItems(relevant_reagents)

class ParsedQLabel(QLabel):

    def __init__(self, input_object, field_name, title:bool=True, label_name:str|None=None):
        super().__init__()
        try:
            check = input_object['parsed']
        except:
            return
        if label_name != None:
            self.setObjectName(label_name)
        if title:
            output = field_name.replace('_', ' ').title()
        else:
            output = field_name.replace('_', ' ')
        if check:
            self.setText(f"Parsed {output}")
        else:
            self.setText(f"MISSING {output}")
