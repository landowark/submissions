// Chart and report tabs: filters on top, then a plotly chart or an html report. Filters are kept per tab.
const charts = {};          // tab name -> {options, values}
let currentChart = null;
let chartRequest = 0;
let plotlyLoading = null;

const plotDiv = document.getElementById('chart-plot');
const reportFrame = document.getElementById('chart-report');
const chartMessage = document.getElementById('chart-message');

function loadPlotly() {
    plotlyLoading ??= new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'plotly.min.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Could not load plotly.min.js'));
      document.head.append(script);
    });
    return plotlyLoading;
  }

function fieldset(label, ...children) {
    const box = document.createElement('fieldset');
    const legend = document.createElement('legend');
    legend.textContent = label;
    box.append(legend, ...children);
    return box;
  }

function dateInput(values, key, label) {
    const wrap = document.createElement('label');
    const input = document.createElement('input');
    input.type = 'date';
    input.id = `chart-${key}`;
    input.value = values[key];
    input.onchange = () => { values[key] = input.value; drawChart(); };
    wrap.append(`${label} `, input);
    return wrap;
  }

function checkboxes(values, key, names) {
    return names.map((name) => {
      const wrap = document.createElement('label');
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = values[key].includes(name);
      box.onchange = () => {
        values[key] = box.checked ? [...values[key], name] : values[key].filter((v) => v !== name);
        drawChart();
      };
      wrap.append(box, ` ${name}`);
      return wrap;         
    });
}

function renderFilters(name) {
    const { options, values } = charts[name];
    const parts = [fieldset('Dates', dateInput(values, 'start_date', 'From'), dateInput(values, 'end_date', 'To'))];
    if (options.submission_types?.length) parts.push(fieldset('Submission Type', ...checkboxes(values, 'submission_types', options.submission_types)));
    if (options.control_types) parts.push(fieldset('Control Type', ...checkboxes(values, 'include', options.control_types.map((c) => c.name))));
    if (options.clientlabs) parts.push(fieldset('Client', ...checkboxes(values, 'clientlabs', options.clientlabs)));
    if (options.turnaround_types) {
      const select = document.createElement('select');
      for (const type of options.turnaround_types) select.add(new Option(type, type));
      select.value = values.submission_type;
      select.onchange = () => { values.submission_type = select.value; drawChart(); };
      parts.push(fieldset('Submission Type', select));
    }
    if (options.projects) {
      const select = document.createElement('select');
      for (const project of options.projects) select.add(new Option(project, project));
      select.value = values.project;
      select.onchange = () => { values.project = select.value; drawChart(); };
      const meta = document.createElement('label');
      const box = document.createElement('input');
      box.type = 'checkbox';
      box.checked = values.metadata_only;
      box.onchange = () => { values.metadata_only = box.checked; drawChart(); };
      meta.append(box, ' Metadata Only');
      parts.push(fieldset('Project', select, meta));
    }
    if (options.error) status(options.error);
    document.getElementById('chart-filters').replaceChildren(...parts);
    document.getElementById('chart-print').hidden = name !== 'cost';
    document.getElementById('chart-save-png').hidden = name === 'cost';
}

function defaultValues(options) {
    return {
      start_date: options.start_date,
      end_date: options.end_date,
      // NOTE: Without a submission type filter the tab uses all submission types, as InfoPane does.
      submission_types: options.submission_types?.length ? [...options.submission_types] : null,
      include: (options.control_types || []).filter((c) => c.checked).map((c) => c.name),
      submission_type: 'All',
      clientlabs: [...(options.clientlabs || [])],
      project: '',
      metadata_only: true,
    };
}

function show(element) {
    for (const el of [plotDiv, reportFrame, chartMessage]) el.hidden = el !== element;
}

async function drawChart() {
    const name = currentChart;
    const values = charts[name].values;
    if (values.start_date > values.end_date) {
      // NOTE: Same correction as InfoPane.update_data.
      const d = new Date(values.end_date);
      d.setDate(d.getDate() - 31);
      values.start_date = d.toISOString().slice(0, 10);
      document.getElementById('chart-start_date').value = values.start_date;
      status(`Start date after end date is not allowed! Setting to ${values.start_date}.`);
    }
    if (name === 'irida' && values.project) {
      show(chartMessage);
      chartMessage.textContent = 'Loading from IRIDA Next…';
    }
    const request = ++chartRequest;
    try {
      const result = await pywebview.api.chart(name, values);
      if (request !== chartRequest) return; // a newer filter change is already on its way
      let hasData = false;
      if (result.figure) {
        await loadPlotly();
        const fig = JSON.parse(result.figure);
        show(plotDiv);
        Plotly.react(plotDiv, fig.data, fig.layout, { responsive: true });
        hasData = true;
      } else if (result.html !== undefined) {
        show(reportFrame);
        reportFrame.srcdoc = result.html;
        hasData = result.has_data;
      } else {
        show(chartMessage);
        chartMessage.textContent = result.message;
      }
      for (const id of ['chart-save-png', 'chart-save-data', 'chart-print']) document.getElementById(id).disabled = !hasData;
    } catch (err) {
      status(`Couldn't draw ${name}: ${err.message ?? err}`);
    }
  }

async function openTab(name) {
    for (const button of document.querySelectorAll('#tabs button')) button.classList.toggle('active', button.dataset.tab === name);
    document.getElementById('tab-submissions').hidden = name !== 'submissions';
    document.getElementById('tab-chart').hidden = name === 'submissions';
    if (name === 'submissions') return;
    currentChart = name;
    try {
      if (!charts[name]) {
        const options = await pywebview.api.chart_options(name);
        charts[name] = { options, values: defaultValues(options) };
      }
      renderFilters(name);
      await drawChart();
    } catch (err) {
      console.error(err);
      status(`Couldn't open ${name}: ${err.message ?? err}`);
    }
  }

for (const button of document.querySelectorAll('#tabs button')) button.addEventListener('click', () => openTab(button.dataset.tab));

document.getElementById('chart-save-png').onclick = async () => {
    const url = await Plotly.toImage(plotDiv, { format: 'png', width: 1600, height: 900 });
    const result = await pywebview.api.save_chart_png(currentChart, charts[currentChart].values, url);
    status(result.message);
  };
document.getElementById('chart-save-data').onclick = async () => {
    const result = await pywebview.api.save_chart_data(currentChart, charts[currentChart].values);
    status(result.message);
  };
document.getElementById('chart-print').onclick = () => pywebview.api.print_report(charts[currentChart].values);
