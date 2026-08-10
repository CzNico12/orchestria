const $ = (id) => document.getElementById(id);

const dropZone = $("dropZone");
const fileInput = $("fileInput");
const fileHint = $("fileHint");
const btnLaunch = $("btnLaunch");
const btnAgain = $("btnAgain");
const miniNote = $("miniNote");

let currentFile = null;
let jobId = null;
let finished = false;
let pollTimer = null;
let elapsedStart = 0;

const STEM_ORDER = ["drums", "bass", "guitar", "piano", "other", "vocals"];

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 4200);
}

function pickFile(file) {
  if (!file) return;
  const ok = /\.(mp3|wav|ogg|flac|m4a|aac)$/i.test(file.name) || file.type.startsWith("audio/");
  if (!ok) {
    toast("Format non supporté : utilise MP3, WAV, OGG, FLAC, M4A ou AAC.");
    return;
  }
  currentFile = file;
  fileHint.textContent = `✅ ${file.name} — ${(file.size / 1024 / 1024).toFixed(1)} Mo`;
  dropZone.classList.add("has-file");
  btnLaunch.disabled = false;
  btnLaunch.textContent = `🎛️ Séparer les instruments de « ${file.name.replace(/\.[^.]+$/, "").slice(0, 28)} »`;
}

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
fileInput.addEventListener("change", () => pickFile(fileInput.files[0]));

["dragenter", "dragover"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.add("drag"); })
);
["dragleave", "drop"].forEach((ev) =>
  dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.remove("drag"); })
);
dropZone.addEventListener("drop", (e) => pickFile(e.dataTransfer.files[0]));

function fmtBytes(n) {
  if (n >= 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + " Mo";
  if (n >= 1024) return (n / 1024).toFixed(0) + " Ko";
  return n + " o";
}

function fmtElapsed() {
  const s = Math.floor((Date.now() - elapsedStart) / 1000);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  return `${m} min ${s % 60} s`;
}

async function launch() {
  if (!currentFile) return;
  btnLaunch.disabled = true;
  btnLaunch.textContent = "⏳ Envoi du fichier…";

  const form = new FormData();
  form.append("file", currentFile);

  let resp;
  try {
    resp = await fetch("/api/upload", { method: "POST", body: form });
  } catch (err) {
    toast("Impossible de contacter le serveur. Est-il bien lancé ?");
    btnLaunch.disabled = false;
    return;
  }

  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    toast("Erreur : " + (detail.detail || resp.status));
    btnLaunch.disabled = false;
    return;
  }

  const data = await resp.json();
  jobId = data.job;
  finished = false;
  localStorage.setItem("demixJob", data.job);

  $("uploadCard").hidden = true;
  $("progressCard").hidden = false;
  $("resultsCard").hidden = true;
  elapsedStart = Date.now();
  $("progressElapsed").textContent = "0 s";

  updateTimeLoop();
  pollTimer = setInterval(poll, 1200);
}

function updateTimeLoop() {
  if (!jobId || finished) return;
  $("progressElapsed").textContent = fmtElapsed();
  setTimeout(updateTimeLoop, 1000);
}

async function poll() {
  if (!jobId || finished) return;
  const id = jobId;
  let s;
  try {
    s = await (await fetch(`/api/status/${id}`)).json();
  } catch {
    return;
  }

  $("progressMessage").textContent = s.message || "";
  $("progressFill").style.width = (s.progress || 0) + "%";
  $("progressPct").textContent = (s.progress || 0) + " %";

  if (s.status === "done") {
    clearInterval(pollTimer);
    renderResults(s, id);
    $("progressCard").hidden = true;
    $("resultsCard").hidden = false;
    $("resultsCard").scrollIntoView({ behavior: "smooth", block: "start" });
    finished = true;
  } else if (s.status === "error") {
    clearInterval(pollTimer);
    jobId = null;
    $("progressCard").hidden = true;
    $("uploadCard").hidden = false;
    toast("Erreur pendant l'analyse : " + (s.error || "inconnue"));
    resetUpload();
  }
}

function stemCard(stem, done, id) {
  const card = document.createElement("div");
  card.className = "stem-card" + (done ? "" : " pending");
  card.id = "stem-" + stem.key;

  const top = document.createElement("div");
  top.className = "stem-top";
  top.innerHTML = `<span class="stem-emoji">${stem.emoji}</span><span class="stem-name">${stem.label}</span>`;

  card.appendChild(top);

  if (done) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "metadata";
    audio.src = `/api/file/${id}/${stem.key}.mp3`;
    card.appendChild(audio);

    const size = document.createElement("span");
    size.className = "stem-size";
    size.textContent = fmtBytes(stem.size);
    top.appendChild(size);

    const actions = document.createElement("div");
    actions.className = "stem-actions";

    const mid = document.createElement("a");
    mid.className = "stem-btn mid";
    mid.href = `/api/file/${id}/${stem.key}.mid`;
    mid.download = `${stem.label}.mid`;
    mid.textContent = "🎹 MIDI";

    const mp3 = document.createElement("a");
    mp3.className = "stem-btn";
    mp3.href = `/api/file/${id}/${stem.key}.mp3`;
    mp3.download = `${stem.label}.mp3`;
    mp3.textContent = "⬇️ MP3 isolé";

    actions.appendChild(mid);
    actions.appendChild(mp3);
    card.appendChild(actions);
  } else {
    top.appendChild(cardStatus("… en attente"));
  }
  return card;
}

function cardStatus(text) {
  const s = document.createElement("span");
  s.className = "stem-size";
  s.textContent = text;
  return s;
}

function renderResults(statusData, id) {
  const name = currentFile ? `« ${currentFile.name} » — ${statusData.stems.length} pistes détectées.` : "";
  $("resultsFile").textContent = name;
  const grid = $("stemGrid");
  grid.innerHTML = "";

  const sorted = [...statusData.stems].sort(
    (a, b) => STEM_ORDER.indexOf(a.key) - STEM_ORDER.indexOf(b.key)
  );
  sorted.forEach((stem) => grid.appendChild(stemCard(stem, true, id)));
  $("btnZip").disabled = false;
}

$("btnLaunch").addEventListener("click", launch);

$("btnZip").addEventListener("click", async () => {
  if (!jobId) return;
  $("btnZip").disabled = true;
  $("btnZip").textContent = "⏳ Préparation…";
  try {
    const resp = await fetch(`/api/zip/${jobId}`);
    if (!resp.ok) throw new Error();
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "separation-instruments.zip";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  } catch {
    toast("Impossible de créer le ZIP. Télécharge chaque piste individuellement.");
  }
  $("btnZip").disabled = false;
  $("btnZip").textContent = "📦 Tout télécharger (ZIP)";
});

function resetUpload() {
  currentFile = null;
  jobId = null;
  finished = false;
  localStorage.removeItem("demixJob");
  fileInput.value = "";
  fileHint.textContent = "Aucun fichier sélectionné";
  dropZone.classList.remove("has-file");
  btnLaunch.disabled = true;
  btnLaunch.textContent = "🎛️ Séparer les instruments";
  $("resultsCard").hidden = true;
  $("uploadCard").hidden = false;
  $("uploadCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

$("btnAgain").addEventListener("click", resetUpload);

async function restoreJob() {
  const params = new URLSearchParams(location.search);
  const urlJob = params.get("job");
  const saved = urlJob || localStorage.getItem("demixJob");
  if (urlJob) localStorage.setItem("demixJob", urlJob);
  if (!saved) return;
  let s;
  try {
    s = await (await fetch(`/api/status/${saved}`)).json();
  } catch {
    return;
  }
  if (s.status === "done") {
    jobId = saved;
    renderResults(s, saved);
    finished = true;
    $("uploadCard").hidden = true;
    $("progressCard").hidden = true;
    $("resultsCard").hidden = false;
  } else if (s.status === "queued" || s.status === "separating" || s.status === "transcribing") {
    jobId = saved;
    $("uploadCard").hidden = true;
    $("progressCard").hidden = false;
    elapsedStart = Date.now();
    updateTimeLoop();
    pollTimer = setInterval(poll, 1200);
  } else {
    localStorage.removeItem("demixJob");
  }
}

restoreJob();