"""
Contains widgets specific to the procedure summary and procedure details.
"""
import sys, logging
from pprint import pformat
from PyQt6.QtWidgets import QMenu, QTreeView, QAbstractItemView
from PyQt6.QtCore import QModelIndex
from PyQt6.QtGui import QAction, QCursor, QStandardItemModel, QStandardItem, QContextMenuEvent
from typing import List
from backend.db.models import Run, ClientSubmission, Procedure
from tools import get_application_from_parent

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionsTree(QTreeView):
    """
    https://stackoverflow.com/questions/54385437/how-can-i-make-a-table-that-can-collapse-its-rows-into-categories-in-qt
    """

    def __init__(self, model, parent=None):
        super(SubmissionsTree, self).__init__(parent)
        self.app = get_application_from_parent(parent)
        self.total_count = ClientSubmission.__database_session__.query(ClientSubmission).count()
        self.setExpandsOnDoubleClick(False)
        self.model: ClientSubmissionRunModel = model
        header_labels = ["Name", "Submission Type", "Client Lab", "Submitted Date"]
        self.model.setHorizontalHeaderLabels(header_labels)
        self.setModel(self.model)
        self.setSelectionBehavior(QAbstractItemView.selectionBehavior(self).SelectRows)
        self.set_data()
        self.doubleClicked.connect(self.show_details)
        self.setStyleSheet("""
            QTreeView {
                background-color: #f5f5f5;
                alternate-background-color: "#cfe2f3";
                border: 1px solid #d3d3d3;
            }
            QTreeView::item {
                padding: 5px;
                border-bottom: 1px solid #d3d3d3;
            }
            QTreeView::item:selected {
                background-color: #0078d7;
                color: white;
            }
        """)

        # Note: Enable alternating row colors
        self.setAlternatingRowColors(True)
        self.setIndentation(20)
        self.setItemsExpandable(True)
        self.setSortingEnabled(True)
        for ii, _ in enumerate(header_labels):
            self.resizeColumnToContents(ii)

    def expand_item(self, event: QModelIndex):
        logger.debug(f"Data: {event.data()}")
        logger.debug(f"Parent {event.parent().data()}")
        logger.debug(f"Row: {event.row()}")
        logger.debug(f"Sibling: {event.siblingAtRow(event.row()).data()}")
        try:
            logger.debug(f"Model: {event.model().event()}")
        except TypeError as e:
            logger.error(f"Couldn't expand due to {e}")

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        indexes = self.selectedIndexes()
        dicto = next((item.data(1) for item in indexes if item.data(1)))
        query_obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
        # NOTE: Convert to data in id column (i.e. column 0)
        self.menu = QMenu(self)
        self.con_actions = query_obj.custom_context_events
        for key in self.con_actions.keys():
            match key.lower():
                case "add procedure":
                    action = QMenu(self.menu)
                    action.setTitle("Add Procedure")
                    for procedure in query_obj.allowed_procedures:
                        proc_name = procedure.name
                        proc = QAction(proc_name, action)
                        proc.triggered.connect(lambda _, procedure_name=proc_name: self.con_actions['Add Procedure'](obj=self, proceduretype_name=procedure_name))
                        action.addAction(proc)
                        self.menu.addMenu(action)
                case "add results":
                    action = QMenu(self.menu)
                    action.setTitle("Add Results")
                    for results in query_obj.proceduretype.allowed_result_methods:
                        res_name = results
                        res = QAction(res_name, action)
                        res.triggered.connect(lambda _, procedure_name=res_name: self.con_actions['Add Results'](obj=self, resultstype_name=procedure_name))
                        action.addAction(res)
                        self.menu.addMenu(action)
                case _:
                    action = QAction(key, self)
                    action.triggered.connect(lambda _, action_name=key: self.con_actions[action_name](obj=self))
                    self.menu.addAction(action)
        # NOTE: add other required actions
        self.menu.popup(QCursor.pos())

    def set_data(self, page: int = 1, page_size: int = 250) -> None:
        """
        sets data in model
        """
        self.clear()
        self.data = [item.to_dict(full_data=True) for item in
        # self.data = [item.details_dict() for item in
                     ClientSubmission.query(chronologic=True, page=page, page_size=page_size)]
        root = self.model.invisibleRootItem()
        for submission in self.data:
            group_str = f"{submission['submissiontype']}-{submission['submitter_plate_id']}-{submission['submitted_date']}"
            submission_item: QStandardItem = self.model.add_child(parent=root, child=dict(
                name=group_str,
                client=submission['clientlab'],
                date=submission['submitted_date'],
                type=submission['submissiontype'],
                query_str=submission['submitter_plate_id'],
                item_type=ClientSubmission
            ), additions=True)
            for run in submission['run']:
                run_item = self.model.add_child(parent=submission_item, child=dict(
                    name=run['plate_number'],
                    query_str=run['plate_number'],
                    item_type=Run
                ))
                for procedure in run['procedures']:
                    procedure_item = self.model.add_child(parent=run_item, child=dict(
                        name=procedure['name'],
                        query_str=procedure['name'],
                        item_type=Procedure
                    ))

    def _populateTree(self, children, parent):
        for child in children:
            child_item = QStandardItem(child['name'])
            parent.appendRow(child_item)
            if isinstance(children, List):
                self._populateTree(child, child_item)

    def clear(self):
        if self.model != None:
            self.model.setRowCount(0)  # works

    def show_details(self, sel: QModelIndex):
        # NOTE: Convert to data in id column (i.e. column 0)
        indexes = self.selectedIndexes()
        dicto = next((item.data(1) for item in indexes if item.data(1)))
        obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
        obj.show_details(self)

    def link_extractions(self):
        pass

    def link_pcr(self):
        pass


class ClientSubmissionRunModel(QStandardItemModel):

    def __init__(self, parent):
        super().__init__(parent)

    def add_child(self, parent: QStandardItem, child:dict, additions:bool=False) -> QStandardItem:
        item = QStandardItem(child['name'])
        item.setData(dict(item_type=child['item_type'], query_str=child['query_str']), 1)
        if additions:
            item_client = QStandardItem(child['client'])
            item_date = QStandardItem(child['date'])
            item_type = QStandardItem(child['type'])
            parent.appendRow([item, item_type, item_client, item_date])
        else:
            parent.appendRow([item])
        item.setEditable(False)
        return item

    def edit_item(self):
        pass
