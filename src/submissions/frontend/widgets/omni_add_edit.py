from datetime import date
from pprint import pformat
from typing import Any, List, Tuple
from pydantic import BaseModel
from PyQt6.QtWidgets import (
    QLabel, QDialog, QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit
)
from sqlalchemy import String, TIMESTAMP
from sqlalchemy.orm import InstrumentedAttribute, ColumnProperty
import logging

from sqlalchemy.orm.relationships import _RelationshipDeclared

from tools import Report, Result

logger = logging.getLogger(f"submissions.{__name__}")


class AddEdit(QDialog):

    def __init__(self, parent, instance: Any | None = None, manager: str = ""):
        super().__init__(parent)
        self.instance = instance
        self.object_type = instance.__class__
        self.layout = QGridLayout(self)
        logger.debug(f"Manager: {manager}")
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        fields = {key: dict(class_attr=getattr(self.object_type, key), instance_attr=getattr(self.instance, key))
                  for key in dir(self.object_type) if isinstance(getattr(self.object_type, key), InstrumentedAttribute)
                  and "id" not in key and key != manager}
        # NOTE: Move 'name' to the front
        try:
            fields = {'name': fields.pop('name'), **fields}
        except KeyError:
            pass
        logger.debug(pformat(fields, indent=4))
        height_counter = 0
        for key, field in fields.items():
            try:
                value = getattr(self.instance, key)
            except AttributeError:
                value = None
            try:
                logger.debug(f"{key} property: {type(field['class_attr'].property)}")
                # widget = EditProperty(self, key=key, column_type=field.property.expression.type,
                #                           value=getattr(self.instance, key))
                logger.debug(f"Column type: {field}, Value: {value}")
                widget = EditProperty(self, key=key, column_type=field, value=value)
            except AttributeError as e:
                logger.error(f"Problem setting widget {key}: {e}")
                continue
            if widget:
                self.layout.addWidget(widget, self.layout.rowCount(), 0)
                height_counter += 1
        self.layout.addWidget(self.buttonBox)
        self.setWindowTitle(f"Add/Edit {self.object_type.__name__}")
        self.setMinimumSize(600, 50 * height_counter)
        self.setLayout(self.layout)

    def parse_form(self) -> Tuple[BaseModel, Report]:
        report = Report()
        parsed = {result[0].strip(":"): result[1] for result in [item.parse_form() for item in self.findChildren(EditProperty)] if result[0]}
        logger.debug(parsed)
        model = self.object_type.get_pydantic_model()
        # NOTE: Hand-off to pydantic model for validation.
        # NOTE: Also, why am I not just using the toSQL method here. I could write one for contacts.
        model = model(**parsed)
        # output, result = model.toSQL()
        # report.add_result(result)
        # if len(report.results) < 1:
        #     report.add_result(Result(msg="Added new regeant.", icon="Information", owner=__name__))
        return model, report


class EditProperty(QWidget):

    def __init__(self, parent: AddEdit, key: str, column_type: Any, value):
        super().__init__(parent)
        self.name = key
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.setObjectName(f"{key}:")
        match column_type['class_attr'].property:
            case ColumnProperty():
                self.column_property_set(column_type, value=value)
            case _RelationshipDeclared():
                self.relationship_property_set(column_type, value=value)
            case _:
                logger.error(f"{column_type} not a supported type.")
                return
        self.layout.addWidget(self.widget, 0, 1, 1, 3)
        self.setLayout(self.layout)

    def relationship_property_set(self, relationship_property, value=None):
        # print(relationship_property)
        self.property_class = relationship_property['class_attr'].property.entity.class_
        self.is_list = relationship_property['class_attr'].property.uselist
        choices = [item.name for item in self.property_class.query()]
        try:
            instance_value = getattr(self.parent().instance, self.name)
        except AttributeError:
            logger.error(f"Unable to get instance {self.parent().instance} attribute: {self.name}")
            instance_value = None
        if isinstance(instance_value, list):
            instance_value = next((item.name for item in instance_value), None)
        if instance_value:
            choices.insert(0, choices.pop(choices.index(instance_value)))
        self.widget = QComboBox()
        self.widget.addItems(choices)

    def column_property_set(self, column_property, value=None):
        match column_property['class_attr'].expression.type:
            case String():
                if not value:
                    value = ""
                self.widget = QLineEdit(self)
                self.widget.setText(value)
            case TIMESTAMP():
                self.widget = QDateEdit(self, calendarPopup=True)
                if not value:
                    value = date.today()
                self.widget.setDate(value)
            case _:
                logger.error(f"{column_property} not a supported property.")
                self.widget = None
        try:
            tooltip_text = self.parent().object_type.add_edit_tooltips[self.name]
            self.widget.setToolTip(tooltip_text)
        except KeyError:
            pass

    def parse_form(self):
        try:
            check = self.widget
        except AttributeError:
            return None, None
        match self.widget:
            case QLineEdit():
                value = self.widget.text()
            case QDateEdit():
                value = self.widget.date().toPyDate()
            case QComboBox():
                value = self.widget.currentText()
                # if self.is_list:
                #     value = [self.property_class.query(name=prelim)]
                # else:
                #     value = self.property_class.query(name=prelim)
            case _:
                value = None
        return self.name, value
