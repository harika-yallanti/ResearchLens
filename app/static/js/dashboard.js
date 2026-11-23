
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";

import {
    getAuth,
    onAuthStateChanged,
    signOut
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";

const firebaseConfig = {
    apiKey: "AIzaSyB_R5rq51BhO4iPSWWVHMPtsYdtM4KDp8",
    authDomain: "researchlens-5cae7.firebaseapp.com",
    projectId: "researchlens-5cae7",
    storageBucket: "researchlens-5cae7.firebasestorage.app",
    messagingSenderId: "184971972362",
    appId: "1:184971972:web:81449c91ff0b7950e334f3"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

const profileName = document.getElementById("profileName");
const profileEmail = document.getElementById("profileEmail");
const profileAvatar = document.getElementById("profileAvatar");
const welcomeName = document.getElementById("welcomeName");
const logoutButton = document.getElementById("logoutButton");

function setProfile(name, email) {
    const safeName = name || "Researcher";
    const safeEmail = email || "Signed in";

    if (profileName) profileName.textContent = safeName;
    if (profileEmail) profileEmail.textContent = safeEmail;

    if (profileAvatar) {
        profileAvatar.textContent = safeName.charAt(0).toUpperCase();
    }

    if (welcomeName) {
        welcomeName.textContent = safeName.split(" ")[0];
    }
}

function initializeScoreBars() {
    document.querySelectorAll(".report-score-fill").forEach((bar) => {
        const score = Number(bar.dataset.score) || 0;
        bar.style.width = `${Math.min(100, Math.max(0, score))}%`;
    });
}

function initializeMobileMenu() {
    const sidebar = document.querySelector(".sidebar");
    const topbar = document.querySelector(".topbar");
    const pageHeading = document.querySelector(".page-heading");

    if (!sidebar || !topbar || !pageHeading) return;

    sidebar.id = "dashboardSidebar";

    let menuButton = document.getElementById("mobileMenuToggle");

    if (!menuButton) {
        menuButton = document.createElement("button");
        menuButton.type = "button";
        menuButton.className = "mobile-menu-toggle";
        menuButton.id = "mobileMenuToggle";
        menuButton.textContent = "☰";
        menuButton.setAttribute("aria-label", "Open navigation menu");
        menuButton.setAttribute("aria-expanded", "false");
        menuButton.setAttribute("aria-controls", "dashboardSidebar");

        topbar.insertBefore(menuButton, pageHeading);
    }

    let overlay = document.querySelector(".sidebar-overlay");

    if (!overlay) {
        overlay = document.createElement("div");
        overlay.className = "sidebar-overlay";
        document.body.appendChild(overlay);
    }

    function closeMenu() {
        document.body.classList.remove("sidebar-open");

        menuButton.textContent = "☰";
        menuButton.setAttribute("aria-expanded", "false");
        menuButton.setAttribute("aria-label", "Open navigation menu");
    }

    function openMenu() {
        document.body.classList.add("sidebar-open");

        menuButton.textContent = "×";
        menuButton.setAttribute("aria-expanded", "true");
        menuButton.setAttribute("aria-label", "Close navigation menu");
    }

    menuButton.addEventListener("click", () => {
        const isOpen = document.body.classList.contains("sidebar-open");

        if (isOpen) {
            closeMenu();
        } else {
            openMenu();
        }
    });

    overlay.addEventListener("click", closeMenu);

    sidebar.querySelectorAll(".sidebar-link").forEach((link) => {
        link.addEventListener("click", closeMenu);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMenu();
        }
    });

    window.addEventListener("resize", () => {
        if (window.innerWidth > 900) {
            closeMenu();
        }
    });
}

initializeScoreBars();
initializeMobileMenu();

onAuthStateChanged(auth, (user) => {
    if (!user) return;

    const name =
        user.displayName ||
        user.email?.split("@")[0] ||
        "Researcher";

    setProfile(
        profileName?.textContent.trim() || name,
        profileEmail?.textContent.trim() || user.email || ""
    );
});

if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
        logoutButton.disabled = true;

        try {
            const response = await fetch("/auth/logout", {
                method: "POST"
            });

            if (!response.ok) {
                throw new Error("Backend logout failed.");
            }

            await signOut(auth);
            window.location.href = "/login";

        } catch (error) {
            console.error("Logout error:", error);

            logoutButton.disabled = false;
            alert("Unable to sign out. Please try again.");
        }
    });
}
