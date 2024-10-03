'''
Search box that performs fuzzy search for samples
'''
from pprint import pformat
from typing import Tuple
from pandas import DataFrame
from PyQt6.QtCore import QSortFilterProxyModel
from PyQt6.QtWidgets import (
    QLabel, QVBoxLayout, QDialog,
    QComboBox, QTableView, QWidget, QLineEdit, QGridLayout
)
from backend.db.models import BasicSample
from .submission_table import pandasModel
import logging

logger = logging.getLogger(f"submissions.{__name__}")


class SearchBox(QDialog):

    def __init__(self, parent):
        super().__init__(parent)
        self.layout = QGridLayout(self)
        self.sample_type = QComboBox(self)
        self.sample_type.setObjectName("sample_type")
        self.sample_type.currentTextChanged.connect(self.update_widgets)
        options = ["Any"] + [cls.__mapper_args__['polymorphic_identity'] for cls in BasicSample.__subclasses__()]
        self.sample_type.addItems(options)
        self.sample_type.setEditable(False)
        self.setMinimumSize(600, 600)
        self.sample_type.setMinimumWidth(self.minimumWidth())
        self.layout.addWidget(self.sample_type, 0, 0)
        self.results = SearchResults()
        self.layout.addWidget(self.results, 5, 0)
        self.setLayout(self.layout)
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
        if self.sample_type.currentText() == "Any":
            self.type = BasicSample
        else:
            self.type = BasicSample.find_polymorphic_subclass(self.sample_type.currentText())
        # logger.debug(f"Sample type: {self.type}")
        searchables = self.type.get_searchables()
        start_row = 1
        for iii, item in enumerate(searchables):
            widget = FieldSearch(parent=self, label=item['label'], field_name=item['field'])
            self.layout.addWidget(widget, start_row+iii, 0)
            widget.search_widget.textChanged.connect(self.update_data)
        self.update_data()

    def parse_form(self) -> dict:
        """
        Converts form into dictionary.

        Returns:
            dict: Fields dictionary
        """        
        fields = [item.parse_form() for item in self.findChildren(FieldSearch)]
        return {item[0]:item[1] for item in fields if item[1] is not None}

    def update_data(self):
        """
        Shows dataframe of relevant samples.
        """
        # logger.debug(f"Running update_data with sample type: {self.type}")
        fields = self.parse_form()
        # logger.debug(f"Got fields: {fields}")
        # sample_list_creator = self.type.fuzzy_search(sample_type=self.type, **fields)
        sample_list_creator = self.type.fuzzy_search(**fields)
        data = self.type.samples_to_df(sample_list=sample_list_creator)
        # logger.debug(f"Data: {data}")
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

    def __init__(self):
        super().__init__()
        self.doubleClicked.connect(lambda x: BasicSample.query(submitter_id=x.sibling(x.row(), 0).data()).show_details(self))

    def setData(self, df:DataFrame) -> None:
        """
        sets data in model
        """
        self.data = df
        try:
            self.data['id'] = self.data['id'].apply(str)
            self.data['id'] = self.data['id'].str.zfill(3)
        except (TypeError, KeyError):
            logger.error("Couldn't format id string.")
        proxy_model = QSortFilterProxyModel()
        proxy_model.setSourceModel(pandasModel(self.data))
        self.setModel(proxy_model)
        