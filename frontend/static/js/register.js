async function redirectToLocalhostIfAvailable() {
    if (window.location.protocol !== "file:") return;
    try {
        const response = await fetch("http://localhost:3000/register.html", { method: "HEAD" });
        if (response.ok) {
            window.location.href = "http://localhost:3000/register.html";
        }
    } catch (err) {
        // server not running; stay on file-based page
    }
}

redirectToLocalhostIfAvailable();

const togglePassword =
document.getElementById("togglePassword");

const password =
document.getElementById("password");

togglePassword.addEventListener("click",()=>{

    if(password.type==="password"){

        password.type="text";
        togglePassword.classList.replace(
            "fa-eye",
            "fa-eye-slash"
        );

    }else{

        password.type="password";
        togglePassword.classList.replace(
            "fa-eye-slash",
            "fa-eye"
        );

    }

});

document
.getElementById("registerForm")
.addEventListener("submit", async (e) => {

    e.preventDefault();

    const fullname =
    document.getElementById("fullname").value;

    const email =
    document.getElementById("email").value;

    const password =
    document.getElementById("password").value;

    const confirmPassword =
    document.getElementById("confirmPassword").value;

    const country =
    document.getElementById("country").value;

    if(password !== confirmPassword){

        alert("Passwords do not match");
        return;

    }

    const submitBtn = document.querySelector("#registerForm button[type=submit]");
    if (submitBtn) submitBtn.disabled = true;

    try {
        const response = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                full_name: fullname,
                email,
                password,
                confirm_password: confirmPassword,
                country,
            }),
        });
        const data = await response.json();

        if (!response.ok) {
            alert(data.error || "Registration failed. Please try again.");
            return;
        }

        // Kept in sync for pages that still check localStorage -- the real
        // gate is the session cookie /api/register just set (it also logs
        // the new account straight in, same as before).
        localStorage.setItem("loggedInUser", email);

        alert("Registration Successful");
        window.location.href = data.redirect || "/dashboard";
    } catch (err) {
        console.error(err);
        alert("Something went wrong. Please try again.");
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }

});