function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email || "");
}

function showError(message) {
    const error = document.getElementById("error");
    if (!error) return;
    error.textContent = message;
    error.classList.add("visible");
    error.style.display = "block";
}

function hideError() {
    const error = document.getElementById("error");
    if (!error) return;
    error.textContent = "";
    error.classList.remove("visible");
    error.style.display = "none";
}

async function isRegister() {
    window.isRegistration = !window.isRegistration;
    const register = document.getElementById("registerBtn");
    const title = document.querySelector("#auth h2, #auth .sign-up-text");
    const hint = document.querySelector(".register-content p");

    if (register) register.textContent = window.isRegistration ? "Sign in" : "Sign up";
    if (title) title.textContent = window.isRegistration ? "Sign up" : "Login";
    if (hint) {
        hint.textContent = window.isRegistration
            ? "Already have an account?"
            : "Don't have an account?";
    }
}

async function authenticate() {
    const auth = document.getElementById("authBtn");
    const emailInput = document.getElementById("emailInput");
    const passwordInput =
        document.getElementById("passwordInput") ||
        document.getElementById("passowrdInput");
    const emailVal = (emailInput && emailInput.value || "").trim();
    const passVal = passwordInput && passwordInput.value || "";

    if (window.isAuthenticating || !emailVal || !passVal) {
        showError("Please fill in both fields.");
        return;
    }
    if (!isValidEmail(emailVal) || passVal.length < 6) {
        showError("Enter a valid email and a password of at least 6 characters.");
        return;
    }

    hideError();
    window.isAuthenticating = true;
    if (auth) auth.textContent = "Authenticating...";

    const path = window.isRegistration ? "/register" : "/login";

    try {
        const response = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: emailVal, password: passVal })
        });
        const data = await response.json().catch(function () { return {}; });

        if (data.token) {
            localStorage.setItem("token", data.token);
            window.location.href = "/chart";
            return;
        }
        throw new Error(data.message || "Failed to authenticate.");
    } catch (err) {
        showError(err.message);
    } finally {
        if (auth) auth.textContent = "Submit";
        window.isAuthenticating = false;
    }
}

function logout() {
    localStorage.removeItem("token");
    window.location.href = "/login";
}

window.isRegistration = false;
window.isAuthenticating = false;
