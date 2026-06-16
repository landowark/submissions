"""
Contains widgets specific to the procedure summary and procedure details.
"""
from datetime import date
import sys, logging
from pprint import pformat
from PyQt6.QtWidgets import QMenu, QTreeView, QAbstractItemView
from PyQt6.QtCore import QModelIndex, Qt, pyqtSignal, QAbstractItemModel
from PyQt6.QtGui import QAction, QCursor, QStandardItem, QContextMenuEvent
from typing import List
from tools import datetime, get_application_from_parent

logger = logging.getLogger(f"submissions.{__name__}")

def _date_sort_key(value) -> tuple:
    """
    Total-ordering key for submitted_date values that may be datetime, date or None.

    Uses POSIX timestamps so tz-aware and tz-naive datetimes compare without
    raising, and sorts None values last (they get the lowest key).
    """
    if isinstance(value, datetime):
        return (1, value.timestamp())
    if isinstance(value, date):
        return (1, datetime(value.year, value.month, value.day).timestamp())
    return (0, 0.0)


def submission_row_data(submission) -> dict:
    """
    Lightweight projection of a ClientSubmission for the tree view.

    Pulls ONLY the fields the tree renders - the top-level columns plus the
    run/procedure names used for lazy child expansion. This deliberately avoids
    ``ClientSubmission.to_pydantic().improved_dict``, which serialises every
    sample association, contact, comment and cost through a recursive sanitiser
    and full Pydantic validation, none of which the tree ever displays.

    :param submission: A ClientSubmission instance.
    :return: dict with submissiontype, submitter_plate_id, submitted_date,
             clientlab, and run (list of {rsl_plate_number, procedure[names]}).
    """
    clientlab = getattr(submission, "clientlab", None)
    runs = [
        dict(
            rsl_plate_number=run.rsl_plate_number,
            procedure=[proc.name for proc in run.procedure],
        )
        for run in submission.run
    ]
    return dict(
        submissiontype=submission.submissiontype_name,
        submitter_plate_id=submission.submitter_plate_id,
        submitted_date=submission.submitted_date,
        clientlab=getattr(clientlab, "name", "") if clientlab is not None else "",
        run=runs,
    )


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
        Rebuild the whole tree (initial load and pagination).

        For a single-submission change after a save, prefer
        :meth:`upsert_submission`, which updates just the affected row instead of
        re-querying and re-serialising the entire page.
        """
        from backend.db.models import ClientSubmission
        self.model.clear()
        subs = [submission_row_data(item)
                for item in ClientSubmission.query(chronologic=True, page=page, page_size=page_size)]
        sorted_subs = sorted(subs, key=lambda s: _date_sort_key(s.get('submitted_date')), reverse=True)
        self.model.add_top_level_submissions(sorted_subs)
        for ii in range(len(self.model.headers)):
            self.resizeColumnToContents(ii)

    def upsert_submission(self, submission) -> None:
        """
        Incrementally insert or refresh a single submission's row.

        Replaces the previous pattern of calling :meth:`set_data` after every
        mutation, which rebuilt up to ``page_size`` rows from scratch. Falls back
        to a full refresh only if the lightweight projection fails.

        :param submission: The ClientSubmission that was created or changed.
        """
        try:
            sub = submission_row_data(submission)
        except Exception as e:
            logger.error(f"Couldn't build row for submission; falling back to full refresh: {e}")
            self.set_data()
            return
        self.model.upsert_top_level(sub)
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

    def _make_child_dict(self, sub: dict) -> dict:
        """Build the TreeItem payload for one top-level submission row."""
        from backend.db.models import ClientSubmission
        raw_date = sub.get('submitted_date')
        if isinstance(raw_date, datetime):
            date_label = raw_date.date().isoformat()
        elif isinstance(raw_date, date):
            date_label = raw_date.isoformat()
        else:
            date_label = str(raw_date)
        group_str = f"{sub['submissiontype']}-{sub['submitter_plate_id']}-{date_label}"
        return dict(
            name=group_str,
            client=sub['clientlab'],
            date=raw_date,
            type=sub['submissiontype'],
            query_str=sub['submitter_plate_id'],
            item_type=ClientSubmission,
            raw_run_data=sub.get('run', []),  # Store temporarily for lazy step
        )

    def add_top_level_submissions(self, submissions_list: list):
        """Populates root level submissions efficiently."""
        if not submissions_list:
            return
        self.beginInsertRows(QModelIndex(), 0, len(submissions_list) - 1)
        for sub in submissions_list:
            self.root_item.child_items.append(TreeItem(self._make_child_dict(sub), self.root_item))
        self.endResetModel()

    def _find_top_level_row(self, query_str) -> int:
        """Return the index of the top-level row whose query_str matches, or -1."""
        for i, child in enumerate(self.root_item.child_items):
            if child.query_str == query_str:
                return i
        return -1

    def remove_top_level(self, query_str) -> bool:
        """Remove the top-level row identified by query_str. Returns True if removed."""
        row = self._find_top_level_row(query_str)
        if row < 0:
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self.root_item.child_items.pop(row)
        self.endRemoveRows()
        return True

    def upsert_top_level(self, sub: dict) -> None:
        """
        Insert a submission row, or refresh it in place if already present.

        Any existing row for the same submitter_plate_id is removed first so its
        run/procedure children rebuild from fresh data on the next expand. The new
        row is inserted at the position that keeps submitted_date descending.
        """
        self.remove_top_level(sub['submitter_plate_id'])
        new_item = TreeItem(self._make_child_dict(sub), self.root_item)
        new_key = _date_sort_key(sub.get('submitted_date'))
        insert_row = len(self.root_item.child_items)
        for i, child in enumerate(self.root_item.child_items):
            if new_key > _date_sort_key(child.data_dict.get('date')):
                insert_row = i
                break
        self.beginInsertRows(QModelIndex(), insert_row, insert_row)
        self.root_item.child_items.insert(insert_row, new_item)
        self.endInsertRows()
