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

    def __init__(self, parent, object_type: Any, extras: List[str], **kwargs):
        super().__init__(parent)
        self.object_type = object_type
        # options = ["Any"] + [cls.__name__ for cls in self.object_type.__subclasses__()]
        # self.sub_class = QComboBox(self)
        # self.sub_class.setObjectName("sub_class")
        # self.sub_class.currentTextChanged.connect(self.update_widgets)
        # self.sub_class.addItems(options)
        # self.sub_class.setEditable(False)
        self.setMinimumSize(600, 600)
        # self.sub_class.setMinimumWidth(self.minimumWidth())
        # self.layout.addWidget(self.sub_class, 0, 0)
        self.results = SearchResults(parent=self, object_type=self.object_type, extras=extras, **kwargs)
        self.layout.addWidget(self.results, 5, 0)
        self.setLayout(self.layout)
        self.setWindowTitle(f"Search {self.object_type.__name__}")
        self.update_widgets()
        self.update_data()

    def update_widgets(self):
        """
        Changes form inputs based on sample type
        """
        for iii, searchable in enumerate(self.object_type.searchables):
            self.widget = FieldSearch(parent=self, label=searchable, field_name=searchable)
            self.layout.addWidget(self.widget, 1, 0)
            self.widget.search_widget.textChanged.connect(self.update_data)
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
        # logger.debug(f"Running update_data with sample type: {self.type}")
        fields = self.parse_form()
        # logger.debug(f"Got fields: {fields}")
        sample_list_creator = self.object_type.fuzzy_search(**fields)
        data = self.object_type.results_to_df(objects=sample_list_creator)
        self.results.setData(df=data)


class FieldSearch(QWidget):

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
        print(self.data)
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
        try:
            object = self.object_type.query(**{self.object_type.search: context[self.object_type.search]})
        except KeyError:
            object = None
        try:
            object.edit_from_search(**context)
        except AttributeError:
            pass
        self.doubleClicked.disconnect()
        self.parent.update_data()

