'''
Search box that performs fuzzy search for samples
'''
from pprint import pformat
from typing import Tuple, Any, List
from pandas import DataFrame
from PyQt6.QtCore import QSortFilterProxyModel
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog,
    QTableView, QWidget, QLineEdit, QGridLayout, QComboBox
)
from .submission_table import pandasModel
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class SearchBox(QDialog):
    """
    The full search widget.
    """

    def __init__(self, parent, object_type: Any, extras: List[str], **kwargs):
        super().__init__(parent)
        self.object_type = self.original_type = object_type
        self.extras = extras
        self.context = kwargs
        self.layout = QGridLayout(self)
        self.setMinimumSize(600, 600)
        options = ["Any"] + [cls.__name__ for cls in self.object_type.__subclasses__()]
        if len(options) > 1:
            self.sub_class = QComboBox(self)
            self.sub_class.setObjectName("sub_class")
            self.sub_class.addItems(options)
            self.sub_class.currentTextChanged.connect(self.update_widgets)
            self.sub_class.setEditable(False)
            self.sub_class.setMinimumWidth(self.minimumWidth())
            self.layout.addWidget(self.sub_class, 0, 0)
        else:
            self.sub_class = None
        self.results = SearchResults(parent=self, object_type=self.object_type, extras=self.extras, **kwargs)
        # logger.debug(f"results: {self.results}")
        self.layout.addWidget(self.results, 5, 0)
        self.setLayout(self.layout)
        self.setWindowTitle(f"Search {self.object_type.__name__}")
        self.update_widgets()
        self.update_data()

    def update_widgets(self):
        """
        Changes form inputs based on sample type
        """
        deletes = [item for item in self.findChildren(FieldSearch)]
        # logger.debug(deletes)
        for item in deletes:
            item.setParent(None)
        # NOTE: Handle any subclasses
        if not self.sub_class:
            self.update_data()
        else:
            if self.sub_class.currentText() == "Any":
                self.object_type = self.original_type
            else:
                self.object_type = self.original_type.find_regular_subclass(self.sub_class.currentText())
        logger.debug(f"{self.object_type} searchables: {self.object_type.searchables}")
        for iii, searchable in enumerate(self.object_type.searchables):
            widget = FieldSearch(parent=self, label=searchable, field_name=searchable)
            widget.setObjectName(searchable)
            self.layout.addWidget(widget, 1+iii, 0)
            widget.search_widget.textChanged.connect(self.update_data)
        self.update_data()

    def parse_form(self) -> dict:
        """
        Converts form into dictionary.

        Returns:
            dict: Fields dictionary
        """
        fields = [item.parse_form() for item in self.findChildren(FieldSearch)]
        return {item[0]: item[1] for item in fields if item[1] is not None}

    def update_data(self):
        """
        Shows dataframe of relevant samples.
        """
        fields = self.parse_form()
        # logger.debug(f"Got fields: {fields}")
        sample_list_creator = self.object_type.fuzzy_search(**fields)
        data = self.object_type.results_to_df(objects=sample_list_creator)
        # Setting results moved to here from __init__ 202411118
        self.results.setData(df=data)


class FieldSearch(QWidget):
    """
    Search bar.
    """

    def __init__(self, parent, label, field_name):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        label_widget = QLabel(label)
        self.layout.addWidget(label_widget)
        self.search_widget = QLineEdit()
        self.search_widget.setObjectName(field_name)
        self.layout.addWidget(self.search_widget)
        self.setLayout(self.layout)
        self.search_widget.returnPressed.connect(self.enter_pressed)

    def enter_pressed(self):
        """
        Triggered when enter is pressed on this input field.
        """
        self.parent().update_data()

    def parse_form(self) -> Tuple:
        field_value = self.search_widget.text()
        if field_value == "":
            field_value = None
        return self.search_widget.objectName(), field_value


class SearchResults(QTableView):
    """
    Results table.
    """

    def __init__(self, parent: SearchBox, object_type: Any, extras: List[str], **kwargs):
        super().__init__()
        self.context = kwargs
        self.parent = parent
        self.object_type = object_type
        self.extras = extras + self.object_type.searchables

    def setData(self, df: DataFrame) -> None:
        """
        sets data in model
        """
        self.data = df
        try:
            self.columns_of_interest = [dict(name=item, column=self.data.columns.get_loc(item)) for item in self.extras]
        except KeyError:
            self.columns_of_interest = []
        try:
            self.data['id'] = self.data['id'].apply(str)
            self.data['id'] = self.data['id'].str.zfill(3)
        except (TypeError, KeyError) as e:
            logger.error(f"Couldn't format id string: {e}")
        proxy_model = QSortFilterProxyModel()
        proxy_model.setSourceModel(pandasModel(self.data))
        self.setModel(proxy_model)
        self.doubleClicked.connect(self.parse_row)

    def parse_row(self, x):
        context = {item['name']: x.sibling(x.row(), item['column']).data() for item in self.columns_of_interest}
        logger.debug(f"Context: {context}")
        try:
            object = self.object_type.query(**context)
        except KeyError:
            object = None
        try:
            object.edit_from_search(obj=self.parent, **context)
        except AttributeError as e:
            logger.error(f"Error getting object function: {e}")
        self.doubleClicked.disconnect()
        self.parent.update_data()
