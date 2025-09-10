"""
A widget to handle adding/updating any database object.
"""
from datetime import date
from pprint import pformat
from typing import Any, Tuple, List
from pydantic import BaseModel
from PyQt6.QtWidgets import (
    QLabel, QDialog, QWidget, QLineEdit, QGridLayout, QComboBox, QDialogButtonBox, QDateEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox
)
from sqlalchemy import String, TIMESTAMP, INTEGER, FLOAT, JSON, BLOB
from sqlalchemy.orm import ColumnProperty
import logging
from sqlalchemy.orm.relationships import _RelationshipDeclared
from backend.db.models import BaseClass
from backend.validators.pydant import PydBaseClass
from tools import Report, report_result

logger = logging.getLogger(f"submissions.{__name__}")


class AddEdit(QDialog):

    def __init__(self, parent, instance: Any | None = None, managers: set = set(), disabled: List[str] = []):
        super().__init__(parent)
        logger.debug(f"Disable = {disabled}")
        self.instance = instance
        self.object_type = instance.__class__
        self.managers = managers
        self.layout = QGridLayout(self)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        fields = {k: v for k, v in self.instance.omnigui_instance_dict.items() if "id" not in k}
        logger.debug(f"Fields: {pformat(fields)}")
        # NOTE: Move 'name' to the front
        try:
            fields = {'name': fields.pop('name'), **fields}
        except KeyError:
            pass
        height_counter = 0
        for key, field in fields.items():
            disable = key in disabled
            try:
                value = getattr(self.instance, key)
            except AttributeError:
                value = None
            try:
                widget = EditProperty(self, key=key, column_type=field, value=value, disable=disable)
            except AttributeError as e:
                logger.error(f"Problem setting widget {key}: {e}")
                continue
            if widget:
                self.layout.addWidget(widget, self.layout.rowCount(), 0)
                height_counter += 1
        self.layout.addWidget(self.buttonBox)
        self.setWindowTitle(f"Add/Edit {self.object_type.__name__}")# - Manager: {self.managers}")
        self.setMinimumSize(600, 50 * height_counter)
        self.setLayout(self.layout)

    @report_result
    def parse_form(self) -> Tuple[BaseModel, Report]:
        report = Report()
        parsed = {result[0].strip(":"): result[1] for result in
                  [item.parse_form() for item in self.findChildren(EditProperty)] if result[0]}
        model = self.object_type.pydantic_model
        if model.__name__ == "PydElastic":
            parsed['instance'] = self.instance
        # NOTE: Hand-off to pydantic model for validation.
        # NOTE: Also, why am I not just using the toSQL method here. I could write one for contact.
        model = model(**parsed)
        return model, report


class EditProperty(QWidget):

    def __init__(self, parent: AddEdit, key: str, column_type: Any, value, disable: bool):
        super().__init__(parent)
        logger.debug(f"Widget column type for {key}: {column_type}")
        self.name = key
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.setObjectName(key)
        try:
            self.property_class = column_type['class_attr'].property.entity.class_
        except AttributeError:
            self.property_class = None
        logger.debug(f"Property class: {self.property_class}")
        try:
            self.is_list = column_type['class_attr'].property.uselist
        except AttributeError:
            self.is_list = False
        match column_type['class_attr'].property:
            case ColumnProperty():
                self.column_property_set(column_type, value=value)
            case _RelationshipDeclared():
                try:
                    check = self.property_class.skip_on_edit
                except AttributeError:
                    check = False
                if not check:
                    self.relationship_property_set(column_type, value=value)
                else:
                    return
            case _:
                logger.error(f"{column_type} not a supported type.")
                return
        self.widget.setDisabled(disable)
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.layout.addWidget(self.widget, 0, 1, 1, 3)
        self.setLayout(self.layout)

    def relationship_property_set(self, relationship, value=None):
        self.widget = QComboBox()
        for manager in self.parent().managers:
            if self.name in manager.aliases:
                choices = [manager.name]
                self.widget.setEnabled(False)
                break
        else:
            choices = [""] + [item.name for item in self.property_class.query()]
        try:
            instance_value = getattr(self.parent().instance, self.objectName())
        except AttributeError:
            logger.error(f"Unable to get instance {self.parent().instance} attribute: {self.objectName()}")
            instance_value = None
        # NOTE: get the value for the current instance and move it to the front.
        if isinstance(instance_value, list):
            instance_value = next((item.name for item in instance_value), None)
        if instance_value:
            match instance_value:
                case x if issubclass(instance_value.__class__, BaseClass):
                    instance_value = instance_value.name
                case x if issubclass(instance_value.__class__, PydBaseClass):
                    instance_value = instance_value.name
                case _:
                    pass
            choices.insert(0, choices.pop(choices.index(instance_value)))
        self.widget.addItems(choices)

    def column_property_set(self, column_property, value=None):
        match column_property['class_attr'].expression.type:
            case String():
                if value is None:
                    value = ""
                self.widget = QLineEdit(self)
                self.widget.setText(value)
            case INTEGER():
                if isinstance(column_property['instance_attr'], bool):
                    self.widget = QCheckBox()
                    self.widget.setChecked(value)
                else:
                    if value is None:
                        value = 1
                    self.widget = QSpinBox()
                    self.widget.setValue(value)
            case FLOAT():
                if not value:
                    value = 1.0
                self.widget = QDoubleSpinBox()
                self.widget.setValue(value)
            case TIMESTAMP():
                self.widget = QDateEdit(self, calendarPopup=True)
                if not value:
                    value = date.today()
                self.widget.setDate(value)
            case JSON():
                self.widget = QLabel("JSON Under construction")
            case BLOB():
                self.widget = QLabel("BLOB Under construction")
            case _:
                logger.error(f"{column_property} not a supported property.")
                self.widget = None
        try:
            tooltip_text = self.parent().object_type.add_edit_tooltips[self.objectName()]
            self.widget.setToolTip(tooltip_text)
        except KeyError:
            pass

    def parse_form(self):
        # NOTE: Make sure there's a widget.
        try:
            check = self.widget
        except AttributeError:
            return None, None
        match check:
            case QLineEdit():
                value = self.widget.text()
            case QDateEdit():
                value = self.widget.date().toPyDate()
            case QComboBox():
                value = self.widget.currentText()
            case QSpinBox() | QDoubleSpinBox():
                value = self.widget.value()
            case QCheckBox():
                value = self.widget.isChecked()
            case _:
                value = None
        return self.objectName(), value
