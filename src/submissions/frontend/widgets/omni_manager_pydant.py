"""
Provides a screen for managing all attributes of a database object.
"""
import json, logging, sys
from json.decoder import JSONDecodeError
from datetime import datetime, timedelta
from pprint import pformat
from typing import Any, List, Literal
from PyQt6.QtCore import QSortFilterProxyModel, Qt, QModelIndex
from PyQt6.QtGui import QAction, QCursor
from PyQt6.QtWidgets import (
    QLabel, QDialog,
    QTableView, QWidget, QLineEdit, QGridLayout, QComboBox, QPushButton, QDialogButtonBox, QDateEdit, QMenu,
    QDoubleSpinBox, QSpinBox, QCheckBox, QTextEdit, QVBoxLayout, QHBoxLayout
)
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
                 extras: List[str],
                 instance: Any | None = None,
                 object_type: Any | None = None,
                 manager: Any | None = None,
                 add_edit: Literal['add', 'edit'] = 'edit',
                 **kwargs):
        super().__init__(parent)
        # NOTE: Should I pass in an instance?
        self.instance = instance
        # logger.debug(f"Setting instance: {self.instance}")
        if not self.instance:
            self.class_object = self.original_type = object_type
        else:
            self.class_object = self.original_type = self.instance.__class__
        self.add_edit = add_edit
        if manager is None:
            try:
                self.manager = self.parent().omni_object
            except AttributeError:
                self.manager = None
        else:
            self.manager = manager
        # logger.debug(f"Manager: {manager}")
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
        self.update_instance(initial=True)
        if self.add_edit == "edit":
            self.options = QComboBox(self)
            self.options.setObjectName("options")
            self.update_options()
        else:
            self.update_data()
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
        # logger.debug(f"self.class_object: {self.class_object}")
        options = [item.name for item in self.class_object.query(**query_kwargs)]
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
        self.options.currentTextChanged.connect(self.update_instance)
        # logger.debug(f"Instance: {self.instance}")
        self.update_data()

    def update_instance(self, initial: bool = False) -> None:
        """
        Gets the proper instance of this object's class object.

        Args:
            initial (bool): Whether this is the initial creation of this object.

        Returns:
            None
        """
        if self.add_edit == "edit" or initial:
            try:
                # logger.debug(f"Querying with {self.options.currentText()}")
                self.instance = self.class_object.query(name=self.options.currentText(), limit=1)
            except AttributeError:
                pass
        # logger.debug(f"Instance: {self.instance}")
        if not self.instance:
            logger.warning(f"Instance not found, creating blank instance.")
            self.instance = self.class_object()
            # logger.debug(f"self.instance: {self.instance}")
        if issubclass(self.instance.__class__, db.BaseClass):
            self.omni_object = self.instance.to_omni(expand=True)
        else:
            self.omni_object = self.instance
        # logger.debug(f"Created omni_object: {self.omni_object.__dict__}")
        self.update_data()

    def update_data(self) -> None:
        """
        Performs updating of widgets on first procedure and after options change.

        Returns:
            None
        """
        # NOTE: Remove all old widgets.
        deletes = [item for item in self.findChildren(EditProperty)] + \
                  [item for item in self.findChildren(EditRelationship)] + \
                  [item for item in self.findChildren(QDialogButtonBox)]
        for item in deletes:
            item.setParent(None)
        logger.debug(f"Self.omni_object: {self.omni_object}")
        fields = self.omni_object.__class__.model_fields
        for key, info in fields.items():
            # logger.debug(f"Attempting to set {key}, {info} widget")
            try:
                value = getattr(self.omni_object, key)
            except AttributeError:
                value = None
            # logger.debug(f"Got value {value} for key {key}")
            match info.description:
                # NOTE: ColumnProperties will be directly edited.
                case "property":
                    # NOTE: field.property.expression.type gives db column type eg. STRING or TIMESTAMP
                    # logger.debug(f"Creating property widget with value: {value}")
                    widget = EditProperty(self, key=key, column_type=info, value=value)
                # NOTE: RelationshipDeclareds will be given a list of existing related objects.
                case "relationship":
                    # NOTE: field.comparator.class_object.class_ gives the relationship class
                    widget = EditRelationship(self, key=key, class_object=info.title, value=value)
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
        # TODO: Need Relationship property here too?
        results = [item.parse_form() for item in self.findChildren(EditProperty)]
        for result in results:
            # logger.debug(f"Incoming property result: {result}")
            setattr(self.omni_object, result['field'], result['value'])
            # NOTE: Getting 'None' back here.
            # logger.debug(f"Set result: {getattr(self.instance, result['field'])}")
        results = [item.parse_form() for item in self.findChildren(EditRelationship)]
        for result in results:
            # logger.debug(f"Incoming relationship result: {result}")
            setattr(self.omni_object, result['field'], result['value'])
            # logger.debug(f"Set result: {getattr(self.omni_object, result['field'])}")
        # logger.debug(f"Instance coming from parsed form: {self.omni_object.__dict__}")
        return self.omni_object

    def add_new(self) -> None:
        """
        Creates a new instance of this object's class object.

        Returns:
            None
        """
        new_instance = self.class_object()
        self.instance = new_instance
        self.update_options()


class EditProperty(QWidget):
    """
    Class to manage info items of SQL objects.
    """
    def __init__(self, parent: ManagerWindow, key: str, column_type: Any, value):
        super().__init__(parent)
        self.label = QLabel(key.title().replace("_", " "))
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 1)
        self.setObjectName(key)
        # logger.debug(f"Column type for {key}: {type(column_type.default)}")
        match column_type.default:
            case str():
                self.widget = QLineEdit(self)
                self.widget.setText(value)
            case bool():
                if isinstance(column_type.default, bool):
                    self.widget = QCheckBox()
                    self.widget.setChecked(value)
                else:
                    if value is None:
                        value = 0
                    self.widget = QSpinBox()
                    self.widget.setMaximum(1)
                    self.widget.setValue(value)
            case float():
                if not value:
                    value = 0.0
                self.widget = QDoubleSpinBox()
                self.widget.setMaximum(999.99)
                self.widget.setValue(value)
            case datetime():
                self.widget = QDateEdit(self)
                self.widget.setDate(value)
            case timedelta():
                self.widget = QSpinBox()
                self.widget.setMaximum(9999)
                self.widget.setToolTip("This time interval is measured in days.")
                self.widget.setValue(value.days)
            case dict():
                self.widget = JsonEditButton(parent=self, key=key, value=value)
            case bytes():
                self.widget = QLabel("BLOB Under construction")
            case _:
                self.widget = None
        self.layout.addWidget(self.widget, 0, 1, 1, 3)
        self.setLayout(self.layout)

    def parse_form(self) -> dict:
        """
        Gets values from this EditProperty form.

        Returns:
            dict: Dictionary of values.
        """
        # logger.debug(f"Parsing widget {self.objectName()}: {type(self.widget)}")
        match self.widget:
            case QLineEdit():
                value = self.widget.text()
            case QDateEdit():
                value = self.widget.date()
            case QSpinBox() | QDoubleSpinBox():
                value = self.widget.value()
            case QCheckBox():
                value = self.widget.isChecked()
            case JsonEditButton():
                value = self.widget.data
            case _:
                value = None
        return dict(field=self.objectName(), value=value)


class EditRelationship(QWidget):

    def __init__(self, parent, key: str, class_object: Any, value):
        from backend.db import models
        super().__init__(parent)
        self.class_object = getattr(models, class_object)
        # logger.debug(f"Attempt value: {value}")
        # logger.debug(f"Class object: {self.class_object}")
        self.setParent(parent)
        # logger.debug(f"Edit relationship class_object: {self.class_object}")
        self.label = QLabel(key.title().replace("_", " "))
        self.setObjectName(key)  #: key is the name of the relationship this represents
        # logger.debug(f"Checking relationship for {self.parent().class_object}: {key}")
        self.relationship = getattr(self.parent().class_object, key)
        self.widget = QTableView()
        self.add_button = QPushButton("Add New")
        self.add_button.clicked.connect(self.add_new)
        self.existing_button = QPushButton("Add Existing")
        self.existing_button.clicked.connect(self.add_existing)
        if not isinstance(value, list):
            if value not in [None, ""]:
                value = [value]
            else:
                value = []
        self.data = value
        # logger.debug(f"Set data: {self.data}")
        # logger.debug(f"Parent manager: {self.parent().manager}")
        checked_manager, is_primary = check_object_in_manager(self.parent().manager, self.objectName())
        if checked_manager:
            if not self.data:
                self.data = [checked_manager]
        try:
            # logger.debug(f"Relationship {key} uses list: {self.relationship.property.uselist}")
            check = not self.relationship.property.uselist and len(self.data) >= 1
        except AttributeError:
            check = True
        if check:
            self.add_button.setEnabled(False)
            self.existing_button.setEnabled(False)
            if is_primary:
                self.widget.setEnabled(False)
        else:
            self.add_button.setEnabled(True)
            self.existing_button.setEnabled(True)
            if is_primary:
                self.widget.setEnabled(True)
        self.layout = QGridLayout()
        self.layout.addWidget(self.label, 0, 0, 1, 5)
        self.layout.addWidget(self.widget, 1, 0, 1, 8)
        self.layout.addWidget(self.add_button, 0, 6, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.layout.addWidget(self.existing_button, 0, 7, 1, 1, alignment=Qt.AlignmentFlag.AlignRight)
        self.setLayout(self.layout)
        self.set_data()

    def update_buttons(self) -> None:
        """
        Enables/disables buttons based on whether property is a list and has data.

        Returns:
            None
        """
        if not self.relationship.property.uselist and len(self.data) >= 1:
            # logger.debug(f"Property {self.relationship} doesn't use list and data is of length: {len(self.data)}")
            self.add_button.setEnabled(False)
            self.existing_button.setEnabled(False)
        else:
            self.add_button.setEnabled(True)
            self.existing_button.setEnabled(True)

    def parse_row(self, x: QModelIndex) -> None:
        """
        Gets instance of class object based on gui row values.

        Args:
            x (QModelIndex): Row object.

        Returns:
            None
        """
        context = {item: x.sibling(x.row(), self.df.columns.get_loc(item)).data() for item in self.df.columns}
        # logger.debug(f"Context: {pformat(context)}")
        try:
            object = self.class_object.query(**context)
        except KeyError:
            object = None
        self.widget.doubleClicked.disconnect()
        self.add_new(instance=object)

    def add_new(self, instance: Any = None, add_edit: Literal["add", "edit"] = "add"):
        """
        Allows addition or new instance or edit of existing one.

        Args:
            instance (Any): instance to be added
            add_edit (Literal["add", "edit"]): Whether this will be a new or existing instance.

        Returns:

        """
        if add_edit == "edit":
            logger.info(f"\n\nEditing instance: {instance.__dict__}\n\n")
        # NOTE: if an existing instance is not being edited, create a new instance
        if not instance:
            # logger.debug(f"Creating new instance of {self.class_object}")
            instance = self.class_object()
        # logger.debug(f"Creating manager window for {instance}")
        manager = self.parent().manager
        # logger.debug(f"Managers going into add new: {managers}")
        dlg = ManagerWindow(self.parent(), instance=instance, extras=[], manager=manager, add_edit=add_edit)
        if dlg.exec():
            new_instance = dlg.parse_form()
            # logger.debug(f"New instance: {pformat(new_instance.__dict__)}")
            # NOTE: Somewhere between this and the next logger, I'm losing the uses data.
            if add_edit == "add":
                # logger.debug("Setting as new object")
                self.parent().omni_object.__setattr__(self.objectName(), new_instance)
            else:
                # logger.debug("Updating dictionary")
                obj = getattr(self.parent().omni_object, self.objectName())
                if isinstance(obj, list):
                    # logger.debug(f"This is a list")
                    try:
                        # NOTE: Okay, this will not work for editing, since by definition not all attributes will line up.
                        # NOTE: Set items to search by in the Omni object itself?
                        obj = next((item for item in obj if item.check_all_attributes(new_instance.__dict__)))
                    except StopIteration:
                        logger.error(f"Couldn't find object in list.")
                        return
                # logger.debug(f"Updating \n{pformat(obj)} with \n{pformat(new_instance.__dict__)}")
                obj.__dict__.update(new_instance.__dict__)
            # logger.debug(f"Final instance: {pformat(self.parent().omni_object.__dict__)}")
            # NOTE: somewhere in the update_data I'm losing changes.
            self.parent().update_data()

    def add_existing(self):
        """
        Method to add association already existing in the database.

        Returns:
            None
        """
        dlg = SearchBox(self, object_type=self.class_object, returnable=True, extras=[])
        if dlg.exec():
            rows = dlg.return_selected_rows()
            for row in rows:
                # logger.debug(f"Querying with {row}")
                instance = self.class_object.query(**row)
                # NOTE: My custom __setattr__ should take care of any list problems.
                if isinstance(instance, list):
                    instance = instance[0]
                self.parent().omni_object.__setattr__(self.objectName(), instance.to_omni())
                self.parent().update_data()

    def set_data(self) -> None:
        """
        sets data in model
        """
        logger.debug(f"Self.data: {self.data}")
        try:
            records = [item.dataframe_dict for item in self.data]
        except AttributeError as e:
            logger.error(e)
            records = []
        logger.debug(f"Records: {records}")
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
        if not self.widget.isEnabled():
            logger.warning(f"{self.objectName()} is disabled.")
            return
        id = self.widget.selectionModel().currentIndex()
        # logger.debug(f"Row id: {id.row()}")
        # NOTE: the overly complicated {column_name: row_value} dictionary construction
        row_data = {self.df.columns[column]: self.widget.model().index(id.row(), column).data() for column in
                    range(self.widget.model().columnCount())}
        # logger.debug(f"Row data: {row_data}")
        # logger.debug(f"Attempting to grab {self.objectName()} from {self.parent().omni_object}")
        object = getattr(self.parent().omni_object, self.objectName())
        # logger.debug(f"Initial object: {object}")
        if isinstance(object, list):
            try:
                object = next((item for item in object if item.check_all_attributes(attributes=row_data)))
            except StopIteration:
                logger.warning(f"Failed to find all attributes equal, getting row {id.row()}")
                object = object[id.row()]
        object.instance_object = object.to_sql()
        # logger.debug(f"Object of interest: {pformat(object.__dict__)}")
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
        edit_action.triggered.connect(
            lambda: self.add_new(instance=object.instance_object, add_edit="edit"))
        self.menu.addAction(edit_action)
        self.menu.popup(QCursor.pos())

    def remove_item(self, object):
        """
        Remove a relationship from a list.

        Args:
            object (Any): Object to be removed.

        Returns:
            None
        """
        # logger.debug(f"Attempting to remove {object} from {self.parent().instance.__dict__}")
        editor = getattr(self.parent().omni_object, self.objectName().lower())
        # logger.debug(f"Editor: {editor}")
        try:
            # logger.debug(f"Using remove technique")
            editor.remove(object)
        except AttributeError as e:
            logger.error(f"Remove failed using set to None for {self.objectName().lower()}.")
            setattr(self.parent().omni_object, self.objectName().lower(), None)
        except ValueError as e:
            logger.error(f"Remove failed for {self.objectName().lower()} due to {e}.")
        # logger.debug(f"Setting {self.objectName()} to {editor}")
        setattr(self.parent().omni_object, self.objectName().lower(), editor)
        # logger.debug(f"After set: {getattr(self.parent().omni_object, self.objectName().lower())}")
        self.set_data()
        self.update_buttons()

    def parse_form(self) -> dict:
        """
        Gets values from this EditRelationship form.

        Returns:
            dict: Dictionary of values.
        """
        # logger.debug(f"Returning parsed form data from {self.objectName()}: {self.data}")
        try:
            check = self.relationship.property.uselist
        except AttributeError:
            check = False
        if check and isinstance(self.data, list):
            try:
                output_data = self.data[0]
            except IndexError:
                output_data = []
        else:
            output_data = self.data
        return dict(field=self.objectName(), value=output_data)


class JsonEditButton(QWidget):

    def __init__(self, parent, key: str, value: str = ""):
        super().__init__(parent)
        # logger.debug(f"Setting jsonedit data to: {value}")
        self.data = value
        self.setParent(parent)
        self.setObjectName(key)
        self.addButton = QPushButton("Add Entry", parent=self)
        self.addButton.clicked.connect(self.add_to_json)
        self.viewButton = QPushButton("View >>>", parent=self)
        self.viewButton.clicked.connect(self.toggle_textedit)
        self.layout = QGridLayout()
        self.layout.addWidget(self.addButton, 0, 0)
        self.layout.addWidget(self.viewButton, 0, 1)
        self.setLayout(self.layout)
        self.edit_box = LargeTextEdit(parent=self, key=key)
        self.parent().parent().layout.addWidget(self.edit_box, 1, self.parent().parent().layout.columnCount(),
                                                self.parent().parent().layout.rowCount() - 1, 1)
        self.edit_box.setVisible(False)
        self.edit_box.widget.textChanged.connect(self.set_json_to_text)

    def set_json_to_text(self):
        """
        Sets this object's data to text.

        Returns:
            None
        """
        # logger.debug(self.edit_box.widget.toPlainText())
        text = self.edit_box.widget.toPlainText()
        try:
            jsoner = json.loads(text)
        except JSONDecodeError:
            jsoner = None
        if jsoner:
            self.data = jsoner

    def add_to_json(self):
        """
        Sets data to jsonedit text.

        Returns:
            None
        """
        jsonedit = JsonEditScreen(parent=self, parameter=self.objectName())
        if jsonedit.exec():
            data = jsonedit.parse_form()
            # logger.debug(f"Data: {pformat(data)}")
            self.data = data

    def toggle_textedit(self):
        """
        Shows/hides text box.

        Returns:
            None
        """
        self.edit_box.setVisible(not self.edit_box.isVisible())
        # logger.debug(f"Data: {data}")
        data = json.dumps(self.data, indent=4)
        self.edit_box.widget.setText(data)


class JsonEditScreen(QDialog):

    def __init__(self, parent, parameter: str):
        super().__init__(parent)
        self.class_obj = parent.parent().parent().class_object
        self.layout = QGridLayout()
        # logger.debug(f"Parameter: {parameter}")
        self.setWindowTitle(parameter)
        try:
            self.json_field = getattr(self.class_obj, f"{parameter}_json_edit_fields")
        except AttributeError:
            try:
                self.json_field = self.class_obj.json_edit_fields
            except AttributeError:
                logger.error(f"No json fields to edit.")
                return
        match self.json_field:
            case dict():
                for key, value in self.json_field.items():
                    # logger.debug(f"Key: {key}, Value: {value}")
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

    def parse_form(self) -> list:
        """
        Gets values from this Jsonedit form.

        Returns:
            list: List of values.
        """
        widgets = [item for item in self.findChildren(QWidget) if item.objectName() in self.json_field.keys()]
        # logger.debug(f"Widgets: {widgets}")
        # logger.debug(type(self.json_field))
        if isinstance(self.json_field, dict):
            output = {}
        elif isinstance(self.json_field, list):
            output = []
        else:
            raise ValueError(f"Inappropriate data type: {type(self.json_field)}")
        for widget in widgets:
            # logger.debug(f"JsonEditScreen Widget: {widget}")
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

    def parse_form(self) -> dict:
        """
        Gets values from this Jsonedit form.

        Returns:
            list: List of values.
        """
        widgets = [item for item in self.findChildren(QWidget) if item.objectName() in self.data.keys()]
        # logger.debug(f"Widgets: {widgets}")
        output = {}
        for widget in widgets:
            # logger.debug(f"DictionaryJsonSubEdit Widget: {widget}")
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
