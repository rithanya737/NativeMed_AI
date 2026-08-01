function showToast(message, type = "success") {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
    setTimeout(() => toast.classList.add("hidden"), 4000);
}

// ---------- Profile update ----------
document.getElementById("profileForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const payload = {
        full_name: document.getElementById("full_name").value.trim(),
        email: document.getElementById("email").value.trim(),
        country: document.getElementById("country").value.trim(),
    };

    try {
        const response = await fetch("/api/update-profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            showToast(data.error || "Failed to update profile", "error");
            return;
        }

        showToast(data.message || "Profile updated successfully");
    } catch (err) {
        console.error(err);
        showToast("Something went wrong. Please try again.", "error");
    }
});

// ---------- Password change ----------
document.getElementById("passwordForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const payload = {
        current_password: document.getElementById("current_password").value,
        new_password: document.getElementById("new_password").value,
        confirm_password: document.getElementById("confirm_password").value,
    };

    try {
        const response = await fetch("/api/change-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();

        if (!response.ok) {
            showToast(data.error || "Failed to change password", "error");
            return;
        }

        showToast(data.message || "Password changed successfully");
        document.getElementById("passwordForm").reset();
    } catch (err) {
        console.error(err);
        showToast("Something went wrong. Please try again.", "error");
    }
});

// ---------- Delete account modal ----------
const deleteModal = document.getElementById("deleteModal");

document.getElementById("deleteAccountBtn").addEventListener("click", () => {
    deleteModal.classList.remove("hidden");
});

document.getElementById("cancelDeleteBtn").addEventListener("click", () => {
    deleteModal.classList.add("hidden");
    document.getElementById("deleteConfirmPassword").value = "";
});

document.getElementById("confirmDeleteBtn").addEventListener("click", async () => {
    const password = document.getElementById("deleteConfirmPassword").value;
    if (!password) {
        showToast("Enter your password to confirm deletion", "error");
        return;
    }

    try {
        const response = await fetch("/api/delete-account", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password }),
        });
        const data = await response.json();

        if (!response.ok) {
            showToast(data.error || "Failed to delete account", "error");
            return;
        }

        localStorage.removeItem("loggedInUser");
        window.location.href = data.redirect || "/";
    } catch (err) {
        console.error(err);
        showToast("Something went wrong. Please try again.", "error");
    }
});
// ---------- Sign out ----------
document.getElementById("logoutBtn").addEventListener("click", () => {
    localStorage.removeItem("loggedInUser");
    window.location.href = "/logout";
});