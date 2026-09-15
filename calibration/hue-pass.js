"use strict";

// Separate schema and storage from the original inverse-profile experiment.
const STORAGE_KEY = "qr65-hue-pass-v2";
const PALETTE = ["#FF0000", "#FF8000", "#FFFF00", "#80FF00", "#00FF00", "#00FF80",
  "#00FFFF", "#0080FF", "#0000FF", "#8000FF", "#FF00FF", "#FF0080"];
const ORDER = [0, 6, 2, 9, 4, 11, 1, 8, 5, 10, 3, 7, 0, 4, 8];
const SAMPLES = ORDER.map((hue, index) => ({
  id: `H${String(index + 1).padStart(2, "0")}`,
  role: index < 12 ? "hue-fit" : "repeat",
  target: PALETTE[hue],
}));
const HEX = /^#[0-9A-F]{6}$/;
const $ = (id) => document.getElementById(id);
let state = {
  version: 2, experiment: "saturated-hue-pass", brightness: 50,
  startedAt: new Date().toISOString(), conditions: "", current: 0,
  measurements: SAMPLES.map((sample) => ({ ...sample, command: null, quality: null, notes: "" })),
};

function validate(data) {
  if (!data || data.version !== 2 || data.experiment !== "saturated-hue-pass" ||
      data.brightness !== 50 || typeof data.startedAt !== "string" ||
      !Number.isFinite(Date.parse(data.startedAt)) ||
      typeof data.conditions !== "string" || data.conditions.length > 4000 ||
      !Number.isInteger(data.current) || data.current < 0 || data.current >= SAMPLES.length ||
      !Array.isArray(data.measurements) || data.measurements.length !== SAMPLES.length) {
    throw new Error("Not a valid version-2 saturated hue session.");
  }
  const measurements = data.measurements.map((row, index) => {
    const sample = SAMPLES[index];
    if (!row || row.id !== sample.id || row.role !== sample.role || row.target !== sample.target ||
        !(row.command === null || (typeof row.command === "string" && HEX.test(row.command))) ||
        ![null, "good", "closest"].includes(row.quality) ||
        typeof row.notes !== "string" || row.notes.length > 4000) {
      throw new Error(`Invalid measurement ${sample.id}.`);
    }
    return { ...sample, command: row.command, quality: row.quality, notes: row.notes };
  });
  return { version: 2, experiment: data.experiment, brightness: 50,
    startedAt: data.startedAt, conditions: data.conditions, current: data.current, measurements };
}

function message(text) { $("message").textContent = text; }
function persist() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); return true; }
  catch {
    message("Browser storage unavailable or full. Export a checkpoint to preserve this session.");
    return false;
  }
}
function complete(row) { return row.command !== null && row.quality !== null; }
function updateProgress() {
  const count = state.measurements.filter(complete).length;
  $("progress").textContent = `${count} / ${SAMPLES.length} complete${count === SAMPLES.length ? " — export and share your JSON." : ""}`;
}
function capture() {
  const raw = $("command").value.trim().toUpperCase();
  const normalized = raw.startsWith("#") ? raw : `#${raw}`;
  if (raw && !HEX.test(normalized)) {
    $("command").setAttribute("aria-invalid", "true");
    message("Enter six HEX digits, optionally prefixed with #, or clear the field.");
    return false;
  }
  $("command").removeAttribute("aria-invalid");
  Object.assign(state.measurements[state.current], {
    command: raw ? normalized : null, quality: $("quality").value || null,
    notes: $("notes").value,
  });
  state.conditions = $("conditions").value;
  message("");
  persist();
  updateProgress();
  return true;
}
function render() {
  const row = state.measurements[state.current];
  $("position").textContent = `Sample ${state.current + 1} of ${SAMPLES.length}`;
  $("target").textContent = row.target;
  $("swatch").style.backgroundColor = row.target;
  $("swatch").setAttribute("aria-label", `Reference ${row.target}`);
  $("command").value = row.command || "";
  $("command").removeAttribute("aria-invalid");
  $("quality").value = row.quality || "";
  $("notes").value = row.notes;
  $("conditions").value = state.conditions;
  $("jump").value = String(state.current);
  $("previous").disabled = state.current === 0;
  $("next").textContent = state.current === SAMPLES.length - 1 ? "Save final sample" : "Save & next";
  updateProgress();
}
function navigate(index) {
  if (!capture()) { $("jump").value = String(state.current); return; }
  state.current = index;
  persist();
  render();
}

try {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) state = validate(JSON.parse(saved));
} catch { message("Saved progress could not be loaded. Import an exported checkpoint if available."); }
for (let index = 0; index < SAMPLES.length; index++) {
  const option = document.createElement("option");
  option.value = String(index);
  option.textContent = `Sample ${index + 1}`;
  $("jump").append(option);
}
$("previous").addEventListener("click", () => navigate(Math.max(0, state.current - 1)));
$("next").addEventListener("click", () => {
  if (state.current !== SAMPLES.length - 1) {
    navigate(state.current + 1);
    return;
  }
  if (!capture()) return;
  const remaining = state.measurements.filter((row) => !complete(row)).length;
  if (!persist()) return;
  message(remaining
    ? `Progress saved. ${remaining} sample(s) still need a HEX and match quality. Use Go to sample to review them.`
    : "All 15 samples saved. Export your JSON checkpoint and share it for review.");
});
$("jump").addEventListener("change", () => navigate(Number($("jump").value)));
for (const id of ["command", "quality", "notes", "conditions"]) {
  $(id).addEventListener("change", capture);
}
$("export").addEventListener("click", () => {
  if (!capture()) return;
  const data = { ...state, exportedAt: new Date().toISOString() };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `qr65-hue-pass-${new Date().toISOString().replaceAll(":", "-")}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("import").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 100000) throw new Error("Session file exceeds 100 KB.");
    const imported = validate(JSON.parse(await file.text()));
    if (!window.confirm("Replace the current session with this imported checkpoint? Export your current work first if needed.")) return;
    state = imported;
    message("Checkpoint imported.");
    persist();
    render();
  } catch (error) { message(`Import failed: ${error.message}`); }
  finally { event.target.value = ""; }
});
window.addEventListener("beforeunload", (event) => {
  if (!capture()) { event.preventDefault(); event.returnValue = ""; }
});
render();
