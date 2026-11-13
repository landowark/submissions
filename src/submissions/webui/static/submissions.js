// Submissions tab: paged tree of submissions -> runs -> procedures, with a right-click menu.
const state = { page: 1, pages: 1 };
const tbody = document.querySelector('#submissions tbody');
const menu = document.getElementById('context-menu');

function cell(text, cls) {
    const td = document.createElement('td');
    td.textContent = text ?? '';
    if (cls) td.className = cls;
    return td;
  }

function makeRow({ kind, id, name, cols = ['', '', ''], depth, children = [] }) {
    const tr = document.createElement('tr');
    tr.className = `${kind} depth-${depth}`;
    Object.assign(tr.dataset, { kind, id, name });
    const nameCell = cell('', 'name');
    const toggle = document.createElement('span');
    toggle.className = 'toggle';
    toggle.textContent = children.length ? '\u25B8' : '';
    toggle.addEventListener('click', (e) => { e.stopPropagation(); toggleRow(tr); });
    nameCell.append(toggle, document.createTextNode(name));
    tr.append(nameCell, ...cols.map((c) => cell(c)));
    tr._children = children;
    tr._childRows = null;
    return tr;
}

function childRows(tr) {
    if (tr.dataset.kind === 'submission') {
      return tr._children.map((run) => makeRow({
        kind: 'run', id: run.id, depth: 1, children: run.procedure,
        name: run.approved ? `${run.rsl_plate_number} \u2714` : run.rsl_plate_number,
      }));
    }
    return tr._children.map((proc) => makeRow({ kind: 'procedure', id: proc.id, name: proc.name, depth: 2 }));
}

function collapse(tr) {
    for (const child of tr._childRows || []) { collapse(child); child.remove(); }
    tr._childRows = null;
    if (tr._children.length) tr.querySelector('.toggle').textContent = '\u25B8';
}

function toggleRow(tr) {
    if (!tr._children.length) return;
    if (tr._childRows) return collapse(tr);
    tr._childRows = childRows(tr);
    tr.after(...tr._childRows);
    tr.querySelector('.toggle').textContent = '\u25BE';
}

async function load(page) {
    try {
      const data = await pywebview.api.list_submissions(page);
      Object.assign(state, { page: data.page, pages: data.pages });
      tbody.replaceChildren(...data.rows.map((sub, ii) => {
        const tr = makeRow({
          kind: 'submission', id: sub.id, depth: 0, children: sub.run,
          name: `${sub.submissiontype}-${sub.submitter_plate_id}-${sub.submitted_date}`,
          cols: [sub.submissiontype, sub.clientlab, sub.submitted_date],
        });
        if (ii % 2) tr.classList.add('alt');
        return tr;
      }));
      document.getElementById('page-label').textContent = `${state.page} of ${state.pages}`;
      document.getElementById('prev').disabled = state.page <= 1;
      document.getElementById('next').disabled = state.page >= state.pages;
    } catch (err) {
      status(`Couldn't load submissions: ${err.message ?? err}`);
    }
}

function select(tr) {
    tbody.querySelector('tr.selected')?.classList.remove('selected');
    tr.classList.add('selected');
}

function menuItem(label, enabled, onClick) {
    const li = document.createElement('li');
    li.textContent = label;
    if (!enabled) {
      li.classList.add('disabled');
      li.title = 'Not available in the web UI yet';
    } else if (onClick) {
      li.addEventListener('click', onClick);
    }
    return li;
}

function showMenu(items, tr, x, y) {
    menu.replaceChildren(...items.map((item) => {
      if (!item.options) return menuItem(item.label, item.enabled, () => runAction(tr, item.label));
      const li = menuItem(item.label, item.enabled);
      li.classList.add('parent');
      const sub = document.createElement('ul');
      sub.className = 'menu';
      sub.append(...item.options.map((option) => menuItem(option, item.enabled, () => runAction(tr, item.label, option))));
      li.append(sub);
      return li;
    }));
    menu.hidden = false;
    const r = menu.getBoundingClientRect();
    menu.style.left = `${Math.min(x, innerWidth - r.width - 4)}px`;
    menu.style.top = `${Math.min(y, innerHeight - r.height - 4)}px`;
}

async function runAction(tr, action, option = null) {
    menu.hidden = true;
    let text = null;
    if (action === 'Delete' && !confirm(`Are you sure you want to delete ${tr.dataset.name}?`)) return;
    if (action === 'Add Comment') {
      text = prompt(`Comment on ${tr.dataset.name}:`);
      if (text === null) return;
    }
    try {
      const result = await pywebview.api.run_action(tr.dataset.kind, Number(tr.dataset.id), action, option, text);
      status(result.message);
      if (result.refresh) await load(state.page);
    } catch (err) {
      status(`${action} failed: ${err.message ?? err}`);
    }
}

let statusTimer;
function status(message) {
    const el = document.getElementById('status');
    el.textContent = message;
    el.hidden = false;
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => { el.hidden = true; }, 5000);
}

tbody.addEventListener('click', (e) => { const tr = e.target.closest('tr'); if (tr) select(tr); });
tbody.addEventListener('dblclick', () => status('Show Details moves to the web UI in phase 4.'));
tbody.addEventListener('contextmenu', async (e) => {
    const tr = e.target.closest('tr');
    if (!tr) return;
    e.preventDefault();
    select(tr);
    try {
      showMenu(await pywebview.api.context_menu(tr.dataset.kind, Number(tr.dataset.id)), tr, e.clientX, e.clientY);
    } catch (err) {
      status(`Couldn't build menu: ${err.message ?? err}`);
    }
});
document.addEventListener('click', () => { menu.hidden = true; });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') menu.hidden = true; });

async function init() {
    const info = await pywebview.api.app_info();
    document.getElementById('title').textContent = `Submissions App TNG (v${info.version}) - ${info.database}`;
    document.getElementById('prev').onclick = () => load(state.page - 1);
    document.getElementById('next').onclick = () => load(state.page + 1);
    await load(1);
}

if (window.pywebview?.api?.app_info) init();
else window.addEventListener('pywebviewready', init);