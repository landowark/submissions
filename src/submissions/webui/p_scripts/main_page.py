"""
Browser code for the main window (Api._page): the Submissions tab and the chart/report tabs.
Port of static/submissions.js and static/charts.js. Written in Python and compiled to JavaScript with PScript,
so it can be inlined into the html= page (an html= page can't load scripts by relative src).
"""
from pscript import py2js


def main_page_script():
    """
    Runs in the browser. PScript compiles this function to JavaScript (see MAIN_PAGE_JS), so it uses the browser's
    `window` and `document`, and JavaScript rules apply to numbers and objects.

    NOTE: PScript treats an empty list as false (like Python, unlike JavaScript), and supports neither `...` nor
    *args in calls, so DOM methods that take many nodes are called with .apply(element, list).
    """
    state = {"page": 1, "pages": 1, "status_timer": None,
             "current_chart": None, "chart_request": 0, "plotly": None}
    charts = {}
    tbody = document.querySelector("#submissions tbody")
    menu = document.getElementById("context-menu")
    plot_div = document.getElementById("chart-plot")
    report_frame = document.getElementById("chart-report")
    chart_message = document.getElementById("chart-message")

    def error_text(err):
        return err.message if err.message is not undefined else str(err)

    def status(message):
        el = document.getElementById("status")
        el.textContent = message
        el.hidden = False
        window.clearTimeout(state["status_timer"])

        def hide():
            el.hidden = True
        state["status_timer"] = window.setTimeout(hide, 5000)

    # ── Submissions tab ─────────────────────────────────────────────────────

    def append_all(parent, nodes):
        parent.append.apply(parent, nodes)

    def replace_all(parent, nodes):
        parent.replaceChildren.apply(parent, nodes)

    def cell(text, cls=None):
        td = document.createElement("td")
        td.textContent = "" if text is None or text is undefined else text
        if cls:
            td.className = cls
        return td

    def make_row(kind, id, name, depth, cols=None, children=None):
        cols = cols if cols is not None else ["", "", ""]
        children = children if children is not None else []
        tr = document.createElement("tr")
        tr.className = kind + " depth-" + str(depth)
        tr.dataset.kind = kind
        tr.dataset.id = id
        tr.dataset.name = name
        name_cell = cell("", "name")
        toggle = document.createElement("span")
        toggle.className = "toggle"
        toggle.textContent = "▸" if len(children) else ""

        def on_toggle(e):
            e.stopPropagation()
            toggle_row(tr)
        toggle.addEventListener("click", on_toggle)
        name_cell.append(toggle, document.createTextNode(name))
        append_all(tr, [name_cell] + [cell(c) for c in cols])
        tr._children = children
        tr._childRows = None
        return tr

    def child_rows(tr):
        if tr.dataset.kind == "submission":
            rows = []
            for run in tr._children:
                name = run.rsl_plate_number + " ✔" if run.approved else run.rsl_plate_number
                rows.append(make_row("run", run.id, name, 1, None, run.procedure))
            return rows
        return [make_row("procedure", proc.id, proc.name, 2) for proc in tr._children]

    def collapse(tr):
        if tr._childRows is not None:
            for child in tr._childRows:
                collapse(child)
                child.remove()
        tr._childRows = None
        if len(tr._children):
            tr.querySelector(".toggle").textContent = "▸"

    def toggle_row(tr):
        if not len(tr._children):
            return
        if tr._childRows is not None:
            collapse(tr)
            return
        tr._childRows = child_rows(tr)
        tr.after.apply(tr, tr._childRows)
        tr.querySelector(".toggle").textContent = "▾"

    def submission_row(sub, index):
        # NOTE: A function per row, so each row keeps its own values (JS loop variables don't).
        name = sub.submissiontype + "-" + sub.submitter_plate_id + "-" + sub.submitted_date
        tr = make_row("submission", sub.id, name, 0,
                      [sub.submissiontype, sub.clientlab, sub.submitted_date], sub.run)
        if index % 2:
            tr.classList.add("alt")
        return tr

    async def load(page):
        try:
            data = await window.pywebview.api.list_submissions(page)
            state["page"] = data.page
            state["pages"] = data.pages
            replace_all(tbody, [submission_row(sub, ii) for ii, sub in enumerate(data.rows)])
            document.getElementById("page-label").textContent = str(state["page"]) + " of " + str(state["pages"])
            document.getElementById("prev").disabled = state["page"] <= 1
            document.getElementById("next").disabled = state["page"] >= state["pages"]
        except Exception as err:
            status("Couldn't load submissions: " + error_text(err))

    def select(tr):
        current = tbody.querySelector("tr.selected")
        if current is not None:
            current.classList.remove("selected")
        tr.classList.add("selected")

    def menu_item(label, enabled, on_click=None):
        li = document.createElement("li")
        li.textContent = label
        if not enabled:
            li.classList.add("disabled")
            li.title = "Not available in the web UI yet"
        elif on_click is not None:
            li.addEventListener("click", on_click)
        return li

    def action_item(tr, item):
        # NOTE: A function per item, so each click handler keeps its own item.
        def on_click():
            run_action(tr, item.label)
        return menu_item(item.label, item.enabled, on_click)

    def option_item(tr, item, option):
        def on_click():
            run_action(tr, item.label, option)
        return menu_item(option, item.enabled, on_click)

    def menu_entry(tr, item):
        if not item.options:
            return action_item(tr, item)
        li = menu_item(item.label, item.enabled)
        li.classList.add("parent")
        sub = document.createElement("ul")
        sub.className = "menu"
        append_all(sub, [option_item(tr, item, option) for option in item.options])
        li.append(sub)
        return li

    def show_menu(items, tr, x, y):
        replace_all(menu, [menu_entry(tr, item) for item in items])
        menu.hidden = False
        r = menu.getBoundingClientRect()
        menu.style.left = str(min(x, window.innerWidth - r.width - 4)) + "px"
        menu.style.top = str(min(y, window.innerHeight - r.height - 4)) + "px"

    async def run_action(tr, action, option=None):
        menu.hidden = True
        text = None
        if action == "Delete" and not window.confirm("Are you sure you want to delete " + tr.dataset.name + "?"):
            return
        if action == "Add Comment":
            text = window.prompt("Comment on " + tr.dataset.name + ":")
            if text is None:
                return
        try:
            result = await window.pywebview.api.run_action(tr.dataset.kind, int(tr.dataset.id), action, option, text)
            if result.message:
                status(result.message)
            if result.refresh:
                await load(state["page"])
        except Exception as err:
            status(action + " failed: " + error_text(err))

    def on_tbody_click(e):
        tr = e.target.closest("tr")
        if tr is not None:
            select(tr)

    def on_tbody_dblclick(e):
        tr = e.target.closest("tr")
        if tr is not None and not e.target.classList.contains("toggle"):
            run_action(tr, "Show Details")

    async def on_tbody_contextmenu(e):
        tr = e.target.closest("tr")
        if tr is None:
            return
        e.preventDefault()
        select(tr)
        try:
            items = await window.pywebview.api.context_menu(tr.dataset.kind, int(tr.dataset.id))
            show_menu(items, tr, e.clientX, e.clientY)
        except Exception as err:
            status("Couldn't build menu: " + error_text(err))

    def hide_menu():
        menu.hidden = True

    def on_keydown(e):
        if e.key == "Escape":
            menu.hidden = True

    tbody.addEventListener("click", on_tbody_click)
    tbody.addEventListener("dblclick", on_tbody_dblclick)
    tbody.addEventListener("contextmenu", on_tbody_contextmenu)
    document.addEventListener("click", hide_menu)
    document.addEventListener("keydown", on_keydown)

    # ── Chart and report tabs ───────────────────────────────────────────────

    def fetch_plotly():
        def loader(resolve, reject):
            script = document.createElement("script")
            script.src = "plotly.min.js"
            script.onload = resolve

            def failed():
                reject(window.Error("Could not load plotly.min.js"))
            script.onerror = failed
            document.head.append(script)
        return window.Promise(loader)

    async def load_plotly():
        if window.Plotly is not undefined:
            return
        if state["plotly"] is None:
            state["plotly"] = fetch_plotly()
        await state["plotly"]

    def fieldset(label, children):
        box = document.createElement("fieldset")
        legend = document.createElement("legend")
        legend.textContent = label
        append_all(box, [legend] + children)
        return box

    def date_input(values, key, label):
        wrap = document.createElement("label")
        input = document.createElement("input")
        input.type = "date"
        input.id = "chart-" + key
        input.value = values[key]

        def on_change():
            values[key] = input.value
            draw_chart()
        input.onchange = on_change
        wrap.append(label + " ", input)
        return wrap

    def checkbox(values, key, name):
        # NOTE: A function per box, so each handler keeps its own name.
        wrap = document.createElement("label")
        box = document.createElement("input")
        box.type = "checkbox"
        box.checked = values[key].includes(name)

        def on_change():
            if box.checked:
                values[key] = values[key].concat([name])
            else:
                values[key] = values[key].filter(lambda v: v != name)
            draw_chart()
        box.onchange = on_change
        wrap.append(box, " " + name)
        return wrap

    def checkboxes(values, key, names):
        return [checkbox(values, key, name) for name in names]

    def render_filters(name):
        options = charts[name].options
        values = charts[name].values
        parts = [fieldset("Dates", [date_input(values, "start_date", "From"), date_input(values, "end_date", "To")])]
        if options.submission_types is not undefined and options.submission_types is not None and len(options.submission_types):
            parts.append(fieldset("Submission Type", checkboxes(values, "submission_types", options.submission_types)))
        if options.control_types:
            parts.append(fieldset("Control Type", checkboxes(values, "include", [c.name for c in options.control_types])))
        if options.clientlabs:
            parts.append(fieldset("Client", checkboxes(values, "clientlabs", options.clientlabs)))
        if options.turnaround_types:
            turnaround = document.createElement("select")
            for kind in options.turnaround_types:
                turnaround.add(window.Option(kind, kind))
            turnaround.value = values.submission_type

            def on_turnaround():
                values.submission_type = turnaround.value
                draw_chart()
            turnaround.onchange = on_turnaround
            parts.append(fieldset("Submission Type", [turnaround]))
        if options.projects:
            project = document.createElement("select")
            for name_ in options.projects:
                project.add(window.Option(name_, name_))
            project.value = values.project

            def on_project():
                values.project = project.value
                draw_chart()
            project.onchange = on_project
            meta = document.createElement("label")
            box = document.createElement("input")
            box.type = "checkbox"
            box.checked = values.metadata_only

            def on_meta():
                values.metadata_only = box.checked
                draw_chart()
            box.onchange = on_meta
            meta.append(box, " Metadata Only")
            parts.append(fieldset("Project", [project, meta]))
        if options.error:
            status(options.error)
        replace_all(document.getElementById("chart-filters"), parts)
        document.getElementById("chart-print").hidden = name != "cost"
        document.getElementById("chart-save-png").hidden = name == "cost"

    def default_values(options):
        submission_types = None
        if options.submission_types is not undefined and options.submission_types is not None and len(options.submission_types):
            # NOTE: Without a submission type filter the tab uses all submission types, as InfoPane does.
            submission_types = options.submission_types.slice()
        control_types = options.control_types or []
        return {
            "start_date": options.start_date,
            "end_date": options.end_date,
            "submission_types": submission_types,
            "include": [c.name for c in control_types if c.checked],
            "submission_type": "All",
            "clientlabs": (options.clientlabs or []).slice(),
            "project": "",
            "metadata_only": True,
        }

    def show(element):
        for el in [plot_div, report_frame, chart_message]:
            el.hidden = el is not element

    async def draw_chart():
        name = state["current_chart"]
        values = charts[name].values
        if values.start_date > values.end_date:
            # NOTE: Same correction as InfoPane.update_data.
            d = window.Date(values.end_date)
            d.setDate(d.getDate() - 31)
            values.start_date = d.toISOString().slice(0, 10)
            document.getElementById("chart-start_date").value = values.start_date
            status("Start date after end date is not allowed! Setting to " + values.start_date + ".")
        if name == "irida" and values.project:
            show(chart_message)
            chart_message.textContent = "Loading from IRIDA Next…"
        state["chart_request"] += 1
        request = state["chart_request"]
        try:
            result = await window.pywebview.api.chart(name, values)
            if request != state["chart_request"]:
                return  # a newer filter change is already on its way
            has_data = False
            if result.figure:
                await load_plotly()
                fig = window.JSON.parse(result.figure)
                show(plot_div)
                window.Plotly.react(plot_div, fig.data, fig.layout, {"responsive": True})
                has_data = True
            elif result.html is not undefined:
                show(report_frame)
                report_frame.srcdoc = result.html
                has_data = result.has_data
            else:
                show(chart_message)
                chart_message.textContent = result.message
            for id in ["chart-save-png", "chart-save-data", "chart-print"]:
                document.getElementById(id).disabled = not has_data
        except Exception as err:
            status("Couldn't draw " + name + ": " + error_text(err))

    async def open_tab(name):
        for button in window.Array.prototype.slice.call(document.querySelectorAll("#tabs button")):
            button.classList.toggle("active", button.dataset.tab == name)
        document.getElementById("tab-submissions").hidden = name != "submissions"
        document.getElementById("tab-chart").hidden = name == "submissions"
        if name == "submissions":
            return
        state["current_chart"] = name
        try:
            if charts[name] is undefined:
                options = await window.pywebview.api.chart_options(name)
                charts[name] = {"options": options, "values": default_values(options)}
            render_filters(name)
            await draw_chart()
        except Exception as err:
            window.console.error(err)
            status("Couldn't open " + name + ": " + error_text(err))

    def tab_button(button):
        def on_click():
            open_tab(button.dataset.tab)
        button.addEventListener("click", on_click)

    for button in window.Array.prototype.slice.call(document.querySelectorAll("#tabs button")):
        tab_button(button)

    async def save_png():
        url = await window.Plotly.toImage(plot_div, {"format": "png", "width": 1600, "height": 900})
        name = state["current_chart"]
        result = await window.pywebview.api.save_chart_png(name, charts[name].values, url)
        status(result.message)

    async def save_data():
        name = state["current_chart"]
        result = await window.pywebview.api.save_chart_data(name, charts[name].values)
        status(result.message)

    def print_report():
        window.pywebview.api.print_report(charts[state["current_chart"]].values)

    document.getElementById("chart-save-png").onclick = save_png
    document.getElementById("chart-save-data").onclick = save_data
    document.getElementById("chart-print").onclick = print_report

    # ── Start-up ─────────────────────────────────────────────────────────────

    async def on_manage():
        manage = document.getElementById("manage")
        name = manage.value
        manage.value = ""
        if name:
            await window.pywebview.api.open_manager(name)

    async def on_search():
        search = document.getElementById("search")
        name = search.value
        search.value = ""
        if name:
            await window.pywebview.api.open_search(name)

    async def on_help():
        help = document.getElementById("help")
        item = help.value
        help.value = ""
        if not item:
            return
        result = await window.pywebview.api.help(item)
        if result is not None and result.message:
            status(result.message)

    async def on_import():
        result = await window.pywebview.api.import_submission()
        if result is not None and result.message:
            status(result.message)

    async def on_export():
        result = await window.pywebview.api.export_submissions()
        if result is not None and result.message:
            status(result.message)

    def previous_page():
        load(state["page"] - 1)

    def next_page():
        load(state["page"] + 1)

    async def init():
        info = await window.pywebview.api.app_info()
        document.getElementById("title").textContent = "Submissions App TNG (v" + info.version + ") - " + info.database
        document.getElementById("prev").onclick = previous_page
        document.getElementById("next").onclick = next_page
        manage = document.getElementById("manage")
        for name in await window.pywebview.api.list_managables():
            manage.add(window.Option(name, name))
        manage.onchange = on_manage
        document.getElementById("import").onclick = on_import
        document.getElementById("search").onchange = on_search
        document.getElementById("export").onclick = on_export
        document.getElementById("help").onchange = on_help
        await load(1)

    if window.pywebview and window.pywebview.api and window.pywebview.api.app_info:
        init()
    else:
        window.addEventListener("pywebviewready", init)

    # NOTE: Drag-and-drop import. The drop itself is handled in Python (Api._on_drop), which gets the real file path.
    def on_dragover(e):
        e.preventDefault()
        document.body.classList.add("dropping")

    def on_dragleave(e):
        if not e.relatedTarget:
            document.body.classList.remove("dropping")

    def on_drop():
        document.body.classList.remove("dropping")

    document.addEventListener("dragover", on_dragover)
    document.addEventListener("dragleave", on_dragleave)
    document.addEventListener("drop", on_drop)


# NOTE: Compiled once, when this module is imported.
MAIN_PAGE_JS = py2js(main_page_script) + "\nmain_page_script();\n"