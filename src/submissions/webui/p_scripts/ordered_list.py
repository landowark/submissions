"""
Drag-to-reorder for the ORDERINPUTSCALAR widget (components._order_active_list).
Written in Python and compiled to JavaScript with PScript, like search.py.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pscript import py2js


def order_list_script():
    """
    Runs in the browser. Listens on `document` rather than on each list, because the manager form is put into
    #object_form with innerHTML after the page loads, and <script> tags inserted that way never run.
    """
    if window.orderListReady:
        return
    window.orderListReady = True
    state = {"dragged": None, "before": None}

    def item_of(node):
        # NOTE: node can be a text node (no .closest), so check for it first.
        if node is None or node.closest is undefined:
            return None
        return node.closest(".order-list-item")

    def current(item):
        # NOTE: The whole list in its current order as [{name, active}], the shape write_exclude_order stores.
        container = item.closest(".order-list-container")
        order = []
        exclude = []
        boxes = window.Array.prototype.slice.call(container.querySelectorAll(".order-check"))
        for box in boxes:
            if box.checked:
                order.append({"name": box.name, "active": box.checked})
            else:
                exclude.append({"name": box.name, "active": box.checked})
        values = order + exclude
        for ii, value in enumerate(values):
            value.update({"index":ii})
        return values

    def report(item):
        container = item.closest(".order-list-container")
        window.instumentedattribute_change(container.id, current(item))

    def on_dragstart(event):
        item = item_of(event.target)
        if item is None:
            return
        state["dragged"] = item
        state["before"] = window.JSON.stringify(current(item))
        item.classList.add("dragging")
        event.dataTransfer.effectAllowed = "move"
        # NOTE: Some engines won't start a drag unless data is set.
        event.dataTransfer.setData("text/plain", "")

    def on_dragover(event):
        dragged = state["dragged"]
        target = item_of(event.target)
        if dragged is None or target is None or target is dragged:
            return
        # NOTE: Only reorder within the list the item came from.
        if target.parentNode is not dragged.parentNode:
            return
        event.preventDefault()
        rect = target.getBoundingClientRect()
        if event.clientY < rect.top + rect.height / 2:
            target.before(dragged)
        else:
            target.after(dragged)

    def on_drop(event):
        if state["dragged"] is not None:
            event.preventDefault()

    def on_dragend(event):
        dragged = state["dragged"]
        if dragged is None:
            return
        state["dragged"] = None
        dragged.classList.remove("dragging")
        # NOTE: Dropped back where it started: nothing changed, so don't send anything.
        if window.JSON.stringify(current(dragged)) != state["before"]:
            report(dragged)

    def on_change(event):
        if event.target.classList.contains("order-check"):
            report(item_of(event.target))

    document.addEventListener("dragstart", on_dragstart)
    document.addEventListener("dragover", on_dragover)
    document.addEventListener("drop", on_drop)
    document.addEventListener("dragend", on_dragend)
    document.addEventListener("change", on_change)


# NOTE: Compiled once, when this module is imported.
ORDER_LIST_JS = py2js(order_list_script) + "\norder_list_script();\n"