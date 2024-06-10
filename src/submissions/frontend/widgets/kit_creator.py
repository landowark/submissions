from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea,
    QGridLayout, QPushButton, QLabel,
    QLineEdit, QComboBox, QDoubleSpinBox,
    QSpinBox, QDateEdit
)
from sqlalchemy import FLOAT, INTEGER
from backend.db import SubmissionTypeKitTypeAssociation, SubmissionType, ReagentRole
from backend.validators import PydReagentRole, PydKit
import logging
from pprint import pformat
from tools import Report
from typing import Tuple

logger = logging.getLogger(f"submissions.{__name__}")


class KitAdder(QWidget):
    """
    dialog to get information to add kit
    """    
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.report = Report()
        self.app = parent.parent
        main_box = QVBoxLayout(self)
        scroll = QScrollArea(self)
        main_box.addWidget(scroll)
        scroll.setWidgetResizable(True)    
        scrollContent = QWidget(scroll)
        self.grid = QGridLayout()
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
        reg_form = ReagentRoleForm(parent=self)
        reg_form.setObjectName(f"ReagentForm_{maxrow}")
        self.grid.addWidget(reg_form, maxrow,0,1,4)
        
    def submit(self) -> None:
        """
        send kit to database
        """        
        report = Report()
        # get form info
        info, reagents = self.parse_form()
        info = {k:v for k,v in info.items() if k in [column.name for column in self.columns] + ['kit_name', 'used_for']}
        # logger.debug(f"kit info: {pformat(info)}")
        # logger.debug(f"kit reagents: {pformat(reagents)}")
        info['reagent_roles'] = reagents
        # logger.debug(pformat(info))
        # send to kit constructor
        kit = PydKit(name=info['kit_name'])
        for reagent in info['reagent_roles']:
            uses = {
                info['used_for']:
                    {'sheet':reagent['sheet'],
                     'name':reagent['name'],
                     'lot':reagent['lot'],
                     'expiry':reagent['expiry']
                    }}
            kit.reagent_roles.append(PydReagentRole(name=reagent['rtname'], eol_ext=reagent['eol'], uses=uses))
        # logger.debug(f"Output pyd object: {kit.__dict__}")
        sqlobj, result = kit.toSQL(self.ctx)
        report.add_result(result=result)
        sqlobj.save()
        
        self.__init__(self.parent())

    def parse_form(self) -> Tuple[dict, list]:
        """
        Pulls reagent and general info from form

        Returns:
            Tuple[dict, list]: dict=info, list=reagents
        """        
        # logger.debug(f"Hello from {self.__class__} parser!")
        info = {}
        reagents = []
        widgets = [widget for widget in self.findChildren(QWidget) if widget.objectName() not in self.ignore and not isinstance(widget.parent(), ReagentRoleForm)]
        for widget in widgets:
            # logger.debug(f"Parsed widget: {widget.objectName()} of type {type(widget)} with parent {widget.parent()}")
            match widget:
                case ReagentRoleForm():
                    reagents.append(widget.parse_form())
                case QLineEdit():
                    info[widget.objectName()] = widget.text()
                case QComboBox():
                    info[widget.objectName()] = widget.currentText()
                case QDateEdit():
                    info[widget.objectName()] = widget.date().toPyDate()
        return info, reagents


class ReagentRoleForm(QWidget):
    """
    custom widget to add information about a new reagenttype
    """    
    def __init__(self, parent) -> None:
        super().__init__(parent)
        grid = QGridLayout()
        self.setLayout(grid)
        grid.addWidget(QLabel("Reagent Type Name"),0,0)
        # Widget to get reagent info
        self.reagent_getter = QComboBox()
        self.reagent_getter.setObjectName("rtname")
        # lookup all reagent type names from db
        lookup = ReagentRole.query()
        # logger.debug(f"Looked up ReagentType names: {lookup}")
        self.reagent_getter.addItems([item.name for item in lookup])
        self.reagent_getter.setEditable(True)
        grid.addWidget(self.reagent_getter,0,1)
        grid.addWidget(QLabel("Extension of Life (months):"),0,2)
        # NOTE: widget to get extension of life
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
        """
        Destroys this row of reagenttype from the form
        """        
        self.setParent(None)
        self.destroy()

    def parse_form(self) -> dict:
        """
        Pulls ReagentType info from the form.

        Returns:
            dict: _description_
        """        
        # logger.debug(f"Hello from {self.__class__} parser!")
        info = {}
        info['eol'] = self.eol.value()
        info['sheet'] = self.location_sheet_name.text()
        info['rtname'] = self.reagent_getter.currentText()
        widgets = [widget for widget in self.findChildren(QWidget) if widget.objectName() not in self.ignore]
        for widget in widgets:
            # logger.debug(f"Parsed widget: {widget.objectName()} of type {type(widget)} with parent {widget.parent()}")
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
                            # logger.debug(f"Adding key {key}, {sub_key} and value {widget.value()} to {info}")
                        info[key][sub_key] = widget.value()        
        return info

