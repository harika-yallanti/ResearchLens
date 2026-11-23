
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";

import {
    getAuth,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    GoogleAuthProvider,
    signInWithPopup,
    sendPasswordResetEmail,
    updateProfile,
    signOut
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyB_R5rq51BhO4iPSWWVHMPtsYdtM4KDpN8",
    authDomain: "researchlens-5cae7.firebaseapp.com",
    projectId: "researchlens-5cae7",
    storageBucket: "researchlens-5cae7.firebasestorage.app",
    messagingSenderId: "184971972362",
    appId: "1:184971972362:web:81449c91ff0b7950e334f3"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const googleProvider = new GoogleAuthProvider();

const authForm = document.getElementById("authForm");
const fullNameInput = document.getElementById("fullName");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const confirmPasswordInput = document.getElementById("confirmPassword");

const nameGroup = document.getElementById("nameGroup");
const confirmPasswordGroup = document.getElementById("confirmPasswordGroup");

const formTitle = document.getElementById("formTitle");
const formSubtitle = document.getElementById("formSubtitle");
const formEyebrow = document.getElementById("formEyebrow");

const submitButton = document.getElementById("submitButton");
const switchModeButton = document.getElementById("switchMode");
const switchText = document.getElementById("switchText");
const googleButton = document.getElementById("googleButton");
const forgotPasswordButton = document.getElementById("forgotPassword");

const formMessage = document.getElementById("formMessage");

const otpSection = document.getElementById("otpSection");
const otpForm = document.getElementById("otpForm");
const otpInput = document.getElementById("otpInput");
const otpMessage = document.getElementById("otpMessage");
const otpVerifyButton = document.getElementById("otpVerifyButton");
const resendOtpButton = document.getElementById("resendOtpButton");
const otpEmail = document.getElementById("otpEmail");
const backToLoginButton = document.getElementById("backToLogin");

const separatorElements = document.querySelectorAll(".separator");
const switchForm = document.querySelector(".switch-form");

let isRegisterMode = false;
let currentFirebaseUser = null;
let currentChallengeId = null;
let resendInterval = null;
let resendSeconds = 0;

function showMessage(message, type = "error") {
    formMessage.textContent = message;
    formMessage.className = `form-message visible ${type}`;
}

function clearMessage() {
    formMessage.textContent = "";
    formMessage.className = "form-message";
}

function showOTPMessage(message, type = "error") {
    otpMessage.textContent = message;
    otpMessage.className = `form-message visible ${type}`;
}

function clearOTPMessage() {
    otpMessage.textContent = "";
    otpMessage.className = "form-message";
}

function setLoading(isLoading) {
    submitButton.disabled = isLoading;
    googleButton.disabled = isLoading;

    if (isLoading) {
        submitButton.textContent = "Please wait...";
    } else {
        submitButton.textContent = isRegisterMode
            ? "Create account"
            : "Sign in";
    }
}

function setMode(registerMode) {
    isRegisterMode = registerMode;
    clearMessage();

    nameGroup.style.display = registerMode ? "flex" : "none";
    confirmPasswordGroup.style.display = registerMode ? "flex" : "none";

    forgotPasswordButton.style.display = registerMode
        ? "none"
        : "inline";

    fullNameInput.required = registerMode;
    confirmPasswordInput.required = registerMode;

    passwordInput.autocomplete = registerMode
        ? "new-password"
        : "current-password";

    formEyebrow.textContent = registerMode
        ? "CREATE YOUR ACCOUNT"
        : "WELCOME BACK";

    formTitle.textContent = registerMode
        ? "Create your account"
        : "Sign in to your account";

    formSubtitle.textContent = registerMode
        ? "Start improving your research with ResearchLens."
        : "Continue your research journey with ResearchLens.";

    switchText.textContent = registerMode
        ? "Already have an account?"
        : "Don't have an account?";

    switchModeButton.textContent = registerMode
        ? "Sign in"
        : "Create account";

    submitButton.textContent = registerMode
        ? "Create account"
        : "Sign in";
}

function getDashboardPath(user) {
    return user?.is_admin === true
        ? "/admin/dashboard"
        : "/dashboard";
}

async function getFirebaseToken() {
    if (!currentFirebaseUser) {
        throw new Error(
            "Your login session expired. Please sign in again."
        );
    }

    return await currentFirebaseUser.getIdToken(true);
}

async function syncUserWithBackend(firebaseUser) {
    currentFirebaseUser = firebaseUser;

    const idToken = await firebaseUser.getIdToken(true);

    const response = await fetch("/auth/verify", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            id_token: idToken
        })
    });

    const result = await response.json();

    if (!response.ok) {
        throw new Error(
            result.detail || "Unable to verify your account."
        );
    }

    if (
        result.status !== "otp_required" ||
        !result.challenge_id
    ) {
        throw new Error(
            "Unable to start email verification."
        );
    }

    currentChallengeId = result.challenge_id;

    showOTPScreen(
        result.user?.email || firebaseUser.email
    );

    return result;
}

function showOTPScreen(email) {
    authForm.style.display = "none";
    otpSection.style.display = "block";

    googleButton.style.display = "none";

    separatorElements.forEach((element) => {
        element.style.display = "none";
    });

    switchForm.style.display = "none";

    formEyebrow.textContent = "EMAIL VERIFICATION";
    formTitle.textContent = "Verify your email";
    formSubtitle.textContent =
        "One more step to access your ResearchLens account.";

    otpEmail.textContent = email || "your registered email";

    otpInput.value = "";

    clearMessage();
    clearOTPMessage();

    startResendCountdown(60);

    setTimeout(() => {
        otpInput.focus();
    }, 100);
}

function showLoginScreen() {
    otpSection.style.display = "none";
    authForm.style.display = "block";

    googleButton.style.display = "";
    separatorElements.forEach((element) => {
        element.style.display = "";
    });

    switchForm.style.display = "";

    currentFirebaseUser = null;
    currentChallengeId = null;

    clearResendCountdown();
    clearOTPMessage();

    setMode(false);
}

function clearResendCountdown() {
    if (resendInterval) {
        clearInterval(resendInterval);
        resendInterval = null;
    }
}

function updateResendButton() {
    if (resendSeconds > 0) {
        resendOtpButton.textContent =
            `Resend code in ${resendSeconds}s`;
        resendOtpButton.disabled = true;
    } else {
        resendOtpButton.textContent = "Resend code";
        resendOtpButton.disabled = false;
    }
}

function startResendCountdown(seconds) {
    clearResendCountdown();

    resendSeconds = seconds;
    updateResendButton();

    resendInterval = setInterval(() => {
        resendSeconds--;

        updateResendButton();

        if (resendSeconds <= 0) {
            clearResendCountdown();
        }
    }, 1000);
}

async function verifyOTP(event) {
    event.preventDefault();

    clearOTPMessage();

    const otp = otpInput.value.trim();

    if (!/^\d{6}$/.test(otp)) {
        showOTPMessage(
            "Please enter a valid six-digit verification code."
        );
        return;
    }

    if (!currentChallengeId || !currentFirebaseUser) {
        showOTPMessage(
            "Your verification session has expired. Please sign in again."
        );
        return;
    }

    otpVerifyButton.disabled = true;
    otpVerifyButton.textContent = "Verifying...";

    try {
        const idToken = await getFirebaseToken();

        const response = await fetch("/auth/otp/verify", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                id_token: idToken,
                challenge_id: currentChallengeId,
                otp: otp
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || "Unable to verify the code."
            );
        }

        clearResendCountdown();

        showOTPMessage(
            "Verification successful. Redirecting...",
            "success"
        );

        window.location.href = getDashboardPath(result.user);

    } catch (error) {
        showOTPMessage(
            error.message || "Verification failed."
        );
    } finally {
        otpVerifyButton.disabled = false;
        otpVerifyButton.textContent = "Verify and continue";
    }
}

async function resendOTP() {
    clearOTPMessage();

    if (!currentChallengeId || !currentFirebaseUser) {
        showOTPMessage(
            "Your verification session has expired. Please sign in again."
        );
        return;
    }

    resendOtpButton.disabled = true;
    resendOtpButton.textContent = "Sending...";

    try {
        const idToken = await getFirebaseToken();

        const response = await fetch("/auth/otp/resend", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                id_token: idToken,
                challenge_id: currentChallengeId
            })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(
                result.detail || "Unable to resend the verification code."
            );
        }

        otpInput.value = "";

        showOTPMessage(
            "A new verification code has been sent to your email.",
            "success"
        );

        startResendCountdown(60);

    } catch (error) {
        showOTPMessage(
            error.message || "Unable to resend the code."
        );

        const waitMatch = error.message.match(/wait\s+(\d+)\s+seconds/i);

        if (waitMatch) {
            startResendCountdown(Number(waitMatch[1]));
        } else {
            resendOtpButton.disabled = false;
            resendOtpButton.textContent = "Resend code";
        }
    }
}

switchModeButton.addEventListener("click", () => {
    setMode(!isRegisterMode);
});

document.querySelectorAll(".password-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const targetId = button.dataset.target;
        const targetInput = document.getElementById(targetId);

        const isPassword = targetInput.type === "password";

        targetInput.type = isPassword ? "text" : "password";

        button.setAttribute(
            "aria-label",
            isPassword ? "Hide password" : "Show password"
        );
    });
});

authForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    clearMessage();

    const email = emailInput.value.trim();
    const password = passwordInput.value;

    if (isRegisterMode) {
        const fullName = fullNameInput.value.trim();
        const confirmPassword = confirmPasswordInput.value;

        if (!fullName) {
            showMessage("Please enter your full name.");
            return;
        }

        if (password.length < 6) {
            showMessage(
                "Password must contain at least 6 characters."
            );
            return;
        }

        if (password !== confirmPassword) {
            showMessage("The passwords do not match.");
            return;
        }

        try {
            setLoading(true);

            const userCredential = await createUserWithEmailAndPassword(
                auth,
                email,
                password
            );

            await updateProfile(userCredential.user, {
                displayName: fullName
            });

            await syncUserWithBackend(userCredential.user);

        } catch (error) {
            showMessage(
                getFriendlyError(error.code, error.message)
            );
        } finally {
            setLoading(false);
        }

    } else {
        try {
            setLoading(true);

            const userCredential = await signInWithEmailAndPassword(
                auth,
                email,
                password
            );

            await syncUserWithBackend(userCredential.user);

        } catch (error) {
            showMessage(
                getFriendlyError(error.code, error.message)
            );
        } finally {
            setLoading(false);
        }
    }
});

googleButton.addEventListener("click", async () => {
    clearMessage();

    try {
        setLoading(true);

        const userCredential = await signInWithPopup(
            auth,
            googleProvider
        );

        await syncUserWithBackend(userCredential.user);

    } catch (error) {
        showMessage(
            getFriendlyError(error.code, error.message)
        );
    } finally {
        setLoading(false);
    }
});

otpForm.addEventListener("submit", verifyOTP);

otpInput.addEventListener("input", () => {
    otpInput.value = otpInput.value
        .replace(/\D/g, "")
        .slice(0, 6);
});

resendOtpButton.addEventListener("click", resendOTP);

backToLoginButton.addEventListener("click", async () => {
    clearOTPMessage();
    clearResendCountdown();

    try {
        await signOut(auth);
    } catch (error) {
        console.error("Sign-out error:", error);
    }

    showLoginScreen();
});

forgotPasswordButton.addEventListener("click", async () => {
    clearMessage();

    const email = emailInput.value.trim();

    if (!email) {
        showMessage(
            "Enter your email address first to reset your password."
        );

        emailInput.focus();
        return;
    }

    try {
        await sendPasswordResetEmail(auth, email);

        showMessage(
            "If an account exists for this email, a password reset email will be sent.",
            "success"
        );

    } catch (error) {
        showMessage(
            getFriendlyError(error.code, error.message)
        );
    }
});

function getFriendlyError(errorCode, fallbackMessage = "") {
    const errorMessages = {
        "auth/email-already-in-use":
            "An account already exists with this email.",

        "auth/invalid-email":
            "Please enter a valid email address.",

        "auth/invalid-credential":
            "Incorrect email or password.",

        "auth/user-not-found":
            "No account was found with these details.",

        "auth/wrong-password":
            "Incorrect email or password.",

        "auth/weak-password":
            "Please choose a stronger password.",

        "auth/popup-closed-by-user":
            "The Google sign-in window was closed.",

        "auth/popup-blocked":
            "Your browser blocked the Google sign-in popup.",

        "auth/network-request-failed":
            "Network error. Please check your connection.",

        "auth/too-many-requests":
            "Too many attempts. Please try again later."
    };

    return errorMessages[errorCode] ||
        fallbackMessage ||
        "Something went wrong. Please try again.";
}

setMode(false);
