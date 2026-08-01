const popup = document.getElementById("popup");

const popupImage = document.getElementById("popupImage");
const popupName = document.getElementById("popupName");
const popupScientific = document.getElementById("popupScientific");
const popupProperties = document.getElementById("popupProperties");
const popupUses = document.getElementById("popupUses");
const popupCulture = document.getElementById("popupCulture");
const popupDisease = document.getElementById("popupDisease");
const popupPrep = document.getElementById("popupPrep");
const popupHowToTake = document.getElementById("popupHowToTake");
const popupDisclaimer = document.getElementById("popupDisclaimer");

const closeBtn = document.getElementById("closePopup");

document.querySelectorAll(".view-btn").forEach(button => {
    button.addEventListener("click", () => {
        popup.style.display = "flex";

        popupImage.src = button.dataset.image || "";
        popupImage.alt = button.dataset.name || "";

        popupName.textContent = button.dataset.name || "";
        popupScientific.textContent = button.dataset.scientific || "";
        popupProperties.textContent = button.dataset.properties || "Not documented.";
        popupUses.textContent = button.dataset.uses || "Not documented.";
        popupCulture.textContent = button.dataset.cultural || "Not documented.";
        popupDisease.textContent = button.dataset.disease || "Not documented.";
        popupPrep.textContent = button.dataset.prep || "Not documented.";
        popupHowToTake.textContent = button.dataset.howtotake || "Not documented.";
        popupDisclaimer.textContent = button.dataset.disclaimer || "";
    });
});

closeBtn.onclick = function () {
    popup.style.display = "none";
};

window.onclick = function (e) {
    if (e.target === popup) {
        popup.style.display = "none";
    }
};

document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") popup.style.display = "none";
});

// ---------- Live search ----------
const liveSearch = document.getElementById("liveSearch");
const cardContainer = document.getElementById("cardContainer");
const noResults = document.getElementById("noResults");

if (liveSearch) {
    liveSearch.addEventListener("input", () => {
        const term = liveSearch.value.trim().toLowerCase();
        const cards = cardContainer.querySelectorAll(".card");
        let visibleCount = 0;

        cards.forEach(card => {
            const matches = card.dataset.search.includes(term);
            card.style.display = matches ? "flex" : "none";
            if (matches) visibleCount++;
        });

        noResults.classList.toggle("hidden", visibleCount > 0);
    });
}
