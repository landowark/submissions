'''
Contains miscellaneous widgets for frontend functions
'''
from datetime import date
from pprint import pformat
from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout,
    QLineEdit, QComboBox, QDialog, 
    QDialogButtonBox, QDateEdit, QSizePolicy, QWidget,
    QGridLayout, QPushButton, QSpinBox, QDoubleSpinBox,
    QHBoxLayout, QScrollArea, QFormLayout
)
from PyQt6.QtCore import Qt, QDate, QSize, pyqtSignal
from tools import check_not_nan, jinja_template_loading, Settings
from backend.db.functions import (lookup_reagent_types, lookup_reagents, lookup_submission_type, lookup_reagenttype_kittype_association, \
    lookup_submissions, lookup_organizations, lookup_kit_types)
from backend.db.models import *
from sqlalchemy import FLOAT, INTEGER
import logging
import numpy as np
from .pop_ups import AlertPop, QuestionAsker
from backend.validators import PydReagent, PydKit, PydReagentType, PydSubmission
from typing import Tuple, List
from pprint import pformat
import difflib


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
        # self.type_input.addItems([item.name for item in lookup_reagent_types(ctx=ctx)])
        self.type_input.addItems([item.name for item in ReagentType.query()])
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

    def parse_form(self):
        return dict(name=self.name_input.currentText(), 
                    lot=self.lot_input.text(), 
                    expiry=self.exp_input.date().toPyDate(),
                    type=self.type_input.currentText())

    def update_names(self):
        """
        Updates reagent names form field with examples from reagent type
        """        
        logger.debug(self.type_input.currentText())
        self.name_input.clear()
        # lookup = lookup_reagents(ctx=self.ctx, reagent_type=self.type_input.currentText())
        lookup = Reagent.query(reagent_type=self.type_input.currentText())
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

    def parse_form(self):
        return dict(start_date=self.start_date.date().toPyDate(), end_date = self.end_date.date().toPyDate())

class KitAdder(QWidget):
    """
    dialog to get information to add kit
    """    
    def __init__(self, parent_ctx:Settings) -> None:
        super().__init__()
        self.ctx = parent_ctx
        main_box = QVBoxLayout(self)
        scroll = QScrollArea(self)
        main_box.addWidget(scroll)
        scroll.setWidgetResizable(True)    
        scrollContent = QWidget(scroll)
        self.grid = QGridLayout()
        # self.setLayout(self.grid)
        scrollContent.setLayout(self.grid)
        # insert submit button at top
        self.submit_btn = QPushButton("Submit")
        self.grid.addWidget(self.submit_btn,0,0,1,1)
        self.grid.addWidget(QLabel("Kit Name:"),2,0)
        # widget to get kit name
        kit_name = QLineEdit()
        kit_name.setObjectName("kit_name")
        self.grid.addWidget(kit_name,2,1)
        self.grid.addWidget(QLabel("Used For Submission Type:"),3,0)
        # widget to get uses of kit
        used_for = QComboBox()
        used_for.setObjectName("used_for")
        # Insert all existing sample types
        # used_for.addItems([item.name for item in lookup_submission_type(ctx=parent_ctx)])
        used_for.addItems([item.name for item in SubmissionType.query()])
        used_for.setEditable(True)
        self.grid.addWidget(used_for,3,1)
        # Get all fields in SubmissionTypeKitTypeAssociation
        self.columns = [item for item in SubmissionTypeKitTypeAssociation.__table__.columns if len(item.foreign_keys) == 0]
        for iii, column in enumerate(self.columns):
            idx = iii + 4
            # convert field name to human readable.
            field_name = column.name.replace("_", " ").title()
            self.grid.addWidget(QLabel(field_name),idx,0)
            match column.type:
                case FLOAT():
                    add_widget = QDoubleSpinBox()
                    add_widget.setMinimum(0)
                    add_widget.setMaximum(9999)
                case INTEGER():
                    add_widget = QSpinBox()
                    add_widget.setMinimum(0)
                    add_widget.setMaximum(9999)
                case _:
                    add_widget = QLineEdit()
            add_widget.setObjectName(column.name)
            self.grid.addWidget(add_widget, idx,1)
        self.add_RT_btn = QPushButton("Add Reagent Type")
        self.grid.addWidget(self.add_RT_btn)
        self.add_RT_btn.clicked.connect(self.add_RT)
        self.submit_btn.clicked.connect(self.submit)
        scroll.setWidget(scrollContent)
        self.ignore = [None, "", "qt_spinbox_lineedit", "qt_scrollarea_viewport", "qt_scrollarea_hcontainer",
                       "qt_scrollarea_vcontainer", "submit_btn"
                       ]
        

    def add_RT(self) -> None:
        """
        insert new reagent type row
        """        
        # get bottommost row
        maxrow = self.grid.rowCount()
        reg_form = ReagentTypeForm(ctx=self.ctx)
        reg_form.setObjectName(f"ReagentForm_{maxrow}")
        # self.grid.addWidget(reg_form, maxrow + 1,0,1,2)
        self.grid.addWidget(reg_form, maxrow,0,1,4)
        


    def submit(self) -> None:
        """
        send kit to database
        """        
        # get form info
        info, reagents = self.parse_form()
        # info, reagents = extract_form_info(self)
        info = {k:v for k,v in info.items() if k in [column.name for column in self.columns] + ['kit_name', 'used_for']}
        logger.debug(f"kit info: {pformat(info)}")
        logger.debug(f"kit reagents: {pformat(reagents)}")
        info['reagent_types'] = reagents
        logger.debug(pformat(info))
        # send to kit constructor
        kit = PydKit(name=info['kit_name'])
        for reagent in info['reagent_types']:
            uses = {
                info['used_for']:
                    {'sheet':reagent['sheet'],
                     'name':reagent['name'],
                     'lot':reagent['lot'],
                     'expiry':reagent['expiry']
                    }}
            kit.reagent_types.append(PydReagentType(name=reagent['rtname'], eol_ext=reagent['eol'], uses=uses))
        logger.debug(f"Output pyd object: {kit.__dict__}")
        # result = construct_kit_from_yaml(ctx=self.ctx, kit_dict=info)
        sqlobj, result = kit.toSQL(self.ctx)
        sqlobj.save()
        msg = AlertPop(message=result['message'], status=result['status'])
        msg.exec()
        self.__init__(self.ctx)

    def parse_form(self) -> Tuple[dict, list]:
        logger.debug(f"Hello from {self.__class__} parser!")
        info = {}
        reagents = []
        widgets = [widget for widget in self.findChildren(QWidget) if widget.objectName() not in self.ignore and not isinstance(widget.parent(), ReagentTypeForm)]
        for widget in widgets:
            # logger.debug(f"Parsed widget: {widget.objectName()} of type {type(widget)} with parent {widget.parent()}")
            match widget:
                case ReagentTypeForm():
                    reagents.append(widget.parse_form())
                case QLineEdit():
                    info[widget.objectName()] = widget.text()
                case QComboBox():
                    info[widget.objectName()] = widget.currentText()
                case QDateEdit():
                    info[widget.objectName()] = widget.date().toPyDate()
        return info, reagents
        
class ReagentTypeForm(QWidget):
    """
    custom widget to add information about a new reagenttype
    """    
    def __init__(self, ctx:Settings) -> None:
        super().__init__()
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel("Reagent Type Name"),0,0)
        # Widget to get reagent info
        self.reagent_getter = QComboBox()
        self.reagent_getter.setObjectName("rtname")
        # lookup all reagent type names from db
        # lookup = lookup_reagent_types(ctx=ctx)
        lookup = ReagentType.query()
        logger.debug(f"Looked up ReagentType names: {lookup}")
        self.reagent_getter.addItems([item.__str__() for item in lookup])
        self.reagent_getter.setEditable(True)
        grid.addWidget(self.reagent_getter,0,1)
        grid.addWidget(QLabel("Extension of Life (months):"),0,2)
        # widget to get extension of life
        self.eol = QSpinBox()
        self.eol.setObjectName('eol')
        self.eol.setMinimum(0)
        grid.addWidget(self.eol, 0,3)
        grid.addWidget(QLabel("Excel Location Sheet Name:"),1,0)
        self.location_sheet_name = QLineEdit()
        self.location_sheet_name.setObjectName("sheet")
        self.location_sheet_name.setText("e.g. 'Reagent Info'")
        grid.addWidget(self.location_sheet_name, 1,1)
        for iii, item in enumerate(["Name", "Lot", "Expiry"]):
            idx = iii + 2
            grid.addWidget(QLabel(f"{item} Row:"), idx, 0)
            row = QSpinBox()
            row.setFixedWidth(50)
            row.setObjectName(f'{item.lower()}_row')
            row.setMinimum(0)
            grid.addWidget(row, idx, 1)
            grid.addWidget(QLabel(f"{item} Column:"), idx, 2)
            col = QSpinBox()
            col.setFixedWidth(50)
            col.setObjectName(f'{item.lower()}_column')
            col.setMinimum(0)
            grid.addWidget(col, idx, 3)
        self.setFixedHeight(175)
        max_row = grid.rowCount()
        self.r_button = QPushButton("Remove")
        self.r_button.clicked.connect(self.remove)
        grid.addWidget(self.r_button,max_row,0,1,1)
        self.ignore = [None, "", "qt_spinbox_lineedit", "qt_scrollarea_viewport", "qt_scrollarea_hcontainer",
                       "qt_scrollarea_vcontainer", "submit_btn", "eol", "sheet", "rtname"
                       ]

    def remove(self):
        self.setParent(None)
        self.destroy()

    def parse_form(self) -> dict:
        logger.debug(f"Hello from {self.__class__} parser!")
        info = {}
        info['eol'] = self.eol.value()
        info['sheet'] = self.location_sheet_name.text()
        info['rtname'] = self.reagent_getter.currentText()
        widgets = [widget for widget in self.findChildren(QWidget) if widget.objectName() not in self.ignore]
        for widget in widgets:
            logger.debug(f"Parsed widget: {widget.objectName()} of type {type(widget)} with parent {widget.parent()}")
            match widget:
                case QLineEdit():
                    info[widget.objectName()] = widget.text()
                case QComboBox():
                    info[widget.objectName()] = widget.currentText()
                case QDateEdit():
                    info[widget.objectName()] = widget.date().toPyDate()
                case QSpinBox() | QDoubleSpinBox():
                    if "_" in widget.objectName():
                        key, sub_key = widget.objectName().split("_")
                        if key not in info.keys():
                            info[key] = {}
                            logger.debug(f"Adding key {key}, {sub_key} and value {widget.value()} to {info}")
                        info[key][sub_key] = widget.value()        
        return info

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

class FirstStrandSalvage(QDialog):

    def __init__(self, ctx:Settings, submitter_id:str, rsl_plate_num:str|None=None) -> None:
        super().__init__()
        if rsl_plate_num == None:
            rsl_plate_num = ""
        self.setWindowTitle("Add Reagent")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.submitter_id_input = QLineEdit()
        self.submitter_id_input.setText(submitter_id)
        self.rsl_plate_num = QLineEdit()
        self.rsl_plate_num.setText(rsl_plate_num)
        self.row_letter = QComboBox()
        self.row_letter.addItems(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'])
        self.row_letter.setEditable(False)
        self.column_number = QComboBox()
        self.column_number.addItems(['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'])
        self.column_number.setEditable(False)
        self.layout = QFormLayout()
        self.layout.addRow(self.tr("&Sample Number:"), self.submitter_id_input)
        self.layout.addRow(self.tr("&Plate Number:"), self.rsl_plate_num)
        self.layout.addRow(self.tr("&Source Row:"), self.row_letter)
        self.layout.addRow(self.tr("&Source Column:"), self.column_number)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self):
        return dict(plate=self.rsl_plate_num.text(), submitter_id=self.submitter_id_input.text(), well=f"{self.row_letter.currentText()}{self.column_number.currentText()}")

class FirstStrandPlateList(QDialog):

    def __init__(self, ctx:Settings) -> None:
        super().__init__()
        self.setWindowTitle("First Strand Plates")

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel

        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # ww = [item.rsl_plate_num for item in lookup_submissions(ctx=ctx, submission_type="Wastewater")]
        ww = [item.rsl_plate_num for item in BasicSubmission.query(submission_type="Wastewater")]
        self.plate1 = QComboBox()
        self.plate2 = QComboBox()
        self.plate3 = QComboBox()
        self.layout = QFormLayout()
        for ii, plate in enumerate([self.plate1, self.plate2, self.plate3]):
            plate.addItems(ww)
            self.layout.addRow(self.tr(f"&Plate {ii+1}:"), plate)
        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)

    def parse_form(self):
        output = []
        for plate in [self.plate1, self.plate2, self.plate3]:
            output.append(plate.currentText())
        return output

class ReagentFormWidget(QWidget):

    def __init__(self, parent:QWidget, reagent:PydReagent, extraction_kit:str):
        super().__init__(parent)
        # self.setParent(parent)
        self.reagent = reagent
        self.extraction_kit = extraction_kit
        self.ctx = reagent.ctx
        layout = QVBoxLayout()
        self.label = self.ReagentParsedLabel(reagent=reagent)
        layout.addWidget(self.label)
        self.lot = self.ReagentLot(reagent=reagent, extraction_kit=extraction_kit)
        layout.addWidget(self.lot)
        # Remove spacing between reagents
        layout.setContentsMargins(0,0,0,0)
        self.setLayout(layout)
        self.setObjectName(reagent.name)
        self.missing = reagent.missing
        # If changed set self.missing to True and update self.label
        self.lot.currentTextChanged.connect(self.updated)

    def parse_form(self) -> Tuple[PydReagent, dict]:
        lot = self.lot.currentText()
        # wanted_reagent = lookup_reagents(ctx=self.ctx, lot_number=lot, reagent_type=self.reagent.type)
        wanted_reagent = Reagent.query(lot_number=lot, reagent_type=self.reagent.type)
        # if reagent doesn't exist in database, off to add it (uses App.add_reagent)
        if wanted_reagent == None:
            dlg = QuestionAsker(title=f"Add {lot}?", message=f"Couldn't find reagent type {self.reagent.type}: {lot} in the database.\n\nWould you like to add it?")
            if dlg.exec():
                wanted_reagent = self.parent().parent().parent().parent().parent().parent().parent().parent().parent.add_reagent(reagent_lot=lot, reagent_type=self.reagent.type, expiry=self.reagent.expiry, name=self.reagent.name)
                return wanted_reagent, None
            else:
                # In this case we will have an empty reagent and the submission will fail kit integrity check
                logger.debug("Will not add reagent.")
                return None, dict(message="Failed integrity check", status="critical")
        else:
            # Since this now gets passed in directly from the parser -> pyd -> form and the parser gets the name
            # from the db, it should no longer be necessary to query the db with reagent/kit, but with rt name directly.
            # rt = lookup_reagent_types(ctx=self.ctx, name=self.reagent.type)
            # rt = lookup_reagent_types(ctx=self.ctx, kit_type=self.extraction_kit, reagent=wanted_reagent)
            rt = ReagentType.query(name=self.reagent.type)
            if rt == None:
                # rt = lookup_reagent_types(ctx=self.ctx, kit_type=self.extraction_kit, reagent=wanted_reagent)
                rt = ReagentType.query(kit_type=self.extraction_kit, reagent=wanted_reagent)
            return PydReagent(ctx=self.ctx, name=wanted_reagent.name, lot=wanted_reagent.lot, type=rt.name, expiry=wanted_reagent.expiry, parsed=not self.missing), None

    def updated(self):
        self.missing = True
        self.label.updated(self.reagent.type)


    class ReagentParsedLabel(QLabel):
        
        def __init__(self, reagent:PydReagent):
            super().__init__()
            try:
                check = not reagent.missing
            except:
                check = False
            self.setObjectName(f"{reagent.type}_label")
            if check:
                self.setText(f"Parsed {reagent.type}")
            else:
                self.setText(f"MISSING {reagent.type}")
        
        def updated(self, reagent_type:str):
            self.setText(f"UPDATED {reagent_type}")

    class ReagentLot(QComboBox):

        def __init__(self, reagent, extraction_kit:str) -> None:
            super().__init__()
            self.ctx = reagent.ctx
            self.setEditable(True)
            # if reagent.parsed:
            #     pass
            logger.debug(f"Attempting lookup of reagents by type: {reagent.type}")
            # below was lookup_reagent_by_type_name_and_kit_name, but I couldn't get it to work.
            # lookup = lookup_reagents(ctx=self.ctx, reagent_type=reagent.type)
            lookup = Reagent.query(reagent_type=reagent.type)
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
                    # looked_up_rt = lookup_reagenttype_kittype_association(ctx=self.ctx, reagent_type=reagent.type, kit_type=extraction_kit)
                    looked_up_rt = KitTypeReagentTypeAssociation.query(reagent_type=reagent.type, kit_type=extraction_kit)
                    try:
                        # looked_up_reg = lookup_reagents(ctx=self.ctx, lot_number=looked_up_rt.last_used)
                        looked_up_reg = Reagent.query(lot_number=looked_up_rt.last_used)
                    except AttributeError:
                        looked_up_reg = None
                    logger.debug(f"Because there was no reagent listed for {reagent.lot}, we will insert the last lot used: {looked_up_reg}")
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

class SubmissionFormWidget(QWidget):

    def __init__(self, parent: QWidget, **kwargs) -> None:
        super().__init__(parent)
        # self.ignore = [None, "", "qt_spinbox_lineedit", "qt_scrollarea_viewport", "qt_scrollarea_hcontainer",
        #                "qt_scrollarea_vcontainer", "submit_btn"
        #                ]
        self.ignore = ['filepath', 'samples', 'reagents', 'csv', 'ctx']
        layout = QVBoxLayout()
        for k, v in kwargs.items():
            if k not in self.ignore:
                add_widget = self.create_widget(key=k, value=v, submission_type=kwargs['submission_type'])
                if add_widget != None:
                    layout.addWidget(add_widget)
            else:
                setattr(self, k, v)
        self.setLayout(layout)

    def create_widget(self, key:str, value:dict, submission_type:str|None=None):
        if key not in self.ignore:
            return self.InfoItem(self, key=key, value=value, submission_type=submission_type)
        return None
        
    def clear_form(self):
        for item in self.findChildren(QWidget):
            item.setParent(None)

    def find_widgets(self, object_name:str|None=None) -> List[QWidget]:
        query = self.findChildren(QWidget)
        if object_name != None:
            query = [widget for widget in query if widget.objectName()==object_name]
        return query
    
    def parse_form(self) -> PydSubmission:
        logger.debug(f"Hello from form parser!")
        info = {}
        reagents = []
        if hasattr(self, 'csv'):
            info['csv'] = self.csv
        # samples = self.parent().parent.parent.samples
        # filepath = self.parent().parent.parent.pyd.filepath
        # logger.debug(f"Using samples: {pformat(samples)}")
        # widgets = [widget for widget in self.findChildren(QWidget) if widget.objectName() not in self.ignore]
        # widgets = [widget for widget in self.findChildren(QWidget)]
        # for widget in widgets:
        for widget in self.findChildren(QWidget):
            logger.debug(f"Parsed widget of type {type(widget)}")
            match widget:
                case ReagentFormWidget():
                    reagent, _ = widget.parse_form()
                    reagents.append(reagent)
                case self.InfoItem():
                    field, value = widget.parse_form()
                    if field != None:
                        info[field] = value
                # case ImportReagent():
                #     reagent = dict(name=widget.objectName().replace("lot_", ""), lot=widget.currentText(), type=None, expiry=None)
                #     # ctx: self.SubmissionContinerWidget.AddSubForm
                #     reagents.append(PydReagent(ctx=self.parent.parent.ctx, **reagent))
                # case QLineEdit():
                #     info[widget.objectName()] = dict(value=widget.text())
                # case QComboBox():
                #     info[widget.objectName()] = dict(value=widget.currentText())
                # case QDateEdit():
                #     info[widget.objectName()] = dict(value=widget.date().toPyDate())
        logger.debug(f"Info: {pformat(info)}")
        logger.debug(f"Reagents: {pformat(reagents)}")
        app = self.parent().parent().parent().parent().parent().parent().parent().parent
        submission = PydSubmission(ctx=app.ctx, filepath=self.filepath, reagents=reagents, samples=self.samples, **info)
        return submission
    
    class InfoItem(QWidget):

        def __init__(self, parent: QWidget, key:str, value:dict, submission_type:str|None=None) -> None:
            super().__init__(parent)
            layout = QVBoxLayout()
            self.label = self.ParsedQLabel(key=key, value=value)
            self.input: QWidget = self.set_widget(parent=self, key=key, value=value, submission_type=submission_type['value'])
            self.setObjectName(key)
            try:
                self.missing:bool = value['missing']
            except (TypeError, KeyError):
                self.missing:bool = False
            if self.input != None:
                layout.addWidget(self.label)
                layout.addWidget(self.input)
            layout.setContentsMargins(0,0,0,0)
            self.setLayout(layout)
            match self.input:
                case QComboBox():
                    self.input.currentTextChanged.connect(self.update_missing)
                case QDateEdit():
                    self.input.dateChanged.connect(self.update_missing)
                case QLineEdit():
                    self.input.textChanged.connect(self.update_missing)
            
        def parse_form(self):
            match self.input:
                case QLineEdit():
                    value = self.input.text()
                case QComboBox():
                    value = self.input.currentText()
                case QDateEdit():
                    value = self.input.date().toPyDate()
                case _:
                    return None, None
            return self.input.objectName(), dict(value=value, missing=self.missing)
        
        def set_widget(self, parent: QWidget, key:str, value:dict, submission_type:str|None=None) -> QWidget:
            try:
                value = value['value']
            except (TypeError, KeyError):
                pass
            obj = parent.parent().parent()
            logger.debug(f"Creating widget for: {key}")
            match key:
                case 'submitting_lab':
                    add_widget = QComboBox()
                    # lookup organizations suitable for submitting_lab (ctx: self.InfoItem.SubmissionFormWidget.SubmissionFormContainer.AddSubForm )
                    # labs = [item.__str__() for item in lookup_organizations(ctx=obj.ctx)]
                    labs = [item.__str__() for item in Organization.query()]
                    # try to set closest match to top of list
                    try:
                        labs = difflib.get_close_matches(value, labs, len(labs), 0)
                    except (TypeError, ValueError):
                        pass
                    # set combobox values to lookedup values
                    add_widget.addItems(labs)
                case 'extraction_kit':
                    # if extraction kit not available, all other values fail
                    if not check_not_nan(value):
                        msg = AlertPop(message="Make sure to check your extraction kit in the excel sheet!", status="warning")
                        msg.exec()
                    # create combobox to hold looked up kits
                    add_widget = QComboBox()
                    # lookup existing kits by 'submission_type' decided on by sheetparser
                    logger.debug(f"Looking up kits used for {submission_type}")
                    # uses = [item.__str__() for item in lookup_kit_types(ctx=obj.ctx, used_for=submission_type)]
                    uses = [item.__str__() for item in KitType.query(used_for=submission_type)]
                    obj.uses = uses
                    logger.debug(f"Kits received for {submission_type}: {uses}")
                    if check_not_nan(value):
                        logger.debug(f"The extraction kit in parser was: {value}")
                        uses.insert(0, uses.pop(uses.index(value)))
                        obj.ext_kit = value
                    else:
                        logger.error(f"Couldn't find {obj.prsr.sub['extraction_kit']}")
                        obj.ext_kit = uses[0]
                    add_widget.addItems(uses)
                    
                    # Run reagent scraper whenever extraction kit is changed.
                    # add_widget.currentTextChanged.connect(obj.scrape_reagents)
                case 'submitted_date':
                    # uses base calendar
                    add_widget = QDateEdit(calendarPopup=True)
                    # sets submitted date based on date found in excel sheet
                    try:
                        add_widget.setDate(value)
                    # if not found, use today
                    except:
                        add_widget.setDate(date.today())
                case 'submission_category':
                    add_widget = QComboBox()
                    cats = ['Diagnostic', "Surveillance", "Research"]
                    # cats += [item.name for item in lookup_submission_type(ctx=obj.ctx)]
                    cats += [item.name for item in SubmissionType.query()]
                    try:
                        cats.insert(0, cats.pop(cats.index(value)))
                    except ValueError:
                        cats.insert(0, cats.pop(cats.index(submission_type)))
                    add_widget.addItems(cats)
                case _:
                    # anything else gets added in as a line edit
                    add_widget = QLineEdit()
                    logger.debug(f"Setting widget text to {str(value).replace('_', ' ')}")
                    add_widget.setText(str(value).replace("_", " "))
            if add_widget != None:
                add_widget.setObjectName(key)
                add_widget.setParent(parent)
                
            return add_widget
            
        def update_missing(self):
            self.missing = True
            self.label.updated(self.objectName())

        class ParsedQLabel(QLabel):

            def __init__(self, key:str, value:dict, title:bool=True, label_name:str|None=None):
                super().__init__()
                try:
                    check = not value['missing']
                except:
                    check = True
                if label_name != None:
                    self.setObjectName(label_name)
                else:
                    self.setObjectName(f"{key}_label")
                if title:
                    output = key.replace('_', ' ').title()
                else:
                    output = key.replace('_', ' ')
                if check:
                    self.setText(f"Parsed {output}")
                else:
                    self.setText(f"MISSING {output}")

            def updated(self, key:str, title:bool=True):
                if title:
                    output = key.replace('_', ' ').title()
                else:
                    output = key.replace('_', ' ')
                self.setText(f"UPDATED {output}")

