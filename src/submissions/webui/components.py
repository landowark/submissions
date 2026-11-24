"""
Reuseable components to be used in htpy.
"""
from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
from pathlib import Path
from markupsafe import Markup
import htpy as h
from datetime import date, datetime

CHANGE = "instumentedattribute_change(this.id, this.value)"

def _plain(node) -> str:
    # NOTE: htpy renders markupsafe.Markup; WebView2 (via pythonnet) only accepts a plain str.
    return str.__str__(str(node))

def _asset(kind: str, name: str) -> Markup:
    """
    The contents of templates/<kind>/<name>.<kind> (css or js), inlined as render_details_template does.
    """
    from tools import jinja_env
    folder = Path(jinja_env.loader.searchpath[0])
    return Markup(folder.joinpath(kind, f"{name}.{kind}").read_text(encoding="utf-8"))

def _text(value) -> str | None:
    # NOTE: htpy attribute values must be text; None leaves the attribute out.
    return None if value is None else str(value)

def _label(item: dict):
    return h.label(for_=item["field"], style="font-size: medium;")[
        f"{item['field']} ",
        h.div(class_="tooltip")[h.u(style="color: blue;")["?"], h.span(class_="tooltiptext")[item["tooltip"]]],
        ":",
    ]

def _options(values, **attrs):
    logger.debug(pformat(values))
    return (h.option(value=_text(value), **attrs)[_text(value)] for value in values or [])

def _relationship_list(field: str, item: dict):
    return h.div(id=field, class_="dual-listbox-container relationshiplist")[
        h.div(class_="selected-list list-panel")[
            h.h4["Selected Options"],
            h.select(id=f"{field}_selectedOptions", multiple=True, size="10", class_="relationship selected")[
                _options(item["value"], class_="relationship")
            ],
        ],
        h.div(class_="controls")[
            h.button(type="button", id=f"{field}_addSelected", name=field, class_="addSelectedBtn")["<"],
            h.button(type="button", id=f"{field}_removeSelected", name=field, class_="removeSelectedBtn")[">"],
        ],
        h.div(class_="available-list list-panel")[
            h.h4["Available Options"],
            h.select(id=f"{field}_availableOptions", multiple=True, size="10", class_="relationship available")[
                _options(item["excluded"], class_="relationship")
            ],
        ],
    ]


def _association_list(field: str, item: dict):
    return h.div(id=field, class_="dual-listbox-container associationlist")[
        h.div(class_="selected-list list-panel")[
            h.h4["Selected Options"],
            h.select(id=f"{field}_selectedOptions", size="10")[_options(item["value"])],
        ],
        h.div(class_="controls")[
            h.button(type="button", id=f"{field}_addSelected", name=field, class_="addSelectedBtn association")["<"],
            h.button(type="button", id=f"{field}_removeSelected", name=field, class_="removeSelectedBtn association")[">"],
        ],
        h.div(class_="available-list list-panel")[
            h.h4["Available Options"],
            h.select(id=f"{field}_availableOptions", multiple=True, size="10",
                     onchange="createAssociationForm(this.id.replace('_availableOptions', ''), this.value)")[
                _options(item["excluded"])
            ],
        ],
        h.form(id=f"{field}association_Form", class_="associationForm"),
    ]

def _control(item: dict):
    """
    The input for one form_dictionary entry, following manager_form.html. None for types it has no input for.
    """
    field, value = item["field"], item["value"]
    match item["type"]:
        case "STR":
            kind = field if field in ("phone", "email") else "text"
            return h.input(type=kind, id=field, name=field, value=_text(value), onchange=CHANGE)
        case "INT":
            return h.input(type="number", id=field, name=field, value=_text(value), onchange=CHANGE)
        case "FLOAT":
            return h.input(type="number", step="0.1", id=field, name=field, value=_text(value), onchange=CHANGE)
        case "BOOL":
            return h.input(type="checkbox", id=field, name=field, checked=bool(value),
                           onchange="instumentedattribute_change(this.id, this.checked)")
        case "DATETIME":
            if isinstance(value, datetime):
                value = value.date().isoformat()
            elif isinstance(value, date):
                value = value.isoformat()
            return h.input(type="date", id=field, name=field, value=_text(value), onchange=CHANGE)
        case "RELATIONSHIPSCALAR":
            return h.select(id=field, name=field, onchange=CHANGE)[
                h.option(value=_text(value), selected=True)["" if value == "NA" else _text(value)],
                _options(item["excluded"]),
            ]
        case "RELATIONSHIPLIST":
            return _relationship_list(field, item)
        case "ASSOCIATIONLIST" | "OBJECTASSOCIATIONPROXYINSTANCE":
            return _association_list(field, item)
    return None

__all__ = ["_plain", "_asset", "_text", "_label", "_options", "_relationship_list", "_association_list", "_control"]