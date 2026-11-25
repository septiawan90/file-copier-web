const state = {
  files: [],
  filteredFiles: [],
  selectedPaths: new Set(),
  sortKey: "modified_at",
  sortAsc: false,
  presets: [],
  browseTargetInputId: null,
  browseCurrent: "",
  browseParent: "",
};

const els = {
  serverBadge: document.getElementById("serverBadge"),
  presetsList: document.getElementById("presetsList"),
  presetNameInput: document.getElementById("presetNameInput"),
  savePresetBtn: document.getElementById("savePresetBtn"),
  sourceDir: document.getElementById("sourceDir"),
  destDir: document.getElementById("destDir"),
  browseSourceBtn: document.getElementById("browseSourceBtn"),
  browseDestBtn: document.getElementById("browseDestBtn"),
  openDestBtn: document.getElementById("openDestBtn"),
  keywords: document.getElementById("keywords"),
  extensions: document.getElementById("extensions"),
  recursive: document.getElementById("recursive"),
  useRegex: document.getElementById("useRegex"),
  dateField: document.getElementById("dateField"),
  dateMode: document.getElementById("dateMode"),
  specificDateGroup: document.getElementById("specificDateGroup"),
  specificDates: document.getElementById("specificDates"),
  datePickerHelper: document.getElementById("datePickerHelper"),
  rangeDateGroup: document.getElementById("rangeDateGroup"),
  dateFrom: document.getElementById("dateFrom"),
  dateTo: document.getElementById("dateTo"),
  scanBtn: document.getElementById("scanBtn"),
  resetBtn: document.getElementById("resetBtn"),
  scanSummary: document.getElementById("scanSummary"),
  quickSearch: document.getElementById("quickSearch"),
  selectAllBtn: document.getElementById("selectAllBtn"),
  clearSelectBtn: document.getElementById("clearSelectBtn"),
  warningsBox: document.getElementById("warningsBox"),
  masterCheck: document.getElementById("masterCheck"),
  resultsBody: document.getElementById("resultsBody"),
  transferMode: document.getElementById("transferMode"),
  conflictPolicy: document.getElementById("conflictPolicy"),
  transferBtn: document.getElementById("transferBtn"),
  selectedCount: document.getElementById("selectedCount"),
  previewMeta: document.getElementById("previewMeta"),
  previewContainer: document.getElementById("previewContainer"),
  activityLog: document.getElementById("activityLog"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  browseModal: document.getElementById("browseModal"),
  browseBackdrop: document.getElementById("browseBackdrop"),
  closeBrowseBtn: document.getElementById("closeBrowseBtn"),
  browseUpBtn: document.getElementById("browseUpBtn"),
  browseCurrentPath: document.getElementById("browseCurrentPath"),
  browseList: document.getElementById("browseList"),
  chooseFolderBtn: document.getElementById("chooseFolderBtn"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const val = bytes / Math.pow(1024, idx);
  return `${val >= 10 || idx === 0 ? val.toFixed(0) : val.toFixed(1)} ${units[idx]}`;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request gagal (${response.status})`);
  }
  return data;
}

function syncDateModeUI() {
  const mode = els.dateMode.value;
  els.specificDateGroup.classList.toggle("hidden", mode !== "specific");
  els.rangeDateGroup.classList.toggle("hidden", mode !== "range");
}

function collectFilterPayload() {
  return {
    source_dir: els.sourceDir.value.trim(),
    dest_dir: els.destDir.value.trim(),
    keywords: els.keywords.value.trim(),
    extensions: els.extensions.value.trim(),
    recursive: els.recursive.checked,
    use_regex: els.useRegex.checked,
    date_field: els.dateField.value,
    date_mode: els.dateMode.value,
    specific_dates: els.specificDates.value.trim(),
    date_from: els.dateFrom.value,
    date_to: els.dateTo.value,
    conflict_policy: els.conflictPolicy.value,
  };
}

function applyPreset(preset) {
  if (preset.source_dir) els.sourceDir.value = preset.source_dir;
  if (preset.dest_dir) els.destDir.value = preset.dest_dir;
  els.keywords.value = preset.keywords || "";
  els.extensions.value = preset.extensions || "";
  els.recursive.checked = Boolean(preset.recursive);
  els.useRegex.checked = Boolean(preset.use_regex);
  els.dateField.value = preset.date_field || "either";
  els.dateMode.value = preset.date_mode || "none";
  els.specificDates.value = preset.specific_dates || "";
  els.dateFrom.value = preset.date_from || "";
  els.dateTo.value = preset.date_to || "";
  if (preset.conflict_policy) els.conflictPolicy.value = preset.conflict_policy;
  syncDateModeUI();
  runScan();
}

function renderPresets() {
  if (!state.presets.length) {
    els.presetsList.innerHTML = `<span class="hint">Belum ada preset tersimpan.</span>`;
    return;
  }
  els.presetsList.innerHTML = state.presets
    .map(
      (preset) => `
      <span class="preset-chip">
        <button type="button" class="preset-apply" data-id="${escapeHtml(preset.id)}">${escapeHtml(preset.name)}</button>
        <button type="button" class="preset-delete" data-id="${escapeHtml(preset.id)}" title="Hapus preset">&times;</button>
      </span>
    `
    )
    .join("");
}

async function loadPresets() {
  try {
    const data = await apiFetch("/api/presets");
    state.presets = data.presets || [];
    renderPresets();
  } catch (err) {
    console.error(err);
  }
}

async function saveCurrentPreset() {
  const name = els.presetNameInput.value.trim();
  if (!name) {
    alert("Masukkan nama preset terlebih dahulu.");
    return;
  }
  try {
    const data = await apiFetch("/api/presets", {
      method: "POST",
      body: JSON.stringify({ ...collectFilterPayload(), name }),
    });
    state.presets = data.presets || [];
    els.presetNameInput.value = "";
    renderPresets();
  } catch (err) {
    alert(err.message);
  }
}

// Only checked files that are visible in the table (after quick search) get processed.
function getEffectiveSelection() {
  return state.filteredFiles.filter((f) => state.selectedPaths.has(f.path)).map((f) => f.path);
}

function updateSelectionUI() {
  const count = getEffectiveSelection().length;
  const hiddenCount = state.selectedPaths.size - count;
  els.selectedCount.textContent = String(count);
  els.transferBtn.disabled = count === 0;
  els.transferBtn.title =
    hiddenCount > 0
      ? `${hiddenCount} file terpilih sedang tersembunyi oleh saringan cepat dan tidak akan diproses.`
      : "";
  const visibleCount = state.filteredFiles.length;
  const allVisibleChecked =
    visibleCount > 0 && state.filteredFiles.every((f) => state.selectedPaths.has(f.path));
  els.masterCheck.checked = allVisibleChecked;
}

function applyQuickFilterAndSort() {
  const q = els.quickSearch.value.trim().toLowerCase();
  const filtered = q
    ? state.files.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.created_at.includes(q) ||
          f.modified_at.includes(q)
      )
    : [...state.files];

  const key = state.sortKey;
  const dir = state.sortAsc ? 1 : -1;
  filtered.sort((a, b) => {
    if (key === "size") return (a.size - b.size) * dir;
    return String(a[key]).localeCompare(String(b[key])) * dir;
  });

  state.filteredFiles = filtered;
  renderTable();
}

function renderTable() {
  if (!state.filteredFiles.length) {
    els.resultsBody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">Tidak ada file yang cocok dengan kriteria.</td>
      </tr>
    `;
    updateSelectionUI();
    return;
  }

  els.resultsBody.innerHTML = state.filteredFiles
    .map((file) => {
      const checked = state.selectedPaths.has(file.path) ? "checked" : "";
      const diffBadge = file.dates_differ
        ? `<span class="badge-diff" title="Tanggal dibuat dan diubah berbeda">Tgl Beda</span>`
        : "";
      return `
        <tr>
          <td class="col-check">
            <input type="checkbox" class="row-check" data-path="${escapeHtml(file.path)}" ${checked} />
          </td>
          <td class="file-name-cell">
            ${escapeHtml(file.name)}${diffBadge}
            <span class="file-subpath">${escapeHtml(file.path)}</span>
          </td>
          <td>${escapeHtml(formatBytes(file.size))}</td>
          <td>${escapeHtml(file.created_at)}</td>
          <td>${escapeHtml(file.modified_at)}</td>
          <td>
            <button type="button" class="btn btn-outline btn-sm preview-btn" data-path="${escapeHtml(file.path)}">
              Preview
            </button>
          </td>
        </tr>
      `;
    })
    .join("");

  updateSelectionUI();
}

async function runScan() {
  els.scanBtn.disabled = true;
  els.scanBtn.textContent = "Memindai...";
  els.warningsBox.classList.add("hidden");
  els.warningsBox.innerHTML = "";

  try {
    const data = await apiFetch("/api/scan", {
      method: "POST",
      body: JSON.stringify(collectFilterPayload()),
    });
    state.files = data.files || [];
    state.selectedPaths = new Set();

    els.scanSummary.textContent = `Ditemukan ${data.total_matched} file cocok dari ${data.total_scanned} file yang dipindai.`;
    if (data.warnings && data.warnings.length) {
      els.warningsBox.innerHTML = data.warnings.map((w) => `<div>• ${escapeHtml(w)}</div>`).join("");
      els.warningsBox.classList.remove("hidden");
    }
    applyQuickFilterAndSort();
  } catch (err) {
    els.scanSummary.textContent = `Gagal memindai: ${err.message}`;
    state.files = [];
    state.filteredFiles = [];
    state.selectedPaths.clear();
    renderTable();
  } finally {
    els.scanBtn.disabled = false;
    els.scanBtn.textContent = "Cari & Tampilkan File";
  }
}

async function loadPreview(filePath) {
  els.previewMeta.textContent = "Memuat preview...";
  els.previewContainer.innerHTML = `<p class="empty-state">Sedang membaca file...</p>`;
  try {
    const data = await apiFetch(`/api/preview?path=${encodeURIComponent(filePath)}`);
    els.previewMeta.textContent = `${data.name} • ${formatBytes(data.size)} • Dibuat: ${data.created_at} • Diubah: ${data.modified_at}`;

    if (data.kind === "text") {
      const note = data.truncated
        ? `<div class="warnings-box">Konten terlalu panjang, hanya menampilkan sebagian awal.</div>`
        : "";
      els.previewContainer.innerHTML = `${note}<pre class="preview-text">${escapeHtml(data.content)}</pre>`;
    } else if (data.kind === "image") {
      els.previewContainer.innerHTML = `<img class="preview-image" src="${escapeHtml(data.url)}" alt="${escapeHtml(data.name)}" />`;
    } else if (data.kind === "pdf") {
      els.previewContainer.innerHTML = `<iframe class="preview-pdf" src="${escapeHtml(data.url)}" title="${escapeHtml(data.name)}"></iframe>`;
    } else {
      els.previewContainer.innerHTML = `<p class="empty-state">${escapeHtml(data.message || "Preview tidak tersedia.")}</p>`;
    }
  } catch (err) {
    els.previewMeta.textContent = "Preview gagal";
    els.previewContainer.innerHTML = `<p class="empty-state status-failed">${escapeHtml(err.message)}</p>`;
  }
}

function appendActivityLog(summary, results, mode, destDir) {
  if (els.activityLog.querySelector(".empty-state")) {
    els.activityLog.innerHTML = "";
  }
  const timeStr = new Date().toLocaleTimeString("id-ID");
  const actionLabel = mode === "move" ? "Pemindahan" : "Penyalinan";
  const rowsHtml = results
    .map(
      (r) => `
      <li class="status-${escapeHtml(r.status)}">
        <strong>${escapeHtml(r.source)}</strong> — ${escapeHtml(r.message)}
      </li>
    `
    )
    .join("");

  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `
    <div>
      <strong>[${escapeHtml(timeStr)}] ${actionLabel} ke ${escapeHtml(destDir)}</strong> —
      Berhasil: <span class="status-succeeded">${summary.succeeded}</span>,
      Dilewati: <span class="status-skipped">${summary.skipped}</span>,
      Gagal: <span class="status-failed">${summary.failed}</span>
      (${escapeHtml(formatBytes(summary.total_bytes))})
    </div>
    <ul>${rowsHtml}</ul>
  `;
  els.activityLog.prepend(entry);
}

async function runTransfer() {
  const selected = getEffectiveSelection();
  if (!selected.length) return;
  const mode = els.transferMode.value;
  const policy = els.conflictPolicy.value;
  const risks = [];
  if (mode === "move") risks.push("• File akan dihapus dari folder sumber.");
  if (policy === "overwrite") {
    risks.push("• File dengan nama sama di folder tujuan akan DITIMPA dan tidak bisa dikembalikan.");
  }
  if (risks.length) {
    const verb = mode === "move" ? "Pindahkan" : "Salin";
    const question = `${verb} ${selected.length} file ke ${els.destDir.value.trim()}?\n\n${risks.join("\n")}`;
    if (!confirm(question)) return;
  }

  els.transferBtn.disabled = true;
  els.transferBtn.textContent = "Memproses...";
  try {
    const data = await apiFetch("/api/transfer", {
      method: "POST",
      body: JSON.stringify({
        files: selected,
        dest_dir: els.destDir.value.trim(),
        mode,
        conflict_policy: policy,
        create_dest: true,
      }),
    });
    appendActivityLog(data.summary, data.results || [], mode, els.destDir.value.trim());
    if (mode === "move") {
      await runScan();
    }
  } catch (err) {
    alert(`Gagal memproses transfer: ${err.message}`);
  } finally {
    els.transferBtn.innerHTML = `Proses File Terpilih (<span id="selectedCount">0</span>)`;
    els.selectedCount = document.getElementById("selectedCount");
    updateSelectionUI();
  }
}

async function openBrowseModal(targetInputId) {
  state.browseTargetInputId = targetInputId;
  const initialPath = document.getElementById(targetInputId).value.trim();
  els.browseModal.classList.remove("hidden");
  await loadBrowseDirectory(initialPath);
}

async function loadBrowseDirectory(pathStr) {
  try {
    const data = await apiFetch(`/api/browse?path=${encodeURIComponent(pathStr || "")}`);
    state.browseCurrent = data.current || "";
    state.browseParent = data.parent || "";
    els.browseCurrentPath.value = state.browseCurrent || "Daftar Drive";
    els.chooseFolderBtn.disabled = !state.browseCurrent;
    els.browseUpBtn.disabled = !state.browseCurrent;

    if (!data.folders.length) {
      els.browseList.innerHTML = `<div class="empty-state">Tidak ada subfolder.</div>`;
      return;
    }
    els.browseList.innerHTML = data.folders
      .map(
        (folder) => `
        <button type="button" class="browse-item" data-path="${escapeHtml(folder.path)}">
          📁 ${escapeHtml(folder.name)}
        </button>
      `
      )
      .join("");
  } catch (err) {
    if (pathStr) {
      await loadBrowseDirectory("");
      return;
    }
    els.browseList.innerHTML = `<div class="empty-state status-failed">${escapeHtml(err.message)}</div>`;
  }
}

function closeBrowseModal() {
  els.browseModal.classList.add("hidden");
  state.browseTargetInputId = null;
}

function bindEvents() {
  els.dateMode.addEventListener("change", syncDateModeUI);

  els.datePickerHelper.addEventListener("change", () => {
    const picked = els.datePickerHelper.value;
    if (!picked) return;
    const current = els.specificDates.value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (!current.includes(picked)) {
      current.push(picked);
      els.specificDates.value = current.join(", ");
    }
  });

  els.scanBtn.addEventListener("click", runScan);
  els.resetBtn.addEventListener("click", () => {
    els.keywords.value = "";
    els.extensions.value = "";
    els.recursive.checked = false;
    els.useRegex.checked = false;
    els.dateField.value = "either";
    els.dateMode.value = "none";
    els.specificDates.value = "";
    els.dateFrom.value = "";
    els.dateTo.value = "";
    els.quickSearch.value = "";
    syncDateModeUI();

    state.files = [];
    state.filteredFiles = [];
    state.selectedPaths.clear();
    els.scanSummary.textContent = "Belum ada pencarian dijalankan.";
    els.warningsBox.classList.add("hidden");
    els.warningsBox.innerHTML = "";
    els.resultsBody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">Klik <strong>Cari &amp; Tampilkan File</strong> untuk memulai.</td>
      </tr>
    `;
    els.previewMeta.textContent = 'Klik tombol "Preview" pada baris file.';
    els.previewContainer.innerHTML = `<p class="empty-state">Belum ada file yang di-preview.</p>`;
    updateSelectionUI();
  });

  els.quickSearch.addEventListener("input", applyQuickFilterAndSort);

  els.selectAllBtn.addEventListener("click", () => {
    state.filteredFiles.forEach((f) => state.selectedPaths.add(f.path));
    renderTable();
  });

  els.clearSelectBtn.addEventListener("click", () => {
    state.filteredFiles.forEach((f) => state.selectedPaths.delete(f.path));
    renderTable();
  });

  els.masterCheck.addEventListener("change", () => {
    const checked = els.masterCheck.checked;
    state.filteredFiles.forEach((f) => {
      if (checked) state.selectedPaths.add(f.path);
      else state.selectedPaths.delete(f.path);
    });
    renderTable();
  });

  els.resultsBody.addEventListener("change", (event) => {
    if (!event.target.classList.contains("row-check")) return;
    const path = event.target.dataset.path;
    if (event.target.checked) state.selectedPaths.add(path);
    else state.selectedPaths.delete(path);
    updateSelectionUI();
  });

  els.resultsBody.addEventListener("click", (event) => {
    const btn = event.target.closest(".preview-btn");
    if (!btn) return;
    loadPreview(btn.dataset.path);
  });

  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortAsc = !state.sortAsc;
      else {
        state.sortKey = key;
        state.sortAsc = key === "name";
      }
      applyQuickFilterAndSort();
    });
  });

  els.transferBtn.addEventListener("click", runTransfer);
  els.savePresetBtn.addEventListener("click", saveCurrentPreset);

  els.presetsList.addEventListener("click", async (event) => {
    const applyBtn = event.target.closest(".preset-apply");
    if (applyBtn) {
      const found = state.presets.find((p) => p.id === applyBtn.dataset.id);
      if (found) applyPreset(found);
      return;
    }
    const delBtn = event.target.closest(".preset-delete");
    if (delBtn) {
      const preset = state.presets.find((p) => p.id === delBtn.dataset.id);
      const label = preset ? preset.name : delBtn.dataset.id;
      if (!confirm(`Hapus preset "${label}"?`)) return;
      try {
        const data = await apiFetch(`/api/presets?id=${encodeURIComponent(delBtn.dataset.id)}`, {
          method: "DELETE",
        });
        state.presets = data.presets || [];
        renderPresets();
      } catch (err) {
        alert(`Gagal menghapus preset: ${err.message}`);
      }
    }
  });

  els.openDestBtn.addEventListener("click", async () => {
    try {
      await apiFetch("/api/open-folder", {
        method: "POST",
        body: JSON.stringify({ path: els.destDir.value.trim() }),
      });
    } catch (err) {
      alert(err.message);
    }
  });

  els.clearLogBtn.addEventListener("click", () => {
    els.activityLog.innerHTML = `<p class="empty-state">Belum ada aktivitas penyalinan.</p>`;
  });

  els.browseSourceBtn.addEventListener("click", () => openBrowseModal("sourceDir"));
  els.browseDestBtn.addEventListener("click", () => openBrowseModal("destDir"));
  els.closeBrowseBtn.addEventListener("click", closeBrowseModal);
  els.browseBackdrop.addEventListener("click", closeBrowseModal);
  els.browseUpBtn.addEventListener("click", () => loadBrowseDirectory(state.browseParent));
  els.browseList.addEventListener("click", (event) => {
    const item = event.target.closest(".browse-item");
    if (!item) return;
    loadBrowseDirectory(item.dataset.path);
  });
  els.chooseFolderBtn.addEventListener("click", () => {
    if (state.browseTargetInputId && state.browseCurrent) {
      document.getElementById(state.browseTargetInputId).value = state.browseCurrent;
    }
    closeBrowseModal();
  });
}

async function init() {
  bindEvents();
  syncDateModeUI();
  try {
    const health = await apiFetch("/api/health");
    els.serverBadge.textContent = "Server Lokal Aktif";
    els.serverBadge.className = "badge badge-ok";
    if (health.default_source) els.sourceDir.value = health.default_source;
    if (health.default_dest) els.destDir.value = health.default_dest;
    await loadPresets();
  } catch (err) {
    els.serverBadge.textContent = "Server Tidak Terhubung";
    els.serverBadge.className = "badge badge-err";
  }
}

init();
