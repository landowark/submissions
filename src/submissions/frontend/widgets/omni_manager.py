"""
Provides a screen for managing all attributes of a database object.
"""
import json, logging
from pprint import pformat
from typing import Any, List, Literal
from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QLabel, QDialog,
    QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit, QMenu,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit, QVBoxLayout, QHBoxLayout
)
from sqlalchemy import String, TIMESTAMP, FLOAT, INTEGER, JSON, BLOB
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.orm.properties import ColumnProperty
from sqlalchemy.orm.relationships import _RelationshipDeclared
from pandas import DataFrame
from backend import db
from tools import check_object_in_manager
from .omni_search import SearchBox
from frontend.widgets.submission_table import pandasModel

logger = logging.getLogger(f"submissions.{__name__}")


class ManagerWindow(QDialog):
    """
    Initially this is a window to manage Organization Contacts, but hope to abstract it more later.
    """

    def __init__(self, parent,
                 object_type: Any,
                 extras: List[str],
                 manager: Any | None = None,
                 add_edit: Literal['add', 'edit'] = 'edit',
                 **kwargs):
        super().__init__(parent)
        self.class_object = self.original_type = object_type
        self.add_edit = add_edit
        # NOTE: Should I pass in an instance?
        self.instance = None
        if manager is None:
            try:
                self.manager = self.parent().instance
            except AttributeError:
                self.manager = None
        else:
            self.manager = manager
        # logger.debug(f"Managers: {managers}")
        self.extras = extras
        self.context = kwargs
        self.layout = QGridLayout(self)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.setMinimumSize(600, 600)
        sub_classes = ["Any"] + [cls.__name__ for cls in self.class_object.__subclasses__()]
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
        if self.add_edit == "edit":
            self.options = QComboBox(self)
            self.options.setObjectName("options")
            self.update_options()
        else:
            self.update_data(initial=True)
        self.setLayout(self.layout)
        self.setWindowTitle(f"Manage {self.class_object.__name__} - Manager: {self.manager}")

    def update_options(self) -> None:
        """
        Changes form inputs based on sample type
        """
        # logger.debug(f"Instance: {self.instance}")
        if self.sub_class:
            self.class_object = getattr(db, self.sub_class.currentText())
        # logger.debug(f"From update options, managers: {self.managers}")
        try:
            query_kwargs = {self.parent().instance.query_alias: self.parent().instance}
        except AttributeError as e:
            # logger.debug(f"Couldn't set query kwargs due to: {e}")
            query_kwargs = {}
        # logger.debug(f"Query kwargs: {query_kwargs}")
        options = [item.name for item in self.class_object.query(**query_kwargs)]
        # logger.debug(f"self.class_object: {self.class_object}")
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
        self.add_button = QPushButton("Add New")
        self.layout.addWidget(self.add_button, 1, 1, 1, 1)
        self.add_button.clicked.connect(self.add_new)
        self.options.currentTextChanged.connect(self.update_data)
        # logger.debug(f"Instance: {self.instance}")
        self.update_data()

    def update_data(self, initial: bool = False) -> None:
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
        if self.add_edit == "edit" and initial:
            # logger.debug(f"Querying with {self.options.currentText()}")
            self.instance = self.class_object.query(name=self.options.currentText(), limit=1)
        # logger.debug(f"Instance: {self.instance}")
        if not self.instance:
            self.instance = self.class_object()
            # logger.debug(f"self.instance: {self.instance}")
        fields = self.instance.omnigui_instance_dict
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
                        # NOTE: field.comparator.class_object.class_ gives the relationship class
                        widget = EditRelationship(self, key=key, class_object=field['class_attr'].comparator.entity.class_,
                                                  value=value)
                    else:
                        continue
                case _:
                    continue
            if widget:
                self.layout.addWidget(widget, self.layout.rowCount(), 0, 1, 2)
        # NOTE: Add OK|Cancel to bottom of dialog.
        self.layout.addWidget(self.buttonBox, self.layout.rowCount(), 0, 1, 2)

    def parse_form(self) -> Any:
        """
        Returns the instance associated with this window.

        Returns:
            Any: The instance with updated fields.
        """
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
        new_instance = self.class_object()
        self.instance = new_instance
        self.update_options()

    def add_to_json(self, caller_child=None):
        try:
            name = caller_child.objectName()
        except AttributeError:
            name = "No Caller"
        jsonedit = JsonEditScreen(parent=self, key=name)
        if jsonedit.exec():
            data = jsonedit.parse_form()
            logger.debug(f"Data: {pformat(data)}")
            current_value = getattr(self.instance, name)
            if isinstance(jsonedit.json_field, dict):
                value = data
            elif isinstance(jsonedit.json_field, list):
                if isinstance(data, list):
                    value = current_value + data
                else:
                    value = current_value + [data]
            setattr(self.instance, name, value)

    def toggle_textedit(self, caller_child=None):
        already_exists = self.findChildren(LargeTextEdit)
        if not already_exists:
            try:
                name = caller_child.objectName()
            except AttributeError:
                name = "No Caller"
            logger.debug(f"Name: {name}, instance: {self.instance}")
            textedit = LargeTextEdit(parent=self, key=name)
            self.layout.addWidget(textedit, 1, self.layout.columnCount(), self.layout.rowCount() - 1, 1)
            data = getattr(self.instance, name)
            logger.debug(f"Data: {data}")
            data = json.dumps(data, indent=4)
            textedit.widget.setText(data)
        else:
            for item in already_exists:
                item.setParent(None)
                item.destroy()


class EditProperty(QWidget):

    def __init__(self, parent: ManagerWindow, key: str, column_type: Any, value):
        super().__init__(parent)
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.setObjectName(key)
        logger.debug(f"Column type for {key}: {column_type['class_attr'].property.expression.type}")
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
                        value = 0
                    self.widget = QSpinBox()
                    self.widget.setMaximum(999)
                    self.widget.setValue(value)
            case FLOAT():
                if not value:
                    value = 0.0
                self.widget = QDoubleSpinBox()
                self.widget.setMaximum(999.99)
                self.widget.setValue(value)
            case TIMESTAMP():
                self.widget = QDateEdit(self)
                self.widget.setDate(value)
            case JSON():
                self.widget = JsonEditButton(parent=self, key=key)
                self.widget.viewButton.clicked.connect(lambda: self.parent().toggle_textedit(self.widget))
                self.widget.addButton.clicked.connect(lambda: self.parent().add_to_json(self.widget))
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

    def __init__(self, parent, key: str, class_object: Any, value):
        super().__init__(parent)
        self.class_object = class_object  #: The class of interest
        self.setParent(parent)
        # logger.debug(f"Edit relationship class_object: {self.class_object}")
        self.label = QLabel(key.title().replace("_", " "))
        self.setObjectName(key)  #: key is the name of the relationship this represents
        self.relationship = getattr(self.parent().instance.__class__,
                                    key)  #: relationship object for type differentiation
        # logger.debug(f"self.relationship: {self.relationship}")
        # logger.debug(f"Relationship uses list: {self.relationship.property.uselist}")
        # NOTE: value is a database object in this case.
        # logger.debug(f"Data for edit relationship: {self.data}")
        self.widget = QTableView()
        self.add_button = QPushButton("Add New")
        self.add_button.clicked.connect(self.add_new)
        self.existing_button = QPushButton("Add Existing")
        self.existing_button.clicked.connect(self.add_existing)
        # self.existing_button.setEnabled(self.class_object.level == 1)
        if not isinstance(value, list):
            if value is not None:
                value = [value]
            else:
                value = []
        self.data = value
        checked_manager, is_primary = check_object_in_manager(self.parent().manager, self.objectName())
        if checked_manager:
            logger.debug(f"Checked manager for {self.objectName()}: {checked_manager}")
            logger.debug(f"Omni will inherit: {self.class_object.omni_inheritable} from {self.parent().class_object}")
            if checked_manager is not None and not self.data and self.objectName() in self.parent().class_object.omni_inheritable:
                logger.debug(f"Setting {checked_manager} in self.data")
                self.data = [checked_manager]
            if not self.relationship.property.uselist:
                self.add_button.setEnabled(False)
                self.existing_button.setEnabled(False)
                if is_primary:
                    self.widget.setEnabled(False)
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 5)
        self.layout.addWidget(self.widget, 1, 0, 1, 8)
        self.layout.addWidget(self.add_button, 0, 6, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.existing_button, 0, 7, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(self.layout)
        self.set_data()

    def update_buttons(self):
        if not self.relationship.property.uselist and len(self.data) >= 1:
            logger.debug(f"Property {self.relationship} doesn't use list and data is of length: {len(self.data)}")
            self.add_button.setEnabled(False)
            self.existing_button.setEnabled(False)
        else:
            self.add_button.setEnabled(True)
            self.existing_button.setEnabled(True)

    def parse_row(self, x):
        context = {item: x.sibling(x.row(), self.df.columns.get_loc(item)).data() for item in self.df.columns}
        try:
            object = self.class_object.query(**context)
        except KeyError:
            object = None
        self.widget.doubleClicked.disconnect()
        self.add_edit(instance=object)

    def add_new(self, instance: Any = None):
        # NOTE: if an existing instance is not being edited, create a new instance
        if not instance:
            instance = self.class_object()
        manager = self.parent().manager
        # logger.debug(f"Managers going into add new: {managers}")
        dlg = ManagerWindow(self.parent(), object_type=instance.__class__, extras=[], manager=manager, add_edit="add")
        if dlg.exec():
            new_instance = dlg.parse_form()
            # NOTE: My custom __setattr__ should take care of any list problems.
            self.parent().instance.__setattr__(self.objectName(), new_instance)
            self.parent().update_data()

    def add_existing(self):
        dlg = SearchBox(self, object_type=self.class_object, returnable=True, extras=[])
        if dlg.exec():
            rows = dlg.return_selected_rows()
            for row in rows:
                # logger.debug(f"Querying with {row}")
                instance = self.class_object.query(**row)
                # NOTE: My custom __setattr__ should take care of any list problems.
                self.parent().instance.__setattr__(self.objectName(), instance)
                self.parent().update_data()

    def set_data(self) -> None:
        """
        sets data in model
        """
        logger.debug(f"Self.data: {self.data}")
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
        self.update_buttons()

    def contextMenuEvent(self, event):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        if not self.widget.isEnabled():
            logger.warning(f"{self.objectName()} is disabled.")
            return
        id = self.widget.selectionModel().currentIndex()
        # NOTE: the overly complicated {column_name: row_value} dictionary construction
        row_data = {self.df.columns[column]: self.widget.model().index(id.row(), column).data() for column in
                    range(self.widget.model().columnCount())}
        logger.debug(f"Row data: {row_data}")
        logger.debug(f"Attempting to grab {self.objectName()} from {self.parent().instance}")
        object = getattr(self.parent().instance, self.objectName())
        if isinstance(object, list):
            object = next((item for item in object if item.check_all_attributes(attributes=row_data)), None)
        logger.debug(f"Object of interest: {object}")
        # logger.debug(object)
        self.menu = QMenu(self)
        try:
            remove_action = QAction(f"Remove {object.name}", self)
        except AttributeError:
            remove_action = QAction(f"Remove object", self)
        remove_action.triggered.connect(lambda: self.remove_item(object=object))
        self.menu.addAction(remove_action)
        try:
            edit_action = QAction(f"Edit {object.name}", self)
        except AttributeError:
            edit_action = QAction(f"Edit object", self)
        edit_action.triggered.connect(lambda: self.add_new(instance=object))
        self.menu.addAction(edit_action)
        self.menu.popup(QCursor.pos())

    def remove_item(self, object):
        logger.debug(f"Attempting to remove {object} from {self.parent().instance.__dict__}")
        editor = getattr(self.parent().instance, self.objectName().lower())
        logger.debug(f"Editor: {editor}")
        if object == self.parent().manager:
            logger.error(f"Can't remove manager object.")
            return
        try:
            self.data.remove(object)
        except (AttributeError, ValueError) as e:
            logger.error(f"Could remove object from self.data due to: {e}")
            self.data = []
        try:
            logger.debug(f"Using remove technique")
            editor.remove(object)
        except AttributeError as e:
            logger.error(f"Remove failed using set to None for {self.objectName().lower()}.")
            setattr(self.parent().instance, self.objectName().lower(), None)
        except ValueError as e:
            logger.error(f"Remove failed for {self.objectName().lower()} due to {e}.")
        self.parent().instance.save()
        self.set_data()

    def parse_form(self):
        return dict(field=self.objectName(), value=self.data)


class JsonEditButton(QWidget):

    def __init__(self, parent, key: str):
        super().__init__(parent)
        self.setParent(parent)
        self.setObjectName(key)
        self.addButton = QPushButton("Add Entry", parent=self)
        self.viewButton = QPushButton("View >>>", parent=self)
        self.layout = QGridLayout()
        self.layout.addWidget(self.addButton, 0, 0)
        self.layout.addWidget(self.viewButton, 0, 1)
        self.setLayout(self.layout)


class JsonEditScreen(QDialog):

    def __init__(self, parent, key: str):
        super().__init__(parent)
        self.class_obj = parent.class_object
        self.layout = QGridLayout()
        self.setWindowTitle(key)
        self.json_field = self.class_obj.json_edit_fields
        match self.json_field:
            case dict():
                for key, value in self.json_field.items():
                    logger.debug(f"Key: {key}, Value: {value}")
                    row = self.layout.rowCount()
                    self.layout.addWidget(QLabel(key), row, 0)
                    match value:
                        case "int":
                            self.widget = QSpinBox()
                        case "str":
                            self.widget = QLineEdit()
                        case dict():
                            self.widget = DictionaryJsonSubEdit(parent=self, key=key, dic=value)
                        case _:
                            continue
                    self.widget.setObjectName(key)
                    self.layout.addWidget(self.widget, row, 1)
        QBtn = QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox, self.layout.rowCount(), 0, 1, 2)
        self.setLayout(self.layout)

    def parse_form(self):
        widgets = [item for item in self.findChildren(QWidget) if item.objectName() in self.json_field.keys()]
        logger.debug(f"Widgets: {widgets}")
        logger.debug(type(self.json_field))
        if isinstance(self.json_field, dict):
            output = {}
        elif isinstance(self.json_field, list):
            output = []
        else:
            raise ValueError(f"Inappropriate data type: {type(self.json_field)}")
        for widget in widgets:
            logger.debug(f"JsonEditScreen Widget: {widget}")
            key = widget.objectName()
            match widget:
                case QSpinBox():
                    value = widget.value()
                case QLineEdit():
                    value = widget.text()
                case DictionaryJsonSubEdit():
                    value = widget.parse_form()
                case _:
                    continue
            if isinstance(self.json_field, dict):
                output[key] = value
            elif isinstance(self.json_field, list):
                if isinstance(value, list):
                    output += value
                else:
                    output.append(value)
            else:
                raise ValueError(f"Inappropriate data type: {type(self.json_field)}")
        return output


class DictionaryJsonSubEdit(QWidget):

    def __init__(self, parent, key, dic: dict):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.setObjectName(key)
        self.data = dic
        for key, value in self.data.items():
            self.layout.addWidget(QLabel(key))
            match value:
                case "int":
                    self.widget = QSpinBox()
                case "str":
                    self.widget = QLineEdit()
                case dict():
                    self.widget = DictionaryJsonSubEdit(parent, key=key, dic=value)
            self.widget.setObjectName(key)
            self.layout.addWidget(self.widget)
        self.setLayout(self.layout)

    def parse_form(self):
        widgets = [item for item in self.findChildren(QWidget) if item.objectName() in self.data.keys()]
        logger.debug(f"Widgets: {widgets}")
        output = {}
        for widget in widgets:
            logger.debug(f"DictionaryJsonSubEdit Widget: {widget}")
            key = widget.objectName()
            match widget:
                case QSpinBox():
                    value = widget.value()
                case QLineEdit():
                    value = widget.text()
                case DictionaryJsonSubEdit():
                    value = widget.parse_form()
                case _:
                    continue
            output[key] = value
        return output


class LargeTextEdit(QWidget):

    def __init__(self, parent, key: str):
        super().__init__(parent)
        self.setParent(parent)
        self.setObjectName(key)
        self.widget = QTextEdit()
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.widget)
        self.setLayout(self.layout)
