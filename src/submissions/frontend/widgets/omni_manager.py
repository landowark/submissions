from typing import Any, List
from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtWidgets import (
    QLabel, QDialog,
    QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit
)
from sqlalchemy import String, TIMESTAMP
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared
from pandas import DataFrame
from backend import db
import logging
from .omni_add_edit import AddEdit
from .omni_search import SearchBox

from frontend.widgets.submission_table import pandasModel

logger = logging.getLogger(f"submissions.{__name__}")


class ManagerWindow(QDialog):
    """
    Initially this is a window to manage Organization Contacts, but hope to abstract it more later.
    """

    def __init__(self, parent, object_type: Any, extras: List[str], **kwargs):
        super().__init__(parent)
        self.object_type = self.original_type = object_type
        self.instance = None
        self.extras = extras
        self.context = kwargs
        self.layout = QGridLayout(self)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setMinimumSize(600, 600)
        sub_classes = ["Any"] + [cls.__name__ for cls in self.object_type.__subclasses__()]
        if len(sub_classes) > 1:
            self.sub_class = QComboBox(self)
            self.sub_class.setObjectName("sub_class")
            self.sub_class.addItems(sub_classes)
            self.sub_class.currentTextChanged.connect(self.update_options)
            self.sub_class.setEditable(False)
            self.sub_class.setMinimumWidth(self.minimumWidth())
            self.layout.addWidget(self.sub_class, 0, 0)
        else:
            self.sub_class = None
        # self.layout.addWidget(self.buttonBox, self.layout.rowCount(), 0)
        self.options = QComboBox(self)
        self.options.setObjectName("options")
        self.update_options()
        self.setLayout(self.layout)
        self.setWindowTitle(f"Manage {self.object_type.__name__}")

    def update_options(self):
        """
        Changes form inputs based on sample type
        """

        if self.sub_class:
            self.object_type = getattr(db, self.sub_class.currentText())
        options = [item.name for item in self.object_type.query()]
        self.options.clear()
        self.options.addItems(options)
        self.options.setEditable(False)
        self.options.setMinimumWidth(self.minimumWidth())
        self.layout.addWidget(self.options, 1, 0, 1, 1)
        self.add_button = QPushButton("Add New")
        self.layout.addWidget(self.add_button, 1, 1, 1, 1)
        self.options.currentTextChanged.connect(self.update_data)
        self.add_button.clicked.connect(self.add_new)
        self.update_data()

    def update_data(self):
        deletes = [item for item in self.findChildren(EditProperty)] + \
                  [item for item in self.findChildren(EditRelationship)] + \
                  [item for item in self.findChildren(QDialogButtonBox)]
        for item in deletes:
            item.setParent(None)
        self.instance = self.object_type.query(name=self.options.currentText())
        fields = {k: v for k, v in self.object_type.__dict__.items() if
                  isinstance(v, InstrumentedAttribute) and k != "id"}
        for key, field in fields.items():
            # logger.debug(f"Key: {key}, Value: {field}")
            match field.property:
                case ColumnProperty():
                    widget = EditProperty(self, key=key, column_type=field.property.expression.type,
                                          value=getattr(self.instance, key))
                case _RelationshipDeclared():
                    if key != "submissions":
                        widget = EditRelationship(self, key=key, entity=field.comparator.entity.class_,
                                                  value=getattr(self.instance, key))
                    else:
                        continue
                case _:
                    continue
            if widget:
                self.layout.addWidget(widget, self.layout.rowCount(), 0, 1, 2)
        self.layout.addWidget(self.buttonBox, self.layout.rowCount(), 0, 1, 2)

    def parse_form(self):
        results = [item.parse_form() for item in self.findChildren(EditProperty)]
        # logger.debug(results)
        for result in results:
            # logger.debug(result)
            self.instance.__setattr__(result[0], result[1])
        return self.instance

    def add_new(self):
        dlg = AddEdit(parent=self, instance=self.object_type(), manager=self.object_type.__name__.lower())
        if dlg.exec():
            new_instance = dlg.parse_form()
            # logger.debug(new_instance.__dict__)
            new_instance.save()
            self.update_options()


class EditProperty(QWidget):

    def __init__(self, parent: ManagerWindow, key: str, column_type: Any, value):
        super().__init__(parent)
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        match column_type:
            case String():
                self.widget = QLineEdit(self)
                self.widget.setText(value)
            case TIMESTAMP():
                self.widget = QDateEdit(self)
                self.widget.setDate(value)
            case _:
                self.widget = None
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


class EditRelationship(QWidget):

    def __init__(self, parent, key: str, entity: Any, value):
        super().__init__(parent)
        self.entity = entity
        self.data = value
        self.label = QLabel(key.title().replace("_", " "))
        self.setObjectName(key)
        self.table = QTableView()
        self.add_button = QPushButton("Add New")
        self.add_button.clicked.connect(self.add_new)
        self.existing_button = QPushButton("Add Existing")
        self.existing_button.clicked.connect(self.add_existing)
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 5)
        self.layout.addWidget(self.table, 1, 0, 1, 8)
        self.layout.addWidget(self.add_button, 0, 6, 1, 1,  alignment=Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.existing_button, 0, 7, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(self.layout)
        self.set_data()

    def parse_row(self, x):
        context = {item: x.sibling(x.row(), self.data.columns.get_loc(item)).data() for item in self.data.columns}
        try:
            object = self.entity.query(**context)
        except KeyError:
            object = None
        # logger.debug(object)
        self.table.doubleClicked.disconnect()
        self.add_edit(instance=object)

    def add_new(self, instance: Any = None):
        if not instance:
            instance = self.entity()
        dlg = AddEdit(self, instance=instance, manager=self.parent().object_type.__name__.lower())
        if dlg.exec():
            new_instance = dlg.parse_form()
            # logger.debug(new_instance.__dict__)
            addition = getattr(self.parent().instance, self.objectName())
            if isinstance(addition, InstrumentedList):
                addition.append(new_instance)
            self.parent().instance.save()

        self.parent().update_data()

    def add_existing(self):
        dlg = SearchBox(self, object_type=self.entity, returnable=True, extras=[])
        if dlg.exec():
            rows = dlg.return_selected_rows()
            for row in rows:
                instance = self.entity.query(**row)
                addition = getattr(self.parent().instance, self.objectName())
                if isinstance(addition, InstrumentedList):
                    addition.append(instance)
                self.parent().instance.save()
            self.parent().update_data()

    def set_data(self) -> None:
        """
        sets data in model
        """
        # logger.debug(self.data)
        self.data = DataFrame.from_records([item.to_dict() for item in self.data])
        try:
            self.columns_of_interest = [dict(name=item, column=self.data.columns.get_loc(item)) for item in self.extras]
        except (KeyError, AttributeError):
            self.columns_of_interest = []
        # try:
        #     self.data['id'] = self.data['id'].apply(str)
        #     self.data['id'] = self.data['id'].str.zfill(3)
        # except (TypeError, KeyError) as e:
        #     logger.error(f"Couldn't format id string: {e}")
        proxy_model = QSortFilterProxyModel()
        proxy_model.setSourceModel(pandasModel(self.data))
        self.table.setModel(proxy_model)
        self.table.doubleClicked.connect(self.parse_row)
