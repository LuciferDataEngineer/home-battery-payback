const STATE_ORDER = ["SA", "NSW", "WA", "ACT", "QLD", "VIC", "TAS", "NT"];
const REGION_ORDER = ["SA1", "NSW1", "QLD1", "VIC1", "TAS1"];
const REGION_NAME = {
  SA1: "South Australia",
  NSW1: "New South Wales",
  QLD1: "Queensland",
  VIC1: "Victoria",
  TAS1: "Tasmania",
};
const COLOURS = ["#2ee6c7", "#7eb6ff", "#f5b942", "#ff8a5b", "#c9a0ff"];

const state = {
  data: null,
  tab: "overview",
  size: 10,
  scenario: "current",
  focus: "ALL",
};

const money = new Intl.NumberFormat("en-AU", {
  style: "currency",
  currency: "AUD",
  maximumFractionDigits: 0,
});
const num = new Intl.NumberFormat("en-AU", { maximumFractionDigits: 1 });

function $(id) {
  return document.getElementById(id);
}

function payRows(size, scenario) {
  return REGION_ORDER.map((region) =>
    state.data.payback.find(
      (row) => row.region === region && row.usable_kwh === size && row.scenario === scenario,
    ),
  );
}

function showTab(name) {
  state.tab = name;
  document.querySelectorAll("nav button").forEach((button) => {
    const on = button.dataset.tab === name;
    button.classList.toggle("active", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.dataset.page === name);
  });
  // Hidden canvases report a zero width. Draw only after the page is visible.
  requestAnimationFrame(drawActive);
}

function drawActive() {
  if (state.tab === "overview") drawMonths();
  if (state.tab === "where") {
    drawUptake();
    drawPostcodes();
  }
  if (state.tab === "payback") {
    drawPayback();
    drawCut();
    renderPayKpis();
  }
  if (state.tab === "prices") {
    drawSpread();
    drawHourly();
  }
}

function fit(canvas) {
  const width = canvas.parentElement.clientWidth - 8;
  const height = canvas.height;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(320, width) * ratio;
  canvas.height = height * ratio;
  canvas.style.height = `${height}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width: canvas.width / ratio, height };
}

function drawBars(canvas, labels, values, colours, format) {
  const { ctx, width, height } = fit(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { l: 44, r: 12, t: 16, b: 64 };
  const max = Math.max(...values, 1) * 1.15;
  const slot = (width - pad.l - pad.r) / values.length;
  ctx.font = "12px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  values.forEach((value, i) => {
    const barW = Math.min(46, slot * 0.62);
    const x = pad.l + slot * i + (slot - barW) / 2;
    const h = ((height - pad.t - pad.b) * value) / max;
    const y = height - pad.b - h;
    ctx.fillStyle = colours[i] || COLOURS[0];
    ctx.beginPath();
    ctx.roundRect(x, y, barW, h, 6);
    ctx.fill();
    ctx.fillStyle = "#e8eef6";
    ctx.fillText(format(value), x + barW / 2, y - 6);
    ctx.save();
    ctx.translate(x + barW / 2, height - 18);
    ctx.rotate(-0.5);
    ctx.fillStyle = "#9aabbd";
    ctx.fillText(labels[i], 0, 0);
    ctx.restore();
  });
}

function drawGrouped(canvas, labels, a, b, nameA, nameB) {
  const { ctx, width, height } = fit(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { l: 44, r: 12, t: 28, b: 64 };
  const max = Math.max(...a, ...b, 1) * 1.18;
  const slot = (width - pad.l - pad.r) / labels.length;
  ctx.font = "12px Segoe UI, sans-serif";
  const sample = ctx.measureText("0123456789.");
  const ascent = sample.actualBoundingBoxAscent || 9;
  const descent = sample.actualBoundingBoxDescent || 2;
  const labelLine = Math.ceil(ascent + descent + 3);
  ctx.textAlign = "center";
  labels.forEach((label, i) => {
    const barW = Math.min(18, slot * 0.28);
    const base = pad.l + slot * i + slot / 2;
    const drawn = [a[i], b[i]].map((value, series) => {
      const x = base + (series === 0 ? -barW - 2 : 2);
      const h = ((height - pad.t - pad.b) * value) / max;
      const y = height - pad.b - h;
      ctx.fillStyle = series === 0 ? "#2ee6c7" : "#f5b942";
      ctx.beginPath();
      ctx.roundRect(x, y, barW, Math.max(h, 1), 4);
      ctx.fill();
      return { text: num.format(value), cx: x + barW / 2, baseline: y - 4, top: y };
    });
    // The paired bars are only a few pixels apart, so labels on one baseline
    // collide. Lift the longer payback by a line, including short pairs such
    // as 9.3 and 9.8 that would otherwise sit a hair apart.
    const box = (item) => {
      const w = ctx.measureText(item.text).width;
      return {
        left: item.cx - w / 2,
        right: item.cx + w / 2,
        top: item.baseline - ascent,
        bottom: item.baseline + descent,
      };
    };
    const crowded = (p, q) =>
      p.left < q.right + 8 && q.left < p.right + 8 && p.top < q.bottom + 2 && q.top < p.bottom + 2;
    const higher = drawn[0].top <= drawn[1].top ? 0 : 1;
    const legendClearance = 15 + descent + 4;
    const fitsAboveLegend = () => drawn[higher].baseline - labelLine - ascent >= legendClearance;
    if (fitsAboveLegend()) drawn[higher].baseline -= labelLine;
    let guard = 0;
    while (crowded(box(drawn[0]), box(drawn[1])) && fitsAboveLegend() && guard < 3) {
      drawn[higher].baseline -= labelLine;
      guard += 1;
    }
    drawn.forEach((item) => {
      ctx.fillStyle = "#e8eef6";
      ctx.fillText(item.text, item.cx, item.baseline);
    });
    ctx.fillStyle = "#9aabbd";
    ctx.fillText(label, base, height - 28);
  });
  ctx.textAlign = "left";
  const legend = [
    { colour: "#2ee6c7", text: nameA },
    { colour: "#f5b942", text: nameB },
  ];
  let legendX = pad.l;
  let legendBaseline = 15;
  legend.forEach((item) => {
    const textW = ctx.measureText(item.text).width;
    if (legendX > pad.l && legendX + 14 + textW > width - 8) {
      legendX = pad.l;
      legendBaseline += labelLine;
    }
    ctx.fillStyle = item.colour;
    ctx.fillRect(legendX, legendBaseline - 9, 10, 10);
    ctx.fillStyle = "#e8eef6";
    ctx.fillText(item.text, legendX + 14, legendBaseline);
    legendX += 14 + textW + 16;
  });
}

function drawLines(canvas, hours, series) {
  const { ctx, width, height } = fit(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = { l: 48, r: 16, t: 16, b: 36 };
  const values = series.flatMap((item) => item.values);
  const min = Math.min(0, ...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const xAt = (i) => pad.l + ((width - pad.l - pad.r) * i) / (hours.length - 1);
  const yAt = (v) => pad.t + ((max - v) / span) * (height - pad.t - pad.b);
  ctx.strokeStyle = "#2c3e52";
  ctx.beginPath();
  ctx.moveTo(pad.l, yAt(0));
  ctx.lineTo(width - pad.r, yAt(0));
  ctx.stroke();
  ctx.fillStyle = "#9aabbd";
  ctx.font = "12px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  hours.forEach((hour, i) => {
    if (hour % 3 === 0) ctx.fillText(String(hour), xAt(i), height - 14);
  });
  ctx.textAlign = "left";
  series.forEach((item) => {
    ctx.strokeStyle = item.colour;
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    item.values.forEach((value, i) => {
      const x = xAt(i);
      const y = yAt(value);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });
  series.forEach((item, index) => {
    const x = pad.l + index * 150;
    ctx.fillStyle = item.colour;
    ctx.fillRect(x, 4, 12, 8);
    ctx.fillStyle = "#e8eef6";
    ctx.fillText(item.name, x + 16, 12);
  });
}

function table(el, headers, rows) {
  const head = `<tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr>`;
  const body = rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("");
  el.innerHTML = `<table>${head}${body}</table>`;
}

function drawMonths() {
  const months = state.data.months;
  drawBars(
    $("chart-months"),
    months.map((row) => row.label.replace(" 20", " ")),
    months.map((row) => row.installs),
    months.map((row) => (row.label.startsWith("Apr") ? "#f5b942" : row.label.startsWith("May") ? "#ff6b6b" : row.provisional ? "#4d6278" : "#2ee6c7")),
    (value) => num.format(value),
  );
  table(
    $("table-months"),
    ["Month", "Validated batteries", "Still being lodged?"],
    months.map((row) => [row.label, num.format(row.installs), row.provisional ? "Yes" : "Mostly complete"]),
  );
}

function drawUptake() {
  const rows = STATE_ORDER.map((code) => state.data.states.find((row) => row.code === code));
  drawBars(
    $("chart-uptake"),
    rows.map((row) => row.code),
    rows.map((row) => row.per_1000),
    rows.map((row) => (state.focus !== "ALL" && row.code !== state.focus ? "#355068" : colourFor(row.per_1000))),
    (value) => num.format(value),
  );
  table(
    $("table-states"),
    ["State", "Batteries", "Homes in 2021", "Per 1,000 homes", "Solar systems", "Storage GWh"],
    rows.map((row) => [
      row.name,
      num.format(row.batteries),
      num.format(row.dwellings),
      num.format(row.per_1000),
      num.format(row.solar),
      num.format(row.gwh),
    ]),
  );
}

function drawPostcodes() {
  const rows = state.data.postcodes_by_solar;
  drawBars(
    $("chart-postcodes"),
    rows.map((row) => row.postcode),
    rows.map((row) => row.per_1000_solar),
    rows.map(() => "#7eb6ff"),
    (value) => num.format(value),
  );
  table(
    $("table-postcodes"),
    ["Postcode", "State", "Batteries", "Solar systems", "Batteries per 1,000 solar", "Homes in 2021"],
    rows.map((row) => [
      row.postcode,
      row.state,
      num.format(row.batteries),
      num.format(row.solar),
      num.format(row.per_1000_solar),
      num.format(row.dwellings),
    ]),
  );
}

function drawPayback() {
  const rows = payRows(state.size, state.scenario);
  $("pay-title").textContent =
    state.scenario === "current"
      ? "South Australia is the only place close to a 10-year payback"
      : "A smaller discount from January 2027 lengthens every payback";
  drawBars(
    $("chart-payback"),
    rows.map((row) => REGION_NAME[row.region].replace("South ", "S. ").replace("New South Wales", "NSW").replace("Queensland", "Qld")),
    rows.map((row) => row.payback_years),
    rows.map((row) => (row.payback_years < 12 ? "#f5b942" : "#ff6b6b")),
    (value) => `${num.format(value)} yrs`,
  );
  table(
    $("table-payback"),
    ["Region", "Price after discount", "Earned per year", "Years to pay back"],
    rows.map((row) => [
      REGION_NAME[row.region],
      money.format(row.household_price_aud),
      money.format(row.annual_value_aud),
      num.format(row.payback_years),
    ]),
  );
}

function drawCut() {
  const current = payRows(state.size, "current");
  const cut = payRows(state.size, "cut");
  drawGrouped(
    $("chart-cut"),
    current.map((row) => row.region.replace("1", "")),
    current.map((row) => row.payback_years),
    cut.map((row) => row.payback_years),
    "Today's discount",
    "From January 2027",
  );
  table(
    $("table-cut"),
    ["Region", "Years today", "Years after the next cut", "Extra years"],
    current.map((row, i) => [
      REGION_NAME[row.region],
      num.format(row.payback_years),
      num.format(cut[i].payback_years),
      num.format(cut[i].payback_years - row.payback_years),
    ]),
  );
}

function drawSpread() {
  const rows = REGION_ORDER.map((region) => state.data.regions.find((row) => row.region === region));
  drawBars(
    $("chart-spread"),
    rows.map((row) => REGION_NAME[row.region].split(" ")[0]),
    rows.map((row) => row.avg_spread),
    COLOURS,
    (value) => `$${num.format(value)}`,
  );
  table(
    $("table-spread"),
    ["Region", "Gap, $ per MWh", "Midday charge", "Evening discharge", "Negative prices", "Earned by 10 kWh"],
    rows.map((row) => [
      REGION_NAME[row.region],
      num.format(row.avg_spread),
      num.format(row.avg_charge),
      num.format(row.avg_discharge),
      `${num.format(row.negative_pct)}%`,
      money.format(row.annual_value_10kwh),
    ]),
  );
}

function drawHourly() {
  const hours = [...Array(24).keys()];
  const wanted = ["SA1", "VIC1", "NSW1", "TAS1"];
  const series = wanted.map((region, index) => ({
    name: REGION_NAME[region].split(" ")[0],
    colour: COLOURS[index],
    values: hours.map(
      (hour) => state.data.hourly.find((row) => row.region === region && row.hour_ending === hour).avg_rrp,
    ),
  }));
  drawLines($("chart-hourly"), hours, series);
  table(
    $("table-hourly"),
    ["Hour ending", ...wanted.map((region) => REGION_NAME[region].split(" ")[0])],
    hours.map((hour) => [
      `${hour}:00`,
      ...wanted.map((region) =>
        num.format(state.data.hourly.find((row) => row.region === region && row.hour_ending === hour).avg_rrp),
      ),
    ]),
  );
}

function colourFor(value) {
  const values = state.data.states.map((row) => row.per_1000);
  const t = (value - Math.min(...values)) / (Math.max(...values) - Math.min(...values) || 1);
  const r = Math.round(40 + (46 - 40) * t);
  const g = Math.round(90 + (230 - 90) * t);
  const b = Math.round(110 + (199 - 110) * t);
  return `rgb(${r},${g},${b})`;
}

function project(lon, lat) {
  const minLon = 112;
  const maxLon = 154.5;
  const minLat = -44.2;
  const maxLat = -9.5;
  const x = ((lon - minLon) / (maxLon - minLon)) * 620 + 10;
  const y = ((maxLat - lat) / (maxLat - minLat)) * 520 + 16;
  return [x, y];
}

function ringPath(ring) {
  return ring
    .map((pair, index) => {
      const [x, y] = project(pair[0], pair[1]);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ") + " Z";
}

function geometryPath(geometry) {
  if (geometry.type === "Polygon") return geometry.coordinates.map(ringPath).join(" ");
  return geometry.coordinates.map((polygon) => polygon.map(ringPath).join(" ")).join(" ");
}

async function drawMap() {
  const response = await fetch("assets/aus_states.geojson");
  const geo = await response.json();
  const svg = $("map");
  svg.innerHTML = "";
  const byCode = Object.fromEntries(state.data.states.map((row) => [row.code, row]));
  geo.features.forEach((feature) => {
    const code = feature.properties.code;
    const row = byCode[code];
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", geometryPath(feature.geometry));
    path.setAttribute("fill", colourFor(row.per_1000));
    path.dataset.code = code;
    path.addEventListener("mousemove", (event) => showTip(event, row));
    path.addEventListener("mouseleave", hideTip);
    svg.appendChild(path);
  });
  const act = byCode.ACT;
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  const [x, y] = project(149.1, -35.3);
  dot.setAttribute("cx", x);
  dot.setAttribute("cy", y);
  dot.setAttribute("r", 7);
  dot.setAttribute("fill", colourFor(act.per_1000));
  dot.setAttribute("stroke", "#e8eef6");
  dot.addEventListener("mousemove", (event) => showTip(event, act));
  dot.addEventListener("mouseleave", hideTip);
  svg.appendChild(dot);
  $("map-note").textContent =
    "Colour shows batteries per 1,000 homes counted in the 2021 Census. The Australian Capital Territory is the dot near Canberra, because it is too small to see at this scale. Western Australia and the Northern Territory are not on the east-coast wholesale market. Boundaries are a simplified public-domain outline, not a survey map.";
}

function showTip(event, row) {
  const tip = $("tip");
  const nem = row.in_nem ? "" : " Not on the east-coast wholesale market.";
  tip.hidden = false;
  tip.innerHTML = `<strong>${row.name}</strong><br>${num.format(row.per_1000)} batteries per 1,000 homes<br>${num.format(row.batteries)} batteries, ${num.format(row.gwh)} GWh.${nem}`;
  const wrap = tip.parentElement.getBoundingClientRect();
  tip.style.left = `${event.clientX - wrap.left + 12}px`;
  tip.style.top = `${event.clientY - wrap.top + 12}px`;
}

function hideTip() {
  $("tip").hidden = true;
}

function renderPayKpis() {
  const row = payRows(state.size, state.scenario).find((item) => item.region === "SA1");
  const tas = payRows(state.size, state.scenario).find((item) => item.region === "TAS1");
  $("pay-kpis").innerHTML = `
    <article class="kpi amber"><div class="value">${num.format(row.payback_years)} years</div><div class="label">South Australia, ${state.size} kWh</div><div class="detail">${money.format(row.household_price_aud)} after the discount, earning ${money.format(row.annual_value_aud)} a year from price swings.</div></article>
    <article class="kpi red"><div class="value">${num.format(tas.payback_years)} years</div><div class="label">Tasmania, same battery</div><div class="detail">The smallest price swings in the east-coast market, and the fewest batteries per 1,000 homes on that market.</div></article>
    <article class="kpi ${state.scenario === "cut" ? "amber" : "green"}"><div class="value">${money.format(row.household_price_aud)}</div><div class="label">${state.scenario === "cut" ? "Price if the January 2027 discount applied today" : "Price households are paying now"}</div><div class="detail">${state.size === 10 ? "Battery only, national average, for a home that already has a compatible inverter." : "Larger batteries get a smaller discount on the kilowatt-hours above 14."}</div></article>`;
}

function renderStatic() {
  const data = state.data;
  $("banner").textContent = data.headline;
  $("kpis").innerHTML = data.kpis
    .map(
      (kpi) =>
        `<article class="kpi ${kpi.status}"><div class="value">${kpi.value}</div><div class="label">${kpi.label}</div><div class="detail">${kpi.detail}</div></article>`,
    )
    .join("");
  ["overview", "where", "payback", "prices", "action"].forEach((name) => {
    $(`means-${name}`).innerHTML = `<strong>What this means. </strong>${data.means[name]}`;
  });
  $("actions").innerHTML = [
    ["Households", "In South Australia, wholesale swings alone are close to a 10-year payback. Everywhere else they are not. The larger saving is usually storing your own solar. Ask for the price after the federal discount, and do not count on two full cycles a day."],
    ["Retailers", "South Australia and Victoria have the most time with negative midday prices. A battery there soaks up surplus solar that the wholesale market is paying to dump. New South Wales has the customers; it does not have the widest price gap."],
    ["Governments", "May 2026 already showed that tightening the discount slows installations. The next scheduled step, in January 2027, adds about half a year to a South Australian wholesale payback and about two years in Tasmania. It does not change the ranking. A deeper cut, still being drafted for the budget, is not in these numbers."],
  ]
    .map(
      ([title, body]) =>
        `<article class="action"><h2>${title}</h2><p>${body}</p></article>`,
    )
    .join("");
  $("pills-state").innerHTML = ["ALL", ...STATE_ORDER]
    .map(
      (code) =>
        `<button type="button" data-state="${code}" class="${code === "ALL" ? "active" : ""}">${code === "ALL" ? "All states" : code}</button>`,
    )
    .join("");
  $("pills-size").innerHTML = [10, 20]
    .map(
      (size) =>
        `<button type="button" data-size="${size}" class="${size === 10 ? "active" : ""}">${size} kWh</button>`,
    )
    .join("");
  $("pills-scenario").innerHTML = [
    ["current", "Today's discount"],
    ["cut", "January 2027 discount"],
  ]
    .map(
      ([id, label]) =>
        `<button type="button" data-scenario="${id}" class="${id === "current" ? "active" : ""}">${label}</button>`,
    )
    .join("");
  const sources = data.sources
    .map((source) => `<li>${source.name}. ${source.licence}. As at ${source.as_at}.</li>`)
    .join("");
  $("footer").innerHTML = `<p>Times on the price charts are ${data.assumptions.time_label}. Figures prepared ${data.as_of_label}.</p><ul>${sources}</ul>`;
}

function bind() {
  document.querySelectorAll("nav button").forEach((button) => {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  });
  $("pills-state").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.focus = button.dataset.state;
    $("pills-state").querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    drawUptake();
  });
  $("pills-size").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.size = Number(button.dataset.size);
    $("pills-size").querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    drawPayback();
    drawCut();
    renderPayKpis();
  });
  $("pills-scenario").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    state.scenario = button.dataset.scenario;
    $("pills-scenario").querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    drawPayback();
    renderPayKpis();
  });
  window.addEventListener("resize", () => drawActive());
}

async function main() {
  const response = await fetch("data/dashboard.json");
  state.data = await response.json();
  renderStatic();
  await drawMap();
  bind();
  showTab("overview");
}

main().catch((error) => {
  document.body.insertAdjacentHTML("beforeend", `<p class="banner">The figures could not be loaded. ${error.message}</p>`);
});
