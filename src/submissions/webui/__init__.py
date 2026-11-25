from __future__ import annotations
from logging import getLogger
logger = getLogger(f"submissions.{__name__}")
import cssutils
from tools import ctx

def css_to_dict(file_path):
    sheet = cssutils.parseFile(file_path)
    css_dict = {}

    for rule in sheet:
        # Filter only standard style rules (ignores comments, @imports, etc.)
        if rule.type == rule.STYLE_RULE:
            selector = rule.selectorText
            # Create a nested dictionary of property: value
            properties = {prop.name: prop.value for prop in rule.style}

            # Merge properties if the selector appears multiple times
            if selector in css_dict:
                css_dict[selector].update(properties)
            else:
                css_dict[selector] = properties

    return css_dict

STYLE = css_to_dict(ctx.static.joinpath("app.css"))
css = "\n".join(
    selector + " { " + "; ".join(
        f"{key}: {value}" for key, value in props.items()
    ) + " }"
    for selector, props in STYLE.items()
)
