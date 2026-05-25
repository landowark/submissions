"""
Contains widgets specific to the procedure summary and procedure details.
"""
from datetime import date
import sys, logging
from operator import itemgetter
from pprint import pformat
from PyQt6.QtWidgets import QMenu, QTreeView, QAbstractItemView
from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal, QAbstractItemModel
from PyQt6.QtGui import QAction, QCursor, QStandardItem, QContextMenuEvent
from typing import List
from tools import datetime, get_application_from_parent

logger = logging.getLogger(f"submissions.{__name__}")


class SubmissionsTree(QTreeView):
    """
    https://stackoverflow.com/questions/54385437/how-can-i-make-a-table-that-can-collapse-its-rows-into-categories-in-qt
    """

    clientsubmissionExpanded = pyqtSignal(QModelIndex)
    runExpanded = pyqtSignal(QModelIndex)

    def __init__(self, model, parent=None):
        super(SubmissionsTree, self).__init__(parent)
        from backend.db.models import ClientSubmission
        self.app = get_application_from_parent(parent)
        self.total_count = ClientSubmission.__database_session__.query(ClientSubmission).count()
        self.setExpandsOnDoubleClick(False)
        self.model: ClientSubmissionRunModel = model
        # header_labels = ["Name", "Submission Type", "Client Lab", "Submitted Date"]
        # self.model.setHorizontalHeaderLabels(header_labels)
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

        # NOTE: Enable alternating row colors
        self.setAlternatingRowColors(True)
        self.setIndentation(20)
        self.setItemsExpandable(True)
        self.setSortingEnabled(True)
        self.sortByColumn(3, Qt.SortOrder.DescendingOrder)
        self.expanded.connect(self._route_expansion)

    def _route_expansion(self, index: QModelIndex):
        """Intercepts tree node expansion requests to build sub-items dynamically."""
        if not index.isValid():
            return

        item: TreeItem = index.internalPointer()
        if item.is_loaded or not item.has_children_placeholder:
            return # Data already present

        from backend.db.models import ClientSubmission, Run, Procedure
        
        # 1. Handle Submission Node expansion -> Load Runs
        if item.item_type == ClientSubmission:
            runs_data = item.data_dict.get('raw_run_data', [])
            if runs_data:
                self.model.beginInsertRows(index, 0, len(runs_data) - 1)
                for run in runs_data:
                    run_node = TreeItem(dict(
                        name=run['rsl_plate_number'],
                        query_str=run['rsl_plate_number'],
                        item_type=Run,
                        raw_procedure_data=run.get('procedure', [])
                    ), item)
                    item.child_items.append(run_node)
                self.model.endInsertRows()
            else:
                item.has_children_placeholder = False

        # 2. Handle Run Node expansion -> Load Procedures
        elif item.item_type == Run:
            procedures_data = item.data_dict.get('raw_procedure_data', [])
            if procedures_data:
                self.model.beginInsertRows(index, 0, len(procedures_data) - 1)
                for proc in procedures_data:
                    proc_name = proc['name'] if isinstance(proc, dict) else proc
                    logger.debug(f" Type: {type(proc_name)}, Value: {proc_name}")
                    proc_node = TreeItem(dict(
                        name=proc_name,
                        query_str=proc_name,
                        item_type=Procedure
                    ), item)
                    item.child_items.append(proc_node)
                self.model.endInsertRows()
            else:
                item.has_children_placeholder = False

        item.is_loaded = True

    def contextMenuEvent(self, event: QContextMenuEvent):
        """
        Creates actions for right click menu events.

        Args:
            event (_type_): the item of interest
        """
        local_pos = event.pos()
        sel: QModelIndex = self.indexAt(local_pos)
        if not sel.isValid():
            return
        # indexes = self.selectedIndexes()
        # dicto = next((item.data(1) for item in indexes if item.data(1)))
        target_index = sel.siblingAtColumn(0)

        # 2. Extract the data dictionary we stored in the UserRole namespace
        metadata = target_index.data(Qt.ItemDataRole.UserRole)
        if metadata and isinstance(metadata, dict):
            item_type = metadata.get('item_type')
            query_str = metadata.get('query_str')

            if item_type and query_str:
                # 3. Perform your database lookup using the safely extracted fields
                query_obj = item_type.query(name=query_str, limit=1)
                
            else:
                return
        else:
            return
        # query_obj = dicto['item_type'].query(name=dicto['query_str'], limit=1)
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
                        res_name = results.get('name', None)
                        if res_name:
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
        from backend.db.models import Run, ClientSubmission, Procedure
        self.model.clear()
        subs = [item.to_pydantic().improved_dict
                for item in ClientSubmission.query(chronologic=True, page=page, page_size=page_size)]
        sorted_subs = sorted(subs, key=itemgetter('submitted_date'), reverse=True)
        self.model.add_top_level_submissions(sorted_subs)
        # self.model.add_top_level_submissions(subs)
        
        for ii in range(len(self.model.headers)):
            self.resizeColumnToContents(ii)

    def _populateTree(self, children, parent):
        for child in children:
            child_item = QStandardItem(child['name'])
            parent.appendRow(child_item)
            if isinstance(children, List):
                self._populateTree(child, child_item)

    def clear(self):
        if self.model != None:
            self.model.setRowCount(0)  # works
            # pass

    def show_details(self, sel: QModelIndex):
        if not sel.isValid():
            return

        # 1. Tree selection returns an index for each column in the row.
        # Force the index to point to Column 0 where our TreeItem pointer exists.
        target_index = sel.siblingAtColumn(0)

        # 2. Extract the data dictionary we stored in the UserRole namespace
        metadata = target_index.data(Qt.ItemDataRole.UserRole)
        if metadata and isinstance(metadata, dict):
            item_type = metadata.get('item_type')
            query_str = metadata.get('query_str')

            if item_type and query_str:
                # 3. Perform your database lookup using the safely extracted fields
                obj = item_type.query(name=query_str, limit=1)
                
                if obj:
                    obj.show_details(self)


class TreeItem:
    def __init__(self, data: dict = None, parent=None):
        self.parent_item = parent
        self.child_items = []
        
        self.data_dict = data or {}
        self.name = self.data_dict.get('name', 'Unknown')
        self.item_type = self.data_dict.get('item_type')
        self.query_str = self.data_dict.get('query_str')
        self.client = self.data_dict.get('client', '')
        self.type_str = self.data_dict.get('type', '')
        
        dt = self.data_dict.get('date', '')
        if isinstance(dt, (date, datetime)):
            self.date_str = dt.strftime("%Y-%m-%d")
        else:
            self.date_str = str(dt)

        # Lazy loading properties
        self.is_loaded = False
        # Procedures are leaf nodes (no children). Submissions & Runs have children.
        from backend.db.models import Procedure
        self.has_children_placeholder = (self.item_type != Procedure)


class ClientSubmissionRunModel(QAbstractItemModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_item = TreeItem()
        self.headers = ["Name", "Submission Type", "Client Lab", "Submitted Date"]

    def hasChildren(self, parent=QModelIndex()):
        if not parent.isValid():
            return True
        return parent.internalPointer().has_children_placeholder

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        return len(parent_item.child_items)

    def index(self, row, column, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_item = parent.internalPointer() if parent.isValid() else self.root_item
        child_item = parent_item.child_items[row]
        return self.createIndex(row, column, child_item)

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        child_item = index.internalPointer()
        parent_item = child_item.parent_item
        if parent_item == self.root_item:
            return QModelIndex()
        grandparent = parent_item.parent_item
        row = grandparent.child_items.index(parent_item)
        return self.createIndex(row, 0, parent_item)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = index.internalPointer()
        
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0: return item.name
            elif index.column() == 1: return item.type_str
            elif index.column() == 2: return item.client
            elif index.column() == 3: return item.date_str

        # Replaces your original item.setData(..., 1) metadata lookups
        if role == Qt.ItemDataRole.UserRole:
            return {
                'item_type': item.item_type,
                'query_str': item.query_str
            }
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None

    def clear(self):
        self.beginResetModel()
        self.root_item.child_items = []
        self.endResetModel()

    def add_top_level_submissions(self, submissions_list: list):
        """Populates root level submissions efficiently."""
        from backend.db.models import ClientSubmission
        self.beginInsertRows(QModelIndex(), 0, len(submissions_list) - 1)
        for sub in submissions_list:
            group_str = f"{sub['submissiontype']}-{sub['submitter_plate_id']}-{sub['submitted_date']}"
            child_dict = dict(
                name=group_str,
                client=sub['clientlab'],
                date=sub['submitted_date'],
                type=sub['submissiontype'],
                query_str=sub['submitter_plate_id'],
                item_type=ClientSubmission,
                raw_run_data=sub.get('run', []) # Store temporarily for lazy step
            )
            self.root_item.child_items.append(TreeItem(child_dict, self.root_item))
        self.endResetModel()


