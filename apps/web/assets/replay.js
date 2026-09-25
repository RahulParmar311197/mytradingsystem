const state = {
  token: sessionStorage.getItem("mtsReplayToken") || "",
  role: null,
  session: null,
  playing: false,
  playbackPending: false,
  playbackPollFailures: 0,
  playbackTimer: null,
};
const byId = (id) => document.getElementById(id);
const SVG_NS = "http://www.w3.org/2000/svg";
const MAX_DATASET_BYTES = 5 * 1024 * 1024;

function svgElement(name, attributes = {}) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function notify(message, error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = `notice visible${error ? " error" : ""}`;
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => { notice.className = "notice"; }, 4500);
}

async function request(path, options = {}) {
  if (!state.token) throw new Error("Connect with an API token first.");
  const response = await fetch(path, {
    ...options,
    headers: { "Authorization": `Bearer ${state.token}`, "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status}).`);
  return payload;
}

function setConnection(connected, role = null) {
  state.role = role;
  byId("connectionBadge").textContent = connected ? "Connected" : "Not connected";
  byId("connectionBadge").dataset.state = connected ? "online" : "offline";
  byId("roleBadge").textContent = role ? role.toUpperCase() : "No role";
  const operator = role === "operator";
  const playbackBusy = state.playing || state.playbackPending;
  byId("authoringPanel").hidden = !operator;
  byId("recentSessions").disabled = !connected || playbackBusy;
  byId("refreshSessions").disabled = !connected || playbackBusy;
  byId("refreshPlaybackHistory").disabled = !connected || !state.session;
  byId("sessionId").disabled = playbackBusy;
  byId("sessionForm").querySelector("button").disabled = playbackBusy;
  byId("disconnect").disabled = state.playbackPending;
  byId("datasetForm").querySelectorAll("input, button").forEach((control) => {
    control.disabled = playbackBusy;
  });
  const complete = state.session && state.session.next_index >= state.session.total_events;
  byId("step").disabled = !operator || !state.session || playbackBusy || complete;
  byId("play").disabled = !operator || !state.session || playbackBusy || complete;
  byId("play").dataset.active = playbackBusy;
  byId("pause").disabled = !state.playing;
  byId("seek").disabled = !operator || !state.session || state.playing;
  byId("operatorHint").hidden = operator;
}

function render(session) {
  state.session = session;
  byId("cursor").textContent = session.next_index;
  byId("version").textContent = session.version;
  byId("total").textContent = session.total_events;
  byId("dataset").textContent = session.dataset_sha256;
  const discovered = Array.from(byId("recentSessions").options).find(
    (option) => option.value === session.session_id,
  );
  if (discovered) {
    discovered.textContent = `${session.session_id} · ${session.next_index}/${session.total_events} · v${session.version}`;
  }
  const rows = session.candles || [];
  renderChart(rows);
  const body = byId("candles");
  body.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6; cell.className = "empty"; cell.textContent = "No candles are visible at this cursor.";
    row.appendChild(cell); body.appendChild(row);
  } else {
    rows.forEach((candle) => {
      const row = document.createElement("tr");
      [candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume].forEach((value) => {
        const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
      });
      body.appendChild(row);
    });
  }
  setConnection(true, state.role);
}

function renderChart(sourceRows) {
  const chart = byId("candleChart");
  const description = byId("chartDescription");
  chart.querySelectorAll(":scope > :not(title):not(desc)").forEach((node) => node.remove());
  const rows = sourceRows.slice(-100).map((candle) => ({
    ...candle,
    open: Number(candle.open), high: Number(candle.high), low: Number(candle.low),
    close: Number(candle.close), volume: Number(candle.volume),
  }));
  byId("chartEmpty").hidden = rows.length > 0;
  if (!rows.length) {
    description.textContent = "No replay candles are visible.";
    return;
  }

  const width = 1000; const height = 380;
  const left = 72; const right = 18; const top = 16; const priceBottom = 286; const volumeBottom = 356;
  const minimum = Math.min(...rows.map((candle) => candle.low));
  const maximum = Math.max(...rows.map((candle) => candle.high));
  const priceRange = maximum - minimum || Math.max(maximum * 0.01, 1);
  const maximumVolume = Math.max(...rows.map((candle) => candle.volume), 1);
  const plotWidth = width - left - right;
  const slot = plotWidth / rows.length;
  const bodyWidth = Math.max(2, Math.min(14, slot * 0.58));
  const priceY = (price) => priceBottom - ((price - minimum) / priceRange) * (priceBottom - top);

  for (let index = 0; index <= 4; index += 1) {
    const y = top + ((priceBottom - top) / 4) * index;
    const price = maximum - (priceRange / 4) * index;
    chart.appendChild(svgElement("line", { x1: left, x2: width - right, y1: y, y2: y, class: "chart-grid" }));
    const label = svgElement("text", { x: left - 10, y: y + 6, class: "chart-axis", "text-anchor": "end" });
    label.textContent = price.toFixed(2); chart.appendChild(label);
  }

  rows.forEach((candle, index) => {
    const x = left + slot * (index + 0.5);
    const direction = candle.close >= candle.open ? "chart-up" : "chart-down";
    chart.appendChild(svgElement("line", {
      x1: x, x2: x, y1: priceY(candle.high), y2: priceY(candle.low), class: `chart-wick ${direction}`,
    }));
    const bodyTop = Math.min(priceY(candle.open), priceY(candle.close));
    const bodyHeight = Math.max(2, Math.abs(priceY(candle.open) - priceY(candle.close)));
    chart.appendChild(svgElement("rect", {
      x: x - bodyWidth / 2, y: bodyTop, width: bodyWidth, height: bodyHeight, rx: 1, class: direction,
    }));
    const volumeHeight = (candle.volume / maximumVolume) * 50;
    chart.appendChild(svgElement("rect", {
      x: x - bodyWidth / 2, y: volumeBottom - volumeHeight, width: bodyWidth, height: volumeHeight,
      class: `chart-volume ${direction}`,
    }));
  });
  description.textContent = `${rows.length} visible closed candles. Price range ${minimum.toFixed(2)} to ${maximum.toFixed(2)}.`;
}

function pausePlayback(message = null) {
  window.clearTimeout(state.playbackTimer);
  state.playbackTimer = null;
  const wasPlaying = state.playing;
  state.playing = false;
  state.playbackPending = false;
  state.playbackPollFailures = 0;
  byId("playbackStatus").textContent = "Idle";
  setConnection(Boolean(state.token), state.role);
  if (message && wasPlaying) notify(message);
}

async function loadSnapshot(preservePlayback = false) {
  if (!preservePlayback) pausePlayback();
  const id = byId("sessionId").value.trim();
  if (!id) throw new Error("Enter a replay session UUID.");
  render(await request(`/api/v1/replay/sessions/${encodeURIComponent(id)}`));
}

async function refreshSessions() {
  const response = await request("/api/v1/replay/sessions?limit=25");
  const select = byId("recentSessions");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = response.items.length
    ? "Choose a recent replay session"
    : "No replay sessions are available";
  select.appendChild(placeholder);
  response.items.forEach((session) => {
    const option = document.createElement("option");
    option.value = session.session_id;
    option.textContent = `${session.session_id} · ${session.next_index}/${session.total_events} · v${session.version}`;
    select.appendChild(option);
  });
}

async function refreshPlaybackHistory() {
  const id = byId("sessionId").value.trim();
  if (!id) throw new Error("Load a replay session first.");
  const response = await request(`/api/v1/replay/sessions/${encodeURIComponent(id)}/playback-runs?limit=10`);
  const body = byId("playbackHistory");
  body.replaceChildren();
  if (!response.items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5; cell.className = "empty"; cell.textContent = "No server playback runs yet.";
    row.appendChild(cell); body.appendChild(row); return;
  }
  response.items.forEach((run) => {
    const row = document.createElement("tr");
    const values = [
      new Date(run.started_at).toLocaleString(),
      run.task_id.slice(0, 8),
      run.outcome.replace("_", " "),
      run.frames_emitted,
      run.resulting_version ?? "—",
    ];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (index === 2) { cell.className = "outcome"; cell.dataset.outcome = run.outcome; }
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
}

byId("authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.token = byId("token").value;
  try {
    const session = await request("/api/v1/session");
    sessionStorage.setItem("mtsReplayToken", state.token);
    setConnection(true, session.role);
    byId("token").value = "";
    notify(`Connected as ${session.role}.`);
    refreshSessions().catch(() => notify("Connected, but replay discovery is unavailable.", true));
  } catch (error) { setConnection(false); notify(error.message, true); }
});

byId("disconnect").addEventListener("click", async () => {
  if (!(await stopServerPlayback("Server playback stopped before disconnecting."))) return;
  sessionStorage.removeItem("mtsReplayToken");
  state.token = ""; state.session = null;
  setConnection(false);
  byId("recentSessions").replaceChildren(new Option("Connect to discover replay sessions", ""));
  notify("Credential cleared from this tab.");
});

byId("sessionForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    if (!(await stopServerPlayback("Previous server playback stopped."))) return;
    await loadSnapshot();
    await refreshPlaybackHistory();
    notify("Replay prefix loaded.");
  } catch (error) { notify(error.message, true); }
});

byId("recentSessions").addEventListener("change", async (event) => {
  if (event.target.value) {
    if (!(await stopServerPlayback("Previous server playback stopped."))) return;
    byId("sessionId").value = event.target.value;
  }
});

byId("refreshSessions").addEventListener("click", () => {
  refreshSessions().then(() => notify("Recent replay sessions refreshed.")).catch((error) => notify(error.message, true));
});

byId("refreshPlaybackHistory").addEventListener("click", () => {
  refreshPlaybackHistory().then(() => notify("Playback evidence refreshed.")).catch((error) => notify(error.message, true));
});

byId("datasetForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    if (!(await stopServerPlayback("Previous server playback stopped."))) return;
    if (state.role !== "operator") throw new Error("Operator credentials are required.");
    const file = byId("datasetFile").files[0];
    if (!file) throw new Error("Choose a JSON candle dataset.");
    if (file.size > MAX_DATASET_BYTES) throw new Error("Dataset file exceeds the 5 MB browser limit.");
    const parsed = JSON.parse(await file.text());
    const candles = Array.isArray(parsed) ? parsed : parsed.candles;
    if (!Array.isArray(candles) || !candles.length) {
      throw new Error("Dataset JSON must be a non-empty candle array or an object with candles.");
    }
    const dataset = await request("/api/v1/operator/replay/datasets", {
      method: "POST", body: JSON.stringify({ candles }),
    });
    const sessionId = crypto.randomUUID();
    await request("/api/v1/operator/replay/sessions", {
      method: "POST", body: JSON.stringify({ session_id: sessionId, dataset_sha256: dataset.dataset_sha256 }),
    });
    byId("sessionId").value = sessionId;
    byId("datasetFile").value = "";
    await loadSnapshot();
    await refreshPlaybackHistory();
    await refreshSessions();
    notify(`Created replay with ${dataset.total_events} candles.`);
  } catch (error) { notify(error instanceof SyntaxError ? "Dataset is not valid JSON." : error.message, true); }
});

byId("step").addEventListener("click", async () => {
  try {
    const mutation = await stepReplay();
    notify(mutation.frame === null ? "Replay is complete." : "Advanced one candle.");
  } catch (error) { notify(error.message, true); }
});

async function stepReplay() {
  const id = byId("sessionId").value.trim();
  const mutation = await request(`/api/v1/operator/replay/sessions/${encodeURIComponent(id)}/step`, {
    method: "POST", body: JSON.stringify({ expected_version: state.session.version }),
  });
  await loadSnapshot(true);
  if (state.playing && (mutation.frame === null || state.session.next_index >= state.session.total_events)) {
    pausePlayback("Replay is complete.");
  }
  return mutation;
}

byId("play").addEventListener("click", () => {
  if (state.playing || state.playbackPending || !state.session) return;
  startServerPlayback().catch((error) => { pausePlayback(); notify(error.message, true); });
});

async function startServerPlayback() {
  state.playbackPending = true;
  byId("playbackStatus").textContent = "Starting";
  setConnection(true, state.role);
  const id = byId("sessionId").value.trim();
  const rate = Number(byId("playbackRate").value);
  const remaining = state.session.total_events - state.session.next_index;
  let task;
  try {
    task = await request(`/api/v1/operator/replay/sessions/${encodeURIComponent(id)}/playback`, {
      method: "POST",
      body: JSON.stringify({
        expected_version: state.session.version,
        candles_per_second: rate,
        maximum_steps: Math.min(Math.max(remaining, 1), 10000),
      }),
    });
    state.playing = true;
    state.playbackPollFailures = 0;
    byId("playbackStatus").textContent = "Running";
  } finally {
    state.playbackPending = false;
    setConnection(true, state.role);
  }
  refreshPlaybackHistory().catch(() => notify("Playback started, but run history is unavailable.", true));
  notify(`Server playback ${task.task_id.slice(0, 8)} started.`);
  pollServerPlayback();
}

async function pollServerPlayback() {
  if (!state.playing) return;
  const id = byId("sessionId").value.trim();
  let task;
  try {
    task = await request(`/api/v1/replay/sessions/${encodeURIComponent(id)}/playback`);
  } catch (error) {
    state.playbackPollFailures += 1;
    byId("playbackStatus").textContent = "Status unavailable";
    const retryDelay = Math.min(5000, 500 * (2 ** Math.min(state.playbackPollFailures, 4)));
    state.playbackTimer = window.setTimeout(pollServerPlayback, retryDelay);
    if (state.playbackPollFailures === 1) {
      notify(`${error.message} Playback ownership is retained; status polling will retry.`, true);
    }
    return;
  }

  state.playbackPollFailures = 0;
  byId("playbackStatus").textContent = task.outcome.replace("_", " ");
  if (task.outcome === "running") {
    await loadSnapshot(true).catch(() => {
      notify("Playback is running, but the prefix refresh failed.", true);
    });
    state.playbackTimer = window.setTimeout(pollServerPlayback, 250);
    return;
  }
  pausePlayback();
  byId("playbackStatus").textContent = task.outcome.replace("_", " ");
  await loadSnapshot(true).catch(() => notify("Playback ended, but the prefix refresh failed.", true));
  await refreshPlaybackHistory().catch(() => notify("Playback ended, but run history is unavailable.", true));
  notify(`Server playback ${task.outcome.replace("_", " ")}.`);
}

async function stopServerPlayback(message = "Server playback stopped.") {
  if (!state.playing) return true;
  const id = byId("sessionId").value.trim();
  try {
    const task = await request(`/api/v1/operator/replay/sessions/${encodeURIComponent(id)}/playback/stop`, {
      method: "POST", body: "{}",
    });
    pausePlayback();
    byId("playbackStatus").textContent = task.outcome;
    await loadSnapshot(true).catch(() => notify("Playback stopped, but the prefix refresh failed.", true));
    await refreshPlaybackHistory().catch(() => notify("Playback stopped, but run history is unavailable.", true));
    if (message) notify(message);
    return true;
  } catch (error) {
    setConnection(true, state.role);
    notify(error.message, true);
    return false;
  }
}

byId("pause").addEventListener("click", () => stopServerPlayback());
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopServerPlayback("Server playback stopped while this tab is hidden.");
});

byId("seek").addEventListener("click", async () => {
  try {
    pausePlayback();
    const value = byId("seekAt").value;
    if (!value) throw new Error("Choose a seek time.");
    const id = byId("sessionId").value.trim();
    await request(`/api/v1/operator/replay/sessions/${encodeURIComponent(id)}/seek`, {
      method: "POST", body: JSON.stringify({ expected_version: state.session.version, as_of: new Date(value).toISOString() }),
    });
    await loadSnapshot();
    notify("Replay cursor moved.");
  } catch (error) { notify(error.message, true); }
});

if (state.token) {
  request("/api/v1/session").then((session) => {
    setConnection(true, session.role);
    refreshSessions().catch(() => notify("Connected, but replay discovery is unavailable.", true));
  }).catch(() => {
    sessionStorage.removeItem("mtsReplayToken"); state.token = ""; setConnection(false);
  });
}
