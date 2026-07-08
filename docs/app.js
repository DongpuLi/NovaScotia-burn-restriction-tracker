const DEFAULT_COUNTY_ID = "Halifax-County";

let countiesById = {};
let selectedCountyId = DEFAULT_COUNTY_ID;
let countyFireWeatherById = {};
let siteMode = "active";
let predictionsByCounty = {};
let metricsByCounty = {};
let historyByCounty = {};

function emoji(level) {
  if (level === "green") return "🟢";
  if (level === "yellow") return "🟡";
  if (level === "red") return "🔴";
  return "❔";
}

function label(level) {
  return level ? level.toUpperCase() : "UNKNOWN";
}

function normalizeLevel(level) {
  const value = (level || "unknown").toLowerCase();

  if (["green", "yellow", "red", "offseason"].includes(value))
    return value;

  return "unknown";
}

function countyIdToSvgId(countyId) {
  return countyId.replace("-County", "");
}

function getHalifaxNow() {
  return new Date(
    new Date().toLocaleString("en-US", {
      timeZone: "America/Halifax",
    })
  );
}

function getDisplayStatus(county) {
  const now = getHalifaxNow();
  const hour = now.getHours();
  const officialLevel = normalizeLevel(county?.level);

  if (hour >= 8 && hour < 14) {
    return {
      displayLevel: "red",
      officialLevel,
      status: "Burning is not allowed.",
      window:
        `Between 8 a.m. and 2 p.m., the display is RED for all counties. ` +
        `Stored official status: ${emoji(officialLevel)} ${label(officialLevel)}.`,
    };
  }

  if (officialLevel === "green") {
    return {
      displayLevel: "green",
      officialLevel,
      status: "Burning allowed between 2 p.m. and 8 a.m.",
      window: "Current burn window: 2 p.m. – 8 a.m.",
    };
  }

  if (officialLevel === "yellow") {
    return {
      displayLevel: "yellow",
      officialLevel,
      status: "Burning allowed between 7 p.m. and 8 a.m.",
      window: "Current burn window: 7 p.m. – 8 a.m.",
    };
  }

  if (officialLevel === "red") {
    return {
      displayLevel: "red",
      officialLevel,
      status: "Burning is not allowed.",
      window: "No burn window.",
    };
  }

  return {
    displayLevel: "unknown",
    officialLevel,
    status: "Official status unavailable.",
    window: "",
  };
}

function setTheme(level) {

  if (siteMode === "offseason") {
    document.body.className = "";
    document.body.classList.add("status-offseason");

    const banner = document.getElementById("offseason-banner");
    if (banner) banner.hidden = false;

    const predictionCard = document.getElementById("prediction-card");
    if (predictionCard) predictionCard.style.display = "none";

    return;
  }

  const allowed = ["green", "yellow", "red"];
  const theme = allowed.includes(level) ? level : "unknown";

  document.body.className = "";
  document.body.classList.add(`status-${theme}`);

  const banner = document.getElementById("offseason-banner");
  if (banner) banner.hidden = true;

  const predictionCard = document.getElementById("prediction-card");
  if (predictionCard) predictionCard.style.display = "";
}

function formatDate(value) {
  if (!value) return "";

  const date = new Date(value + "T12:00:00");

  return date.toLocaleDateString("en-CA", {
    weekday: "short",
    month: "short",
    day: "numeric",
    timeZone: "America/Halifax",
  });
}

function formatUpdated(value) {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleString("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Halifax",
  });
}

async function loadJSON(path, fallback = null) {
  const response = await fetch(path + "?t=" + Date.now());

  if (!response.ok) {
    if (fallback !== null) return fallback;
    throw new Error(`Failed to load ${path}: ${response.status}`);
  }

  return await response.json();
}

function safeCssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function levelFill(level) {
  if (level === "green") return "#22c55e";
  if (level === "yellow") return "#facc15";
  if (level === "red") return "#ef4444";
  return "#9ca3af";
}

function applyFillToSvgElement(el, level) {
  const fill = levelFill(level);

  el.classList.add("county-shape", `county-${level}`);
  el.setAttribute("data-level", level);
  el.setAttribute("fill", fill);
  el.style.fill = fill;
  el.style.cursor = "pointer";

  el.querySelectorAll("path, polygon, polyline").forEach((child) => {
    child.classList.add("county-shape", `county-${level}`);
    child.setAttribute("data-level", level);
    child.setAttribute("fill", fill);
    child.style.fill = fill;
    child.style.cursor = "pointer";
  });
}

function updateSelectedCounty(countyId) {
  const county = countiesById[countyId] || countiesById[DEFAULT_COUNTY_ID];
  if (!county) return;

  selectedCountyId = county.id;

  const display = getDisplayStatus(county);
  setTheme(display.displayLevel);

  const countyNameEl = document.getElementById("county-name");
  if (countyNameEl) countyNameEl.textContent = county.name;

  const today = document.getElementById("today");
  if (today) {
    today.textContent = `${emoji(display.displayLevel)} ${label(display.displayLevel)}`;
    today.className = "today " + display.displayLevel;
  }

  const statusEl = document.getElementById("status");
  if (statusEl) statusEl.textContent = display.status;

  const windowEl = document.getElementById("window");
  if (windowEl) windowEl.textContent = display.window;

  const selectedEl = document.getElementById("selected-county");
  if (selectedEl) {
    selectedEl.textContent =
      `Selected: ${county.name} · Official stored status: ` +
      `${emoji(display.officialLevel)} ${label(display.officialLevel)}`;
  }
const predictionTitle = document.getElementById("prediction-title");
if (predictionTitle) {
  predictionTitle.textContent = `Experimental 7-day ${county.name} risk outlook`;
}

const historyTitle = document.getElementById("history-title");
if (historyTitle) {
  historyTitle.textContent = `${county.name} history`;
}
  document.querySelectorAll(".county-selected").forEach((el) => {
    el.classList.remove("county-selected");
  });

  const svgId = countyIdToSvgId(county.id);
  const svgEl = document.querySelector(`#${safeCssEscape(svgId)}`);
  if (svgEl) svgEl.classList.add("county-selected");

  renderOfficialFireWeather(county.id);
  renderPredictions(predictionsByCounty[county.id] || []);
  renderMetrics(metricsByCounty[county.id] || null);
  renderHistory(historyByCounty[county.id] || []);
}

async function loadMap(countiesData) {
  const container = document.getElementById("map-container");
  if (!container) return;

  try {
    const response = await fetch("assets/ns-counties-map.svg?t=" + Date.now());

    if (!response.ok) {
      throw new Error(`Failed to load map SVG: ${response.status}`);
    }

    const svgText = await response.text();
    container.innerHTML = svgText;

    countiesById = {};

    countiesData.counties.forEach((county) => {
      const level = normalizeLevel(county.level);
      countiesById[county.id] = { ...county, level };

      const svgId = countyIdToSvgId(county.id);
      const el = container.querySelector(`#${safeCssEscape(svgId)}`);
      if (!el) return;

      applyFillToSvgElement(el, level);

      el.addEventListener("click", () => {
        updateSelectedCounty(county.id);
      });

      el.querySelectorAll("path, polygon, polyline").forEach((child) => {
        child.addEventListener("click", (event) => {
          event.stopPropagation();
          updateSelectedCounty(county.id);
        });
      });
    });

    updateSelectedCounty(DEFAULT_COUNTY_ID);
  } catch (error) {
    container.textContent = error.message;
    console.error(error);
  }
}

function renderPredictions(predictions) {
  const el = document.getElementById("predictions");
  if (!el) return;

  el.innerHTML = "";

  if (!predictions || predictions.length === 0) {
    el.textContent = "No predictions available yet.";
    return;
  }

  predictions.forEach((item) => {
    const level = normalizeLevel(item.predicted_level);
    const row = document.createElement("div");
    row.className = "prediction-row";

    row.innerHTML = `
      <div>
        <div class="prediction-main">${formatDate(item.date)}</div>
        <div class="prediction-sub">${item.reason || ""}</div>
      </div>
      <div>
        <div class="${level}">
          ${emoji(level)} ${label(level)}
        </div>
        <div class="prediction-sub">
          ${item.confidence ?? ""}% confidence
        </div>
      </div>
    `;

    el.appendChild(row);
  });
}

function renderMetrics(metrics) {
  const el = document.getElementById("metrics");
  if (!el) return;

  if (!metrics || !metrics.total_evaluated) {
    el.textContent = "Not enough evaluated predictions yet.";
    return;
  }

  const accuracy = Math.round(metrics.accuracy * 100);

  el.innerHTML = `
    <div><strong>${accuracy}%</strong> accuracy</div>
    <div>${metrics.correct} / ${metrics.total_evaluated} predictions correct</div>
  `;
}

function renderHistory(history) {
  const historyEl = document.getElementById("history");
  if (!historyEl) return;

  historyEl.innerHTML = "";

  if (!history || history.length === 0) {
    historyEl.textContent = "No history yet.";
    return;
  }

  history.slice().reverse().forEach((item) => {
    const level = normalizeLevel(item.level);
    const row = document.createElement("div");
    row.className = "row";

    row.innerHTML = `
      <span>${item.date}</span>
      <span>${item.county || "County"}</span>
      <span class="${level}">
        ${emoji(level)} ${label(level)}
      </span>
    `;

    historyEl.appendChild(row);
  });
}

function renderOfficialFireWeather(countyId) {
  const titleEl = document.getElementById("official-fire-weather-title");
  const el = document.getElementById("official-fire-weather");

  if (!el) return;

  const county = countiesById[countyId] || countiesById[DEFAULT_COUNTY_ID];
  const record = countyFireWeatherById[countyId];

  if (titleEl && county) {
    titleEl.textContent = `Official ${county.name} Fire Weather Forecast`;
  }

  if (!record) {
    el.textContent = "No official fire weather data available for this county yet.";
    return;
  }

  function value(v) {
    return v === null || v === undefined ? "—" : v;
  }

  el.innerHTML = `
    <div class="fire-weather-item">
      <strong>${value(record.fwi)}</strong>
      <span>FWI</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.ffmc)}</strong>
      <span>FFMC</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.dmc)}</strong>
      <span>DMC</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.dc)}</strong>
      <span>DC</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.isi)}</strong>
      <span>ISI</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.bui)}</strong>
      <span>BUI</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.temp_c)}°C</strong>
      <span>Max station temperature</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.rh_percent)}%</strong>
      <span>Lowest station RH</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.wind_speed_kph)} kph</strong>
      <span>Max station wind</span>
    </div>

    <div class="fire-weather-item">
      <strong>${value(record.rain_24h_mm)} mm</strong>
      <span>Max 24h rain</span>
    </div>

    <div class="fire-weather-stations">
      Stations used: ${(record.stations || []).join(", ") || "—"}
    </div>
  `;
}

async function main() {
  try {
    const latest = await loadJSON("latest.json");
    siteMode = latest.site_mode || "active";

    const counties = await loadJSON("counties.json", { counties: [] });

    predictionsByCounty = await loadJSON("county_prediction.json", {});
    metricsByCounty = await loadJSON("county_metrics.json", {});
    historyByCounty = await loadJSON("county_history.json", {});
    countyFireWeatherById = await loadJSON("county_fire_weather.json", {});

    const updatedEl = document.getElementById("updated");
    if (updatedEl) {
      updatedEl.textContent = latest.updated_at
        ? `Last updated: ${formatUpdated(latest.updated_at)}`
        : "";
    }

    const source = document.getElementById("source");
    if (source) {
      source.href = latest.source || "https://novascotia.ca/burnsafe/";
    }

    await loadMap(counties);
  } catch (error) {
    setTheme("unknown");

    const today = document.getElementById("today");
    if (today) today.textContent = "Error";

    const status = document.getElementById("status");
    if (status) status.textContent = error.message;

    console.error(error);
  }
}

main();