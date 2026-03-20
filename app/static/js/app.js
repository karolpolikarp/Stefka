const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const fileInfo = document.getElementById("file-info");
const fileName = document.getElementById("file-name");
const fileSize = document.getElementById("file-size");
const clearFileBtn = document.getElementById("clear-file");
const uploadForm = document.getElementById("upload-form");
const submitBtn = document.getElementById("submit-btn");
const exportFormat = document.getElementById("export-format");

const uploadSection = document.getElementById("upload-section");
const progressSection = document.getElementById("progress-section");
const resultSection = document.getElementById("result-section");
const errorSection = document.getElementById("error-section");

const progressFill = document.getElementById("progress-fill");
const progressPercent = document.getElementById("progress-percent");
const progressStatus = document.getElementById("progress-status");
const progressMessage = document.getElementById("progress-message");
const progressFilename = document.getElementById("progress-filename");
const progressFormat = document.getElementById("progress-format");

const downloadBtn = document.getElementById("download-btn");
const newFileBtn = document.getElementById("new-file-btn");
const retryBtn = document.getElementById("retry-btn");
const errorMessage = document.getElementById("error-message");
const resultMessage = document.getElementById("result-message");
const resultFilename = document.getElementById("result-filename");
const resultFormat = document.getElementById("result-format");

let selectedFile = null;
let currentJobId = null;

const MAX_POLL_ATTEMPTS = 300;

const FORMAT_LABELS = {
    md: "Markdown",
    pdf: "PDF",
    docx: "Word",
};

// --- Drop zone ---

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
        selectFile(e.dataTransfer.files[0]);
    }
});

fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        selectFile(fileInput.files[0]);
    }
});

clearFileBtn.addEventListener("click", () => {
    clearFile();
});

function selectFile(file) {
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatSize(file.size);
    fileInfo.hidden = false;
    submitBtn.disabled = false;
    dropZone.classList.add("has-file");
}

function clearFile() {
    selectedFile = null;
    fileInput.value = "";
    fileInfo.hidden = true;
    submitBtn.disabled = true;
    dropZone.classList.remove("has-file");
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

// --- Upload ---

uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("export_format", exportFormat.value);

    // Show file info in progress section
    progressFilename.textContent = selectedFile.name;
    progressFormat.textContent = FORMAT_LABELS[exportFormat.value] || exportFormat.value;

    submitBtn.disabled = true;
    showSection("progress");

    try {
        const resp = await fetch("/api/upload", {
            method: "POST",
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Błąd uploadu");
        }

        const data = await resp.json();
        currentJobId = data.job_id;
        startSSE(currentJobId);
    } catch (err) {
        showError(err.message);
    }
});

// --- SSE Progress ---

function startSSE(jobId) {
    const source = new EventSource(`/api/status/${jobId}/stream`);

    progressSection.classList.add("processing");

    source.onmessage = (event) => {
        const job = JSON.parse(event.data);
        updateProgress(job);

        if (job.status === "completed") {
            source.close();
            showResult(job);
        } else if (job.status === "failed") {
            source.close();
            showError(job.error || job.message || "Nieznany błąd");
        }
    };

    source.onerror = () => {
        source.close();
        setTimeout(() => checkFinalStatus(jobId, 0), 1000);
    };
}

async function checkFinalStatus(jobId, attempt) {
    if (attempt >= MAX_POLL_ATTEMPTS) {
        showError("Przekroczono limit czasu przetwarzania. Odśwież stronę i sprawdź status.");
        return;
    }

    try {
        const resp = await fetch(`/api/status/${jobId}`);
        if (!resp.ok) {
            showError("Nie udało się sprawdzić statusu przetwarzania.");
            return;
        }
        const job = await resp.json();
        updateProgress(job);

        if (job.status === "completed") {
            showResult(job);
        } else if (job.status === "failed") {
            showError(job.error || "Przetwarzanie nie powiodło się.");
        } else {
            setTimeout(() => checkFinalStatus(jobId, attempt + 1), 2000);
        }
    } catch {
        showError("Utracono połączenie z serwerem.");
    }
}

function updateProgress(job) {
    progressFill.style.width = job.progress + "%";
    progressPercent.textContent = job.progress + "%";
    progressMessage.textContent = job.message || "";

    const statusLabels = {
        pending: "Oczekiwanie...",
        processing: "Przetwarzanie pliku",
        transcribing: "Transkrypcja",
        structuring: "Strukturyzowanie notatki",
        exporting: "Eksportowanie",
        completed: "Ukończono",
        failed: "Błąd",
    };
    progressStatus.textContent = statusLabels[job.status] || job.status;
}

// --- Result ---

function showResult(job) {
    resultMessage.textContent = "Notatka została wygenerowana pomyślnie.";

    const baseName = (job.original_filename || "plik").replace(/\.[^.]+$/, "");
    const fmt = job.export_format || exportFormat.value;
    resultFilename.textContent = baseName + "_notatka." + fmt;
    resultFormat.textContent = FORMAT_LABELS[fmt] || fmt;

    showSection("result");
}

downloadBtn.addEventListener("click", () => {
    if (!currentJobId) return;
    window.location.href = `/api/download/${currentJobId}`;
});

newFileBtn.addEventListener("click", () => {
    reset();
});

retryBtn.addEventListener("click", () => {
    reset();
});

// --- Helpers ---

function showSection(name) {
    uploadSection.hidden = name !== "upload";
    progressSection.hidden = name !== "progress";
    resultSection.hidden = name !== "result";
    errorSection.hidden = name !== "error";
}

function showError(msg) {
    errorMessage.textContent = msg;
    showSection("error");
}

function reset() {
    currentJobId = null;
    clearFile();
    progressFill.style.width = "0%";
    progressPercent.textContent = "0%";
    progressStatus.textContent = "Oczekiwanie...";
    progressMessage.textContent = "";
    progressFilename.textContent = "";
    progressFormat.textContent = "";
    progressSection.classList.remove("processing");
    showSection("upload");
    submitBtn.disabled = true;
}
