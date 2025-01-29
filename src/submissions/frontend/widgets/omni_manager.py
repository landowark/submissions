"""
Provides a screen for managing all attributes of a database object.
"""
from copy import deepcopy
from pprint import pformat
from typing import Any, List
from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QLabel, QDialog,
    QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit, QMenu,
    QDoubleSpinBox, QSpinBox, QCheckBox
)
from sqlalchemy import String, TIMESTAMP, FLOAT, INTEGER, JSON, BLOB
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm.collections import InstrumentedList
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared
from pandas import DataFrame
from backend import db
import logging

from tools import check_object_in_managers
from .omni_add_edit import AddEdit
from .omni_search import SearchBox
from frontend.widgets.submission_table import pandasModel

logger = logging.getLogger(f"submissions.{__name__}")


class ManagerWindow(QDialog):
    """
    Initially this is a window to manage Organization Contacts, but hope to abstract it more later.
    """

    def __init__(self, parent, object_type: Any, extras: List[str], managers: set = set(), **kwargs):
        super().__init__(parent)
        self.object_type = self.original_type = object_type
        self.instance = None
        # self.managers = deepcopy(managers)
        self.managers = managers
        try:
            self.managers.add(self.parent().instance)
        except AttributeError:
            pass
        # logger.debug(f"Managers: {managers}")
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
        self.options = QComboBox(self)
        self.options.setObjectName("options")
        self.update_options()
        self.setLayout(self.layout)
        self.setWindowTitle(f"Manage {self.object_type.__name__} - Managers: {self.managers}")

    def update_options(self) -> None:
        """
        Changes form inputs based on sample type
        """
        # logger.debug(f"Instance: {self.instance}")
        if self.sub_class:
            self.object_type = getattr(db, self.sub_class.currentText())
        # logger.debug(f"From update options, managers: {self.managers}")
        try:
            query_kwargs = {self.parent().instance.query_alias: self.parent().instance}
        except AttributeError as e:
            # logger.debug(f"Couldn't set query kwargs due to: {e}")
            query_kwargs = {}
        # logger.debug(f"Query kwargs: {query_kwargs}")
        options = [item.name for item in self.object_type.query(**query_kwargs)]
        # logger.debug(f"self.object_type: {self.object_type}")
        if self.instance:
            try:
                inserter = options.pop(options.index(self.instance.name))
            except ValueError:
                inserter = self.instance.name
            options.insert(0, inserter)
        self.options.clear()
        self.options.addItems(options)
        self.options.setEditable(False)
        self.options.setMinimumWidth(self.minimumWidth())
        self.layout.addWidget(self.options, 1, 0, 1, 1)
        if len(options) > 0:
            self.add_button = QPushButton("Add New")
            self.layout.addWidget(self.add_button, 1, 1, 1, 1)
            self.add_button.clicked.connect(self.add_new)
        self.options.currentTextChanged.connect(self.update_data)
        # logger.debug(f"Instance: {self.instance}")
        self.update_data()

    def update_data(self) -> None:
        """
        Performs updating of widgets on first run and after options change.

        Returns:
            None
        """
        # NOTE: Remove all old widgets.
        deletes = [item for item in self.findChildren(EditProperty)] + \
                  [item for item in self.findChildren(EditRelationship)] + \
                  [item for item in self.findChildren(QDialogButtonBox)]
        for item in deletes:
            item.setParent(None)
        # logger.debug(f"Current options text lower: {self.options.currentText().lower()}")
        # NOTE: Find the instance this manager will update
        if "blank" not in self.options.currentText().lower() and self.options.currentText() != "":
            # logger.debug(f"Querying with {self.options.currentText()}")
            self.instance = self.object_type.query(name=self.options.currentText(), limit=1)
        # logger.debug(f"Instance: {self.instance}")
        if not self.instance:
            self.instance = self.object_type()
            # logger.debug(f"self.instance: {self.instance}")
        fields = {k: v for k, v in self.instance.omnigui_instance_dict.items() if
                      isinstance(v['class_attr'], InstrumentedAttribute) and k != "id"}
        for key, field in fields.items():
            try:
                value = getattr(self.instance, key)
            except AttributeError:
                value = None
            match field['class_attr'].property:
                # NOTE: ColumnProperties will be directly edited.
                case ColumnProperty():
                    # NOTE: field.property.expression.type gives db column type eg. STRING or TIMESTAMP
                    widget = EditProperty(self, key=key, column_type=field,
                                          value=value)
                # NOTE: RelationshipDeclareds will be given a list of existing related objects.
                case _RelationshipDeclared():
                    if key != "submissions":
                        # NOTE: field.comparator.entity.class_ gives the relationship class
                        widget = EditRelationship(self, key=key, entity=field['class_attr'].comparator.entity.class_,
                                                  value=value)
                    else:
                        continue
                case _:
                    continue
            if widget:
                self.layout.addWidget(widget, self.layout.rowCount(), 0, 1, 2)
        # NOTE: Add OK|Cancel to bottom of dialog.
        self.layout.addWidget(self.buttonBox, self.layout.rowCount(), 0, 1, 2)


    def add_new_relation(self, field: str):
        pass


    def parse_form(self) -> Any:
        """
        Returns the instance associated with this window.

        Returns:
            Any: The instance with updated fields.
        """
        # TODO: Need Relationship property here too?
        results = [item.parse_form() for item in self.findChildren(EditProperty)]
        for result in results:
            # logger.debug(f"Incoming result: {result}")
            setattr(self.instance, result['field'], result['value'])
            # logger.debug(f"Set result: {getattr(self.instance, result['field'])}")
        results = [item.parse_form() for item in self.findChildren(EditRelationship)]
        for result in results:
            logger.debug(f"Incoming result: {result}")
            if not getattr(self.instance, result['field']):
                setattr(self.instance, result['field'], result['value'])
            logger.debug(f"Set result: {getattr(self.instance, result['field'])}")
        logger.debug(f"Instance coming from parsed form: {self.instance.__dict__}")
        return self.instance

    def add_new(self):
        # dlg = AddEdit(parent=self, instance=self.object_type(), managers=self.managers)
        # if dlg.exec():
        #     new_pyd = dlg.parse_form()
        #     new_instance = new_pyd.to_sql()
        #     # new_instance.save()
        #     logger.debug(f"New instance: {new_instance}")
        #     self.instance = new_instance
        #     self.update_options()
        new_instance = self.object_type()
        self.instance = new_instance
        self.update_options()


class EditProperty(QWidget):

    def __init__(self, parent: ManagerWindow, key: str, column_type: Any, value):
        super().__init__(parent)
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.setObjectName(key)
        # logger.debug(f"Column type: {column_type}")
        match column_type['class_attr'].property.expression.type:
            case String():
                self.widget = QLineEdit(self)
                self.widget.setText(value)
            case INTEGER():
                if isinstance(column_type['instance_attr'], bool):
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
                self.widget.setMaximum(999.99)
                self.widget.setValue(value)
            case TIMESTAMP():
                self.widget = QDateEdit(self)
                self.widget.setDate(value)
            case JSON():
                self.widget = QLabel("JSON Under construction")
            case BLOB():
                self.widget = QLabel("BLOB Under construction")
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
            case QSpinBox() | QDoubleSpinBox():
                value = self.widget.value()
            case QCheckBox():
                value = self.widget.isChecked()
            case _:
                value = None
        return dict(field=self.objectName(), value=value)


class EditRelationship(QWidget):

    def __init__(self, parent, key: str, entity: Any, value):
        super().__init__(parent)
        self.entity = entity  #: The class of interest
        self.setParent(parent)
        # logger.debug(f"Edit relationship entity: {self.entity}")
        self.label = QLabel(key.title().replace("_", " "))
        self.setObjectName(key) #: key is the name of the relationship this represents
        self.relationship = getattr(self.parent().instance.__class__, key)
        # logger.debug(f"self.relationship: {self.relationship}")
        # logger.debug(f"Relationship uses list: {self.relationship.property.uselist}")
        self.data = value
        # logger.debug(f"Data for edit relationship: {self.data}")
        self.widget = QTableView()
        self.set_data()
        self.add_button = QPushButton("Add New")
        self.add_button.clicked.connect(self.add_new)
        self.existing_button = QPushButton("Add Existing")
        self.existing_button.clicked.connect(self.add_existing)
        # self.existing_button.setEnabled(self.entity.level == 1)
        if not self.relationship.property.uselist and len(self.data) >= 1:
            self.add_button.setEnabled(False)
            self.existing_button.setEnabled(False)
        checked_manager = check_object_in_managers(self.parent().managers, self.objectName())
        logger.debug(f"Checked manager for check: {checked_manager}")
        if checked_manager:
            self.widget.setEnabled(False)
            self.add_button.setEnabled(False)
            self.existing_button.setEnabled(False)
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 5)
        self.layout.addWidget(self.widget, 1, 0, 1, 8)
        self.layout.addWidget(self.add_button, 0, 6, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.existing_button, 0, 7, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(self.layout)
        # self.set_data()

    def parse_row(self, x):
        context = {item: x.sibling(x.row(), self.data.columns.get_loc(item)).data() for item in self.data.columns}
        try:
            object = self.entity.query(**context)
        except KeyError:
            object = None
        self.widget.doubleClicked.disconnect()
        self.add_edit(instance=object)

    def add_new(self, instance: Any = None):
        # NOTE: if an existing instance is not being edited, create a new instance
        if not instance:
            instance = self.entity()
        managers = self.parent().managers
        # logger.debug(f"Managers going into add new: {managers}")
        dlg = ManagerWindow(self.parent(), object_type=instance.__class__, extras=[], managers=managers)
        if dlg.exec():
            new_instance = dlg.parse_form()
            # logger.debug(f"New instance before transformation attempt: {new_instance}")
            # try:
            #     new_instance = new_instance.to_sql()
            # except AttributeError as e:
            #     logger.error(f"Couldn't convert {new_instance} to sql due to {e}")
            # # logger.debug(f"New instance after transformation attempt: {new_instance.__dict__}")
            # setattr(self.parent().instance, self.objectName(), new_instance)
            # # logger.debug(f"Parent instance after insert: {getattr(self.parent().instance, self.objectName())}")
            # # NOTE: Saving currently disabled
            # self.parent().instance.save()
            # return new_instance
        self.parent().update_data()

    def add_existing(self):
        dlg = SearchBox(self, object_type=self.entity, returnable=True, extras=[])
        if dlg.exec():
            rows = dlg.return_selected_rows()
            for row in rows:
                # logger.debug(f"Querying with {row}")
                instance = self.entity.query(**row)
                # logger.debug(f"Queried instance: {instance}")
                # logger.debug(f"Checking field type: {self.objectName()}")
                # addition = getattr(self.parent().instance, self.objectName())
                # logger.debug(f"Instance object: {addition}")
                # NOTE: Saving currently disabled
                # if self.relationship.property.uselist:
                #     addition.append(instance)
                # else:
                #     addition = instance
                setattr(self.parent().instance, self.objectName(), instance)
                # self.parent().instance.save()
            self.parent().update_data()
            #     yield instance

    def set_choices(self) -> None:
        pass

    def set_data(self) -> None:
        """
        sets data in model
        """
        # logger.debug(self.data)
        if not isinstance(self.data, list):
            if self.data is not None:
                self.data = [self.data]
            else:
                self.data = []
        checked_manager = check_object_in_managers(self.parent().managers, self.objectName())
        # logger.debug(f"Returned checked_manager: {checked_manager}")
        if checked_manager is not None:
            if not self.data:
                self.data = [checked_manager]
                # setattr(self.parent().instance, self.objectName(), checked_manager)
        # logger.debug(f"Data: {self.data}")
        try:
            records = [{k: v['instance_attr'] for k, v in item.omnigui_instance_dict.items()} for item in self.data]
        except AttributeError:
            records = []
        # logger.debug(f"Records: {records}")
        self.df = DataFrame.from_records(records)
        try:
            self.columns_of_interest = [dict(name=item, column=self.df.columns.get_loc(item)) for item in self.extras]
        except (KeyError, AttributeError):
            self.columns_of_interest = []
        try:
            self.df['id'] = self.df['id'].apply(str)
            self.df['id'] = self.df['id'].str.zfill(4)
        except KeyError as e:
            logger.error(f"Could not alter id to string due to KeyError: {e}")
        proxy_model = QSortFilterProxyModel()
        proxy_model.setSourceModel(pandasModel(self.df))
        self.widget.setModel(proxy_model)
        self.widget.resizeColumnsToContents()
        self.widget.resizeRowsToContents()
        self.widget.setSortingEnabled(True)
        self.widget.doubleClicked.connect(self.parse_row)

    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        print(self.widget.isEnabled())
        if not self.widget.isEnabled():
            logger.warning(f"{self.objectName()} is disabled.")
            return
        id = self.widget.selectionModel().currentIndex()
        # NOTE: the overly complicated {column_name: row_value} dictionary construction
        row_data = {self.df.columns[column]: self.widget.model().index(id.row(), column).data() for column in
                    range(self.widget.model().columnCount())}
        object = self.entity.query(**row_data)
        if isinstance(object, list):
            object = object[0]
        # logger.debug(object)
        self.menu = QMenu(self)
        try:
            action = QAction(f"Remove {object.name}", self)
        except AttributeError:
            action = QAction(f"Remove object", self)
        action.triggered.connect(lambda: self.remove_item(object=object))
        self.menu.addAction(action)
        self.menu.popup(QCursor.pos())

    def remove_item(self, object):
        editor = getattr(self.parent().instance, self.objectName().lower())
        editor.remove(object)
        self.parent().instance.save()
        self.parent().update_data()

    def parse_form(self):
        return dict(field=self.objectName(), value=self.data)
