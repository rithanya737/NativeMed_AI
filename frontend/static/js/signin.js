// async function redirectToLocalhostIfAvailable() {
//     if (window.location.protocol !== "file:") return;
//     try {
//         const response = await fetch("http://localhost:3000/signin.html", { method: "HEAD" });
//         if (response.ok) {
//             window.location.href = "http://localhost:3000/signin.html";
//         }
//     } catch (err) {
//         // server not running; stay on file-based page
//     }
// }

// redirectToLocalhostIfAvailable();

const togglePassword =
document.getElementById("togglePassword");

const password =
document.getElementById("password");

togglePassword.addEventListener("click",()=>{

    if(password.type==="password"){

        password.type="text";

        togglePassword.classList.remove("fa-eye");

        togglePassword.classList.add("fa-eye-slash");

    }

    else{

        password.type="password";

        togglePassword.classList.remove("fa-eye-slash");

        togglePassword.classList.add("fa-eye");

    }

});

const loginForm =
document.getElementById("loginForm");
const appBase = window.location.protocol === "file:" ? "http://localhost:3000" : window.location.origin;

loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    let email = document.getElementById("email").value;
    let password = document.getElementById("password").value;

    if (email === "" || password === "") {
        alert("Please fill all fields");
        return;
    }

    const submitBtn = loginForm.querySelector("button[type=submit]");
    if (submitBtn) submitBtn.disabled = true;

    try {
        const response = await fetch("/api/signin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        const data = await response.json();

        if (!response.ok) {
            alert(data.error || "Invalid email or password");
            return;
        }

        // loggedInUser is kept in sync for pages (e.g. identifyherb.js) that
        // still check localStorage instead of asking the server -- the real
        // gate is the session cookie /api/signin just set.
        localStorage.setItem("loggedInUser", email);
        window.location.href = data.redirect || "/dashboard";
    } catch (err) {
        console.error(err);
        alert("Something went wrong. Please try again.");
    } finally {
        if (submitBtn) submitBtn.disabled = false;
    }
});