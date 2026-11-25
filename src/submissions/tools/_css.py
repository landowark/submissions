STYLE = {
    ":root": {
        "--bg": "#f5f5f5",
        "--alt": "#cfe2f3",
        "--line": "#d3d3d3",
        "--sel": "#0078d7",
    },
    "body": {
        "margin": "10px",
        "font": '14px "Segoe UI", sans-serif',
        "background": "#fff",
        "color": "#222",
    },
    "header": {
        "padding": "8px 16px",
        "border-bottom": "1px solid var(--line)",
        "display": "flex",
        "justify-content": "space-between",
        "align-items": "center",
    },
    "header h1": {
        "font-size": "16px",
        "margin": "0",
    },
    "main": {
        "padding": "8px 16px",
    },
    "table": {
        "border-collapse": "collapse",
        "width": "100%",
        "background": "var(--bg)",
        "border": "1px solid var(--line)",
    },
    "th, td": {
        "text-align": "left",
        "padding": "5px 8px",
        "border-bottom": "1px solid var(--line)",
        "white-space": "nowrap",
    },
    "th": {
        "position": "sticky",
        "top": "0",
        "background": "#e8e8e8",
    },
    "tr.alt td": {
        "background": "var(--alt)",
    },
    "tr.selected td": {
        "background": "var(--sel)",
        "color": "#fff",
    },
    ".toggle": {
        "display": "inline-block",
        "width": "1.2em",
        "cursor": "pointer",
        "user-select": "none",
    },
    "tr.depth-1 td.name": {
        "padding-left": "28px",
    },
    "tr.depth-2 td.name": {
        "padding-left": "48px",
    },
    ".tooltip": {
        "position": "relative",
        "z-index": "2",
        "display": "inline-block",
        "border-bottom": "1px dotted black",
    },
    ".tooltip .tooltiptext": {
        "visibility": "hidden",
        "width": "120px",
        "background-color": "black",
        "color": "#fff",
        "text-align": "center",
        "padding": "5px 0",
        "border-radius": "6px",
        "position": "absolute",
        "z-index": "1",
        "bottom": "100%",
        "left": "50%",
        "transform": "translateX(-50%)",
    },
    ".tooltip:hover .tooltiptext": {
        "visibility": "visible",
        "font-size": "large",
    },
    "#pager": {
        "margin": "8px 0",
        "display": "flex",
        "gap": "12px",
        "align-items": "center",
    },
    ".menu": {
        "position": "fixed",
        "list-style": "none",
        "margin": "0",
        "padding": "4px 0",
        "background": "#fff",
        "color": "#222",
        "border": "1px solid #999",
        "box-shadow": "2px 2px 6px rgba(0, 0, 0, .2)",
        "min-width": "160px",
        "z-index": "10",
    },
    ".menu li": {
        "padding": "4px 24px 4px 16px",
        "position": "relative",
        "white-space": "nowrap",
    },
    ".menu li:hover:not(.disabled)": {
        "background": "var(--sel)",
        "color": "#fff",
    },
    ".menu li.disabled": {
        "color": "#999",
    },
    ".menu li.parent::after": {
        "content": '"\\203A"',
        "position": "absolute",
        "right": "8px",
    },
    ".menu li > .menu": {
        "display": "none",
        "position": "absolute",
        "top": "-5px",
        "left": "100%",
    },
    ".menu li:hover > .menu": {
        "display": "block",
    },
    "#status": {
        "position": "fixed",
        "bottom": "12px",
        "right": "16px",
        "background": "#333",
        "color": "#fff",
        "padding": "8px 12px",
        "border-radius": "4px",
    },
    "#tabs": {
        "display": "flex",
        "gap": "2px",
        "padding": "0 16px",
        "border-bottom": "1px solid var(--line)",
    },
    "#tabs button": {
        "border": "1px solid transparent",
        "border-bottom": "none",
        "background": "none",
        "padding": "6px 14px",
        "cursor": "pointer",
    },
    "#tabs button.active": {
        "border-color": "var(--line)",
        "background": "var(--bg)",
        "font-weight": "600",
    },
    "#chart-filters": {
        "display": "flex",
        "flex-wrap": "wrap",
        "gap": "12px",
        "align-items": "flex-start",
    },
    "#chart-filters fieldset": {
        "border": "1px solid var(--line)",
        "padding": "4px 10px",
    },
    "#chart-filters fieldset label": {
        "display": "block",
        "white-space": "nowrap",
    },
    "#chart-actions": {
        "margin": "8px 0",
        "display": "flex",
        "gap": "8px",
    },
    "#chart-plot": {
        "height": "70vh",
    },
    "#chart-report": {
        "width": "100%",
        "height": "75vh",
        "border": "1px solid var(--line)",
    },
    ".header-actions": {
        "display": "flex",
        "gap": "8px",
    },
    "body.dropping": {
        "outline": "3px dashed var(--sel)",
        "outline-offset": "-6px",
    },
    "#fields": {
        "display": "flex",
        "flex-wrap": "wrap",
        "gap": "10px",
        "margin-bottom": "10px",
    },
    "#fields label": {
        "display": "flex",
        "flex-direction": "column",
        "font-weight": "600",
    },
    "tbody tr:hover": {
        "background": "#cfe2f3",
        "cursor": "default",
    },
    "#results": {
        "max-height": "75vh",
        "overflow": "auto",
    },
    "#message": {
        "color": "#666",
    },
    ".order-list-item": {
        "display": "grid",
        "grid-template-columns": "1fr auto 1fr",
        "align-items": "center",
        "align-items": "center",
        "border": "1px solid black",
        "border-radius": "6px"
    },
    ".order-check": {
        "justify-self": "start"
    },
    ".order-span": {
        "justify-self": "end"
    },
    ".order-list-container": {
        "display": "flex",
        "justify-content": "center",
        "align-items": "center",
        "width": "fit-content",
        "padding": "10px",
        "margin": "auto"
    },
    ".data-link": {
        "color": "blue",
        "text-decoration": "underline",
        "text-decoration-color": "blue",
    },
    ".data-link:hover": {
        "color": "#ff33ff",
        "text-decoration-color": "#ff33ff",
        "cursor": "pointer",
    },
    "div.procedure_creation_leftright": {
        "width": "100%",
        "overflow": "auto",
        "border-style": "solid",
        "border-width": "2px",
        "background-color": "#FFFFFF",
        "display": "flex",
    },
    "div.procedure_creation_leftright div.left": {
        "height": "100%",
        "width": "15%",
        "float": "left",
        "border-style": "solid",
        "border-width": "1px",
        "background-color": "#FFF4A3",
        "padding": "5px",
        "flex": "0.25",
    },
    "div.procedure_creation_leftright div.right": {
        "height": "100%",
        "width": "84%",
        "float": "left",
        "border-style": "solid",
        "border-width": "1px",
        "background-color": "#D9EEE1",
        "padding": "5px",
        "flex": "0.75",
        "object-fit": "contain",
    },
    ".dropdown": {
        "width": "100%",
    },
    ".form_text.full": {
        "width": "97%",
    },
    "div.gallery": {
        "width": "100%",
        "object-fit": "contain",
    },
    ".context-menu": {
        "display": "none",
        "flex-direction": "column",
        "align-items": "flex-start",
        "width": "150px",
        "margin": "32px",
        "position": "absolute",
    },
    ".context-menu--active": {
        "display": "block",
        "z-index": "10",
        "background-color": "white",
        "border": "2px solid black",
        "padding": "5px",
    },
    ".plate": {
        "display": "inline-grid",
        "grid-auto-columns": "1fr",
        "grid-auto-flow": "column",
        "place-content": "center center",
        "height": "auto",
        "grid-gap": "2px",
        "width": "100%",
        "max-width": "100%",
        "position": "relative",
        "z-index": "1",
    },
    ".well": {
        "border": "1px solid #000",
        "padding": "2px",
        "display": "flex",
        "text-align": "center",
        "box-shadow": "0 2px 10px rgba(0, 0, 0, 0.1)",
        "transition": "all 0.3s ease",
        "background-color": "#ffffff",
        "cursor": "move",
        "overflow": "hidden",
        "justify-content": "center",
        "align-items": "center",
        "width": "100%",
        "height": "100%",
        "aspect-ratio": "1/1",
        "z-index": "2",
    },
    ".well:hover": {
        "box-shadow": "0 4px 25px rgba(0, 0, 0, 0.5)",
    },
    ".well.selected": {
        "background-color": "#4a90e2",
        "color": "white",
        "border": "2px solid #2c5aa0",
        "box-shadow": "0 0 10px rgba(74, 144, 226, 0.8)",
    },
    'button[type="button"]': {
        "position": "relative",
        "z-index": "10",
    },
    ".grid-item p": {
        "max-width": "100%",
        "border-radius": "8px",
    },
    "ul.no-bullets": {
        "list-style-type": "none",
        "padding": "0",
        "margin": "0",
    },
    ".negativecontrol": {
        "background-color": "cyan",
    },
    ".positivecontrol": {
        "background-color": "pink",
    },
    ".sample": {
        "background-color": "greenyellow",
    },
    ".nested": {
        "margin-left": "50px",
        "padding": "0 18px",
        "overflow": "hidden",
        "background-color": "#f1f1f1",
    },
    ".nested .nested": {
        "background-color": "#ffffff",
    },
    ".hidden_input": {
        "display": "none",
    },
    ".collapsible": {
        "background-color": "#eee",
        "color": "#444",
        "cursor": "pointer",
        "padding": "18px",
        "width": "100%",
        "border": "none",
        "text-align": "left",
        "outline": "none",
        "font-size": "15px",
    },
    ".active, .collapsible:hover": {
        "background-color": "#ccc",
    },
    ".unused": {
        "color": "red",
        "text-decoration-line": "line-through",
        "text-decoration-color": "red",
    },
    ".grid-container": {
        "display": "grid",
        "grid-auto-flow": "column",
    },
    ".disable_section": {
        "pointer-events": "none",
        "opacity": "0.4",
    },
    ".dual-listbox-container": {
        "display": "flex",
        "justify-content": "center",
        "align-items": "center",
        "gap": "15px",
    },
    ".list-panel": {
        "border": "1px solid #ccc",
        "padding": "10px",
        "border-radius": "5px",
    },
    ".list-panel select": {
        "width": "200px",
        "height": "250px",
        "border": "none",
        "outline": "none",
    },
    ".controls": {
        "display": "flex",
        "flex-direction": "column",
        "gap": "10px",
    },
    ".controls button": {
        "padding": "8px 12px",
        "background-color": "#007bff",
        "color": "white",
        "border": "none",
        "border-radius": "3px",
        "cursor": "pointer",
    },
    ".controls button:hover": {
        "background-color": "#0056b3",
    },
    ".rich-tooltip": {
        "position": "fixed",
        "z-index": "1000",
        "display": "none",
        "max-width": "360px",
        "padding": "6px 8px",
        "background": "#ffffe1",
        "color": "#000",
        "border": "1px solid #767676",
        "box-shadow": "2px 2px 4px rgba(0, 0, 0, 0.2)",
        "font-size": "12px",
        "line-height": "1.35",
        "pointer-events": "none",
    },
}

css = "\n".join(
    selector + " { " + "; ".join(
        f"{key}: {value}" for key, value in props.items()
    ) + " }"
    for selector, props in STYLE.items()
)