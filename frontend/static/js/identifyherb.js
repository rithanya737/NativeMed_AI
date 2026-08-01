const dropArea = document.getElementById("dropArea");
const fileInput = document.getElementById("fileInput");
const previewImage = document.getElementById("previewImage");
const analyzeBtn = document.getElementById("analyzeBtn");
const resultArea = document.getElementById("resultArea");
const cameraVideo = document.getElementById("cameraVideo");
const cameraCanvas = document.getElementById("cameraCanvas");
const cameraBtn = document.getElementById("cameraBtn");
const captureBtn = document.getElementById("captureBtn");
const cancelCameraBtn = document.getElementById("cancelCameraBtn");
const cameraControls = document.getElementById("cameraControls");
const actionButtons = document.getElementById("actionButtons");
const explainToggle = document.getElementById("explainToggle");

let selectedFile = null;
let cameraStream = null;

function setSelectedFile(file) {
    if (!file) return;

    if (!file.type || !file.type.startsWith("image/")) {
        renderError("Please choose an image file (PNG or JPG).");
        return;
    }

    selectedFile = file;
    const reader = new FileReader();
    reader.onload = function(event) {
        previewImage.src = event.target.result;
        previewImage.style.display = "block";
    };
    reader.readAsDataURL(file);

    // Reset result area whenever a new image is chosen
    resultArea.innerHTML = `
        <p class="placeholder">
            Click "Run AI Analysis" to identify this plant.
        </p>
    `;
}

function setLoadingState(isLoading) {
    analyzeBtn.disabled = isLoading;
    analyzeBtn.innerHTML = isLoading
        ? `<i class="fa-solid fa-spinner fa-spin"></i> Analyzing...`
        : `<i class="fa-solid fa-wand-magic-sparkles"></i> Run AI Analysis`;
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
}

function renderResult(plant) {
    let resultHtml = `
        <div class="result-box">
            <h3>🌿 ${escapeHtml(plant.commonName)}</h3>
    `;

    if (plant.scientificName) {
        resultHtml += `<p><strong>Scientific Name:</strong> <em>${escapeHtml(plant.scientificName)}</em></p>`;
    }

    resultHtml += `<p><strong>Confidence:</strong> ${escapeHtml(plant.confidence)}%</p>`;

    if (plant.hasDetailedInfo) {
        if (plant.medicinalProperties) {
            resultHtml += `<p><strong>Medicinal Properties:</strong> ${escapeHtml(plant.medicinalProperties)}</p>`;
        }
        if (plant.traditionalUses) {
            resultHtml += `<p><strong>Traditional Uses:</strong> ${escapeHtml(plant.traditionalUses)}</p>`;
        }
        if (plant.diseasesTreated) {
            resultHtml += `<p><strong>Diseases Treated:</strong> ${escapeHtml(plant.diseasesTreated)}</p>`;
        }
        if (plant.culturalSignificance) {
            resultHtml += `<p><strong>Cultural Significance:</strong> ${escapeHtml(plant.culturalSignificance)}</p>`;
        }
        if (plant.preparationMethod) {
            resultHtml += `<p><strong>Preparation Method:</strong> ${escapeHtml(plant.preparationMethod)}</p>`;
        }
        if (plant.howToTake) {
            resultHtml += `<p><strong>How To Take / Apply:</strong> ${escapeHtml(plant.howToTake)}</p>`;
        }
        if (plant.generalDisclaimer) {
            resultHtml += `<p class="disclaimer-note"><em>${escapeHtml(plant.generalDisclaimer)}</em></p>`;
        }
    } else {
        resultHtml += `<p><em>${escapeHtml(plant.note || "Detailed medicinal information for this plant is not available in our database.")}</em></p>`;
    }

    if (plant.explanation) {
        const fidelityPct = Math.round(Math.max(0, plant.explanation.fidelityScore) * 100);
        const fidelityLabel = plant.explanation.fidelityLabel || "unknown";
        resultHtml += `
            <div class="explanation-box">
                <h4><i class="fa-solid fa-magnifying-glass-chart"></i> AI Explanation (LIME)</h4>
                <img
                    class="explanation-image"
                    src="data:image/png;base64,${plant.explanation.overlayImageBase64}"
                    alt="Highlighted regions the AI used to identify this plant">
                <p class="explanation-score fidelity-${escapeHtml(fidelityLabel)}">
                    <strong>Explanation reliability:</strong> ${escapeHtml(fidelityLabel)} (score: ${escapeHtml(String(fidelityPct))}%)
                </p>
                <p class="explanation-note">${escapeHtml(plant.explanation.fidelityNote)}</p>
                <p class="explanation-note">${escapeHtml(plant.explanation.note)}</p>
            </div>
        `;
    } else if (plant.explanationError) {
        resultHtml += `
            <div class="explanation-box">
                <p class="explanation-note">⚠️ ${escapeHtml(plant.explanationError)}</p>
            </div>
        `;
    }

    resultHtml += `</div>`;
    resultArea.innerHTML = resultHtml;
}

/**
 * Camera capture (via getUserMedia). Works over http://localhost / 127.0.0.1
 * and https:// origins -- browsers treat those as "secure enough" for
 * camera access. It will NOT work if the site is loaded over plain http
 * from a non-localhost address (e.g. a LAN IP); browsers block camera
 * access on insecure origins in that case.
 */
async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        renderError("Your browser doesn't support camera access. Please upload a photo instead.");
        return;
    }

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" },
            audio: false
        });
    } catch (error) {
        console.error("Camera error:", error);
        if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
            renderError("Camera access was blocked. Please allow camera permission for this site and try again.");
        } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
            renderError("No camera was found on this device.");
        } else if (error.name === "NotReadableError") {
            renderError("Your camera is already in use by another app.");
        } else {
            renderError("Unable to access the camera: " + error.message);
        }
        return;
    }

    cameraVideo.srcObject = cameraStream;
    cameraVideo.style.display = "block";
    previewImage.style.display = "none";

    cameraControls.hidden = false;
    actionButtons.hidden = true;
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
    }
    cameraVideo.srcObject = null;
    cameraVideo.style.display = "none";

    cameraControls.hidden = true;
    actionButtons.hidden = false;
}

function capturePhoto() {
    if (!cameraStream) return;

    const width = cameraVideo.videoWidth;
    const height = cameraVideo.videoHeight;
    if (!width || !height) {
        renderError("Camera isn't ready yet -- please wait a moment and try again.");
        return;
    }

    cameraCanvas.width = width;
    cameraCanvas.height = height;
    cameraCanvas.getContext("2d").drawImage(cameraVideo, 0, 0, width, height);

    cameraCanvas.toBlob((blob) => {
        if (!blob) {
            renderError("Couldn't capture a photo from the camera. Please try again.");
            return;
        }
        const file = new File([blob], `camera-capture-${Date.now()}.jpg`, { type: "image/jpeg" });
        stopCamera();
        setSelectedFile(file);
    }, "image/jpeg", 0.92);
}

function renderError(message) {
    resultArea.innerHTML = `
        <div class="result-box">
            <p style="color: #b00020;">⚠️ ${escapeHtml(message)}</p>
        </div>
    `;
}

/**
 * Sends the selected image to your backend for identification.
 * Replace the URL below with your real Flask endpoint once it's built
 * (e.g. an endpoint that runs a proper ML model server-side).
 */
async function analyzeImage() {
    if (!selectedFile) {
        renderError("Please upload an image first.");
        return;
    }

    const explain = Boolean(explainToggle && explainToggle.checked);

    try {
        setLoadingState(true);
        resultArea.innerHTML = `
            <div class="result-box">
                <p>${explain ? "🔍 Analyzing your plant image and building the AI explanation (this can take a while -- please be patient)..." : "🔍 Analyzing your plant image..."}</p>
            </div>
        `;

        const formData = new FormData();
        formData.append("image", selectedFile);

        const url = explain ? "/api/identify-plant?explain=true" : "/api/identify-plant";
        const response = await fetch(url, {
            method: "POST",
            body: formData
        });

        if (response.status === 401) { window.location.href = "/signin"; return; }
        if (!response.ok) {
            renderError("The server had trouble processing your image. Please try again.");
            return;
        }

        const data = await response.json();

        renderResult({
            commonName: data.common_name || "Unknown Plant",
            scientificName: data.scientific_name || "—",
            confidence: data.confidence ?? "—",
            hasDetailedInfo: Boolean(
                data.medicinal_properties || data.traditional_uses ||
                data.diseases_treated || data.cultural_significance ||
                data.preparation_method || data.how_to_take
            ),
            medicinalProperties: data.medicinal_properties,
            traditionalUses: data.traditional_uses,
            diseasesTreated: data.diseases_treated,
            culturalSignificance: data.cultural_significance,
            preparationMethod: data.preparation_method,
            howToTake: data.how_to_take,
            generalDisclaimer: data.general_disclaimer,
            note: data.note || data.message,
            explanation: data.explanation
                ? {
                    overlayImageBase64: data.explanation.overlay_image_base64,
                    note: data.explanation.note,
                    fidelityScore: data.explanation.fidelity_score,
                    fidelityLabel: data.explanation.fidelity_label,
                    fidelityNote: data.explanation.fidelity_note
                }
                : null,
            explanationError: data.explanation_error || null
        });

    } catch (error) {
        console.error("Analysis error:", error);
        renderError("Unable to analyze image right now. Please try again.");
    } finally {
        setLoadingState(false);
    }
}

/* CLICK TO UPLOAD */

dropArea.addEventListener("click", () => {
    if (cameraStream) return; // don't open the file picker while the camera is live
    fileInput.click();
});

/* CAMERA */

cameraBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    startCamera();
});

captureBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    capturePhoto();
});

cancelCameraBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    stopCamera();
});

window.addEventListener("beforeunload", stopCamera);

/* FILE SELECT */

fileInput.addEventListener("change", function() {
    const file = this.files[0];
    setSelectedFile(file);
});

/* DRAG DROP */

dropArea.addEventListener("dragover", (e) => {
    e.preventDefault();
});

dropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    setSelectedFile(file);
});

analyzeBtn.addEventListener("click", analyzeImage);

const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
        localStorage.removeItem("loggedInUser");
        window.location.href = "/logout";
    });
}


