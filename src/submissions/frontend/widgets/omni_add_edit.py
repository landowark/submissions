from datetime import date
from typing import Any

from PyQt6.QtWidgets import (
    QLabel, QDialog, QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit
)
from sqlalchemy import String, TIMESTAMP
from sqlalchemy.orm import InstrumentedAttribute
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class AddEdit(QDialog):

    def __init__(self, parent, instance: Any|None=None):
        super().__init__(parent)
        self.instance = instance
        self.object_type = instance.__class__
        self.layout = QGridLayout(self)

        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        # fields = {k: v for k, v in self.object_type.__dict__.items() if
        #           isinstance(v, InstrumentedAttribute) and k != "id"}
        fields = {k: v for k, v in self.object_type.__dict__.items() if k != "id"}
        for key, field in fields.items():
            logger.debug(f"")
            try:
                widget = EditProperty(self, key=key, column_type=field.property.expression.type,
                                          value=getattr(self.instance, key))
            except AttributeError as e:
                logger.error(f"Problem setting widget {key}: {e}")
                continue
            self.layout.addWidget(widget, self.layout.rowCount(), 0)
        self.layout.addWidget(self.buttonBox)
        self.setWindowTitle(f"Add/Edit {self.object_type.__name__}")
        self.setMinimumSize(600, 50 * len(fields))
        self.setLayout(self.layout)

    def parse_form(self):
        results = {result[0]:result[1] for result in [item.parse_form() for item in self.findChildren(EditProperty)]}
        # logger.debug(results)
        model = self.object_type.get_pydantic_model()
        model = model(**results)
        try:
            extras = list(model.model_extra.keys())
        except AttributeError:
            extras = []
        fields = list(model.model_fields.keys()) + extras
        for field in fields:
            # logger.debug(result)
            self.instance.__setattr__(field, model.__getattribute__(field))
        return self.instance


class EditProperty(QWidget):

    def __init__(self, parent: AddEdit, key: str, column_type: Any, value):
        super().__init__(parent)
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.setObjectName(key)
        match column_type:
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
                logger.error(f"{column_type} not a supported type.")
                self.widget = None
                return
        self.layout.addWidget(self.widget, 0, 1, 1, 3)
        self.setLayout(self.layout)

    def parse_form(self):
        match self.widget:
            case QLineEdit():
                value = self.widget.text()
            case QDateEdit():
                value = self.widget.date()
            case _:
                value = None
        return self.objectName(), value




