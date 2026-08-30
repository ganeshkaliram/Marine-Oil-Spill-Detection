/* ==========================================================================
   College SIH 2026 - Landing Page (app.js)
   ========================================================================== */

const API = {
    get: async (path) => {
        const res = await fetch(path);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || "Request failed");
        return res.json();
    },
    post: async (path, body) => {
        const res = await fetch(path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Request failed");
        return data;
    },
};

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

const DIFF_CLASS = { Hard: "diff-hard", Medium: "diff-medium", Easy: "diff-easy" };
const TOKEN_KEY = "sih2026_token";

if (sessionStorage.getItem(TOKEN_KEY)) {
    window.location.href = "dashboard.html";
}

/* ---------- Problem Statements ---------- */
let allProblems = [];
let activeTheme = "All";

function renderProblemCard(p) {
    return `
        <div class="problem-card reveal">
            <div class="top">
                <span class="badge theme">${esc(p.theme)}</span>
                <span class="badge ${DIFF_CLASS[p.difficulty] || "diff-medium"}">${esc(p.difficulty)}</span>
            </div>
            <h3>${esc(p.title)}</h3>
            <p class="desc">${esc(p.description)}</p>
            <div class="problem-meta">
                <span>${esc(p.org)}</span>
                <span>${esc(p.id)}</span>
            </div>
        </div>`;
}

function renderThemeChips() {
    const themes = [...new Set(allProblems.map((p) => p.theme))];
    const chips = ["All", ...themes];
    $("#themeChips").innerHTML = chips
        .map((t) => `<button class="chip ${t === activeTheme ? "active" : ""}" data-theme="${esc(t)}">${esc(t)}</button>`)
        .join("");
    document.querySelectorAll("#themeChips .chip").forEach((chip) => {
        chip.addEventListener("click", () => {
            activeTheme = chip.dataset.theme;
            renderThemeChips();
            renderProblems();
        });
    });
}

function renderProblems() {
    const q = ($("#problemSearch").value || "").toLowerCase().trim();
    const filtered = allProblems.filter((p) => {
        const matchesTheme = activeTheme === "All" || p.theme === activeTheme;
        const matchesQuery = (p.title + " " + p.theme + " " + p.org + " " + p.description).toLowerCase().includes(q);
        return matchesTheme && matchesQuery;
    });

    const grid = $("#problemsGrid");
    if (!filtered.length) {
        grid.innerHTML = `<div class="empty-state">No problem statements match your search.</div>`;
        return;
    }
    grid.innerHTML = filtered.map(renderProblemCard).join("");
    observeReveals();
}

async function loadProblems() {
    try {
        allProblems = await API.get("/api/problems");
        renderThemeChips();
        renderProblems();
    } catch (e) {
        $("#problemsGrid").innerHTML = `<div class="empty-state">Could not load problems.</div>`;
    }
}

$("#problemSearch").addEventListener("input", renderProblems);

/* ---------- Timeline ---------- */
async function loadTimeline() {
    try {
        const items = await API.get("/api/timeline");
        $("#timeline").innerHTML = items
            .map((t) => `
                <div class="tl-item reveal">
                    <div class="date">${esc(t.date)}</div>
                    <h3>${esc(t.title)}</h3>
                    <p>${esc(t.detail)}</p>
                </div>`)
            .join("");
        observeReveals();
    } catch (e) {
        $("#timeline").innerHTML = `<div class="empty-state">Could not load timeline.</div>`;
    }
}

/* ---------- Teams (public browse) ---------- */
function teamStats(members) {
    const count = (members || []).filter((m) => m && m.name).length;
    const girls = (members || []).filter((m) => m && m.gender === "Female").length;
    const departments = new Set((members || []).filter((m) => m && m.department).map((m) => m.department)).size;
    return {
        count,
        girls,
        departments,
        valid: count === 6 && girls >= 2 && departments >= 2,
    };
}

async function loadTeams() {
    try {
        const teams = await API.get("/api/teams");
        const grid = $("#teamsGrid");
        if (!teams.length) {
            grid.innerHTML = `<div class="empty-state">No teams yet. Log in to create the first one!</div>`;
            return;
        }
        grid.innerHTML = teams.map((t) => {
            const members = (t.members || [])
                .map((m) => `<span class="team-member">${esc(m.name)}<span class="role">· ${esc(m.gender || "")} · ${esc(m.department || "")}</span></span>`)
                .join("");
            const looking = (t.lookingFor || []).join(", ");
            const stats = teamStats(t.members || []);
            const valid = stats.valid
                ? `<span class="badge status-selected">Valid team</span>`
                : (stats.count === 6
                    ? `<span class="badge status-rejected">Does not meet rules</span>`
                    : `<span class="badge status-pending">${stats.count}/6 members</span>`);
            return `
                <div class="team-card reveal">
                    <h3>${esc(t.name)}</h3>
                    <span class="problem-link">${t.problemId ? "Problem: " + esc(t.problemTitle || t.problemId) : "No problem statement assigned yet"}</span>
                    <div class="team-members">${members || "<span class='team-member'>No members listed</span>"}</div>
                    <div class="team-stats">
                        <span class="badge theme">${stats.count}/${6} members</span>
                        <span class="badge ${stats.girls >= 2 ? "status-selected" : "status-rejected"}">${stats.girls} girls</span>
                        <span class="badge ${stats.departments >= 2 ? "status-selected" : "status-rejected"}">${stats.departments} departments</span>
                        ${valid}
                    </div>
                    <p class="looking-for">${looking ? "<strong>Looking for:</strong> " + esc(looking) : ""}</p>
                </div>`;
        }).join("");
        observeReveals();
    } catch (e) {
        $("#teamsGrid").innerHTML = `<div class="empty-state">Could not load teams.</div>`;
    }
}

/* ---------- Announcements ---------- */
async function loadAnnouncements() {
    try {
        const items = await API.get("/api/announcements");
        $("#announceList").innerHTML = items
            .map((a) => `
                <div class="announce reveal">
                    <div class="date">${esc(a.date || "")}</div>
                    <h3>${esc(a.title)}</h3>
                    <p>${esc(a.body)}</p>
                </div>`)
            .join("");
        observeReveals();
    } catch (e) {
        $("#announceList").innerHTML = `<div class="empty-state">Could not load announcements.</div>`;
    }
}

/* ---------- Stats ---------- */
async function loadStats() {
    try {
        const s = await API.get("/api/stats");
        $("#statsGrid").innerHTML = `
            <div><div class="stat-num">${s.problems}</div><div class="stat-label">Problem Statements</div></div>
            <div><div class="stat-num">${s.students}</div><div class="stat-label">Students Registered</div></div>
            <div><div class="stat-num">${s.teams}</div><div class="stat-label">Teams Formed</div></div>
            <div><div class="stat-num">${s.themes}</div><div class="stat-label">Domains / Themes</div></div>`;
    } catch (e) { /* keep defaults */ }
}

/* ---------- Auth: toggle ---------- */
document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".auth-tab").forEach((t) => t.classList.toggle("active", t === tab));
        const form = tab.dataset.form;
        $("#loginCard").classList.toggle("hidden", form !== "login");
        $("#registerCard").classList.toggle("hidden", form !== "register");
    });
});

/* ---------- Auth: register ---------- */
const languages = [];
const langSet = new Set();

function renderLangTags() {
    $("#rLangTags").innerHTML = languages
        .map((s) => `<span class="skill-tag">${esc(s)}<button type="button" data-lang="${esc(s)}">&times;</button></span>`)
        .join("");
    document.querySelectorAll("#rLangTags .skill-tag button").forEach((btn) => {
        btn.addEventListener("click", () => {
            langSet.delete(btn.dataset.lang);
            languages.length = 0;
            languages.push(...langSet);
            renderLangTags();
        });
    });
}

function addLanguage() {
    const input = $("#rLanguage");
    const val = input.value.trim();
    if (!val || langSet.has(val)) { input.value = ""; return; }
    langSet.add(val);
    languages.push(val);
    input.value = "";
    renderLangTags();
}

$("#addLangBtn").addEventListener("click", addLanguage);
$("#rLanguage").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addLanguage(); } });

$("#registerForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#registerNotice");
    notice.innerHTML = "";

    if ($("#rPassword").value !== $("#rPassword2").value) {
        notice.innerHTML = `<div class="notice err">Passwords do not match.</div>`;
        return;
    }

    const payload = {
        name: $("#rName").value,
        section: $("#rSection").value,
        department: $("#rDepartment").value,
        domain: $("#rDomain").value,
        languages,
        gender: $("#rGender").value,
        github: $("#rGithub").value,
        phone: $("#rPhone").value,
        techstack: ($("#rStack").value || "").split(",").map((s) => s.trim()).filter(Boolean),
        password: $("#rPassword").value,
        registered: new Date().toISOString(),
    };

    try {
        const res = await API.post("/api/auth/register", payload);
        sessionStorage.setItem(TOKEN_KEY, res.token);
        notice.innerHTML = `<div class="notice ok">Account created! Taking you to your dashboard...</div>`;
        setTimeout(() => { window.location.href = "dashboard.html"; }, 600);
    } catch (err) {
        notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`;
    }
});

/* ---------- Auth: login ---------- */
$("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#loginNotice");
    notice.innerHTML = "";
    try {
        const res = await API.post("/api/auth/login", {
            phone: $("#lPhone").value,
            password: $("#lPassword").value,
        });
        sessionStorage.setItem(TOKEN_KEY, res.token);
        notice.innerHTML = `<div class="notice ok">Welcome back! Taking you to your dashboard...</div>`;
        setTimeout(() => { window.location.href = "dashboard.html"; }, 500);
    } catch (err) {
        notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`;
    }
});

/* ---------- Reveal on scroll ---------- */
let revealObserver;
function observeReveals() {
    if (!revealObserver) {
        revealObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("in");
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.08 });
    }
    document.querySelectorAll(".reveal:not(.in)").forEach((el) => revealObserver.observe(el));
}

/* ---------- Init ---------- */
loadStats();
loadProblems();
loadTimeline();
loadTeams();
loadAnnouncements();
observeReveals();
