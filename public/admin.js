/* ==========================================================================
   College SIH 2026 - Admin Dashboard (admin.js)
   ========================================================================== */

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

const TOKEN_KEY = "sih2026_admin_token";

function getToken() { return sessionStorage.getItem(TOKEN_KEY) || ""; }

async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (getToken()) headers["Authorization"] = "Bearer " + getToken();
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
        logout("Session expired. Please sign in again.");
        throw new Error(data.error || "Unauthorized");
    }
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
}

/* ---------- Auth ---------- */
$("#loginForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#loginNotice");
    notice.innerHTML = "";
    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: $("#loginPassword").value }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || "Invalid password");
        sessionStorage.setItem(TOKEN_KEY, data.token);
        enterDashboard();
    } catch (err) {
        notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`;
    }
});

function enterDashboard() {
    $("#loginGate").classList.add("hidden");
    $("#dashboard").classList.remove("hidden");
    loadAll();
}

function logout(msg) {
    sessionStorage.removeItem(TOKEN_KEY);
    $("#dashboard").classList.add("hidden");
    $("#loginGate").classList.remove("hidden");
    $("#loginPassword").value = "";
    $("#loginNotice").innerHTML = msg ? `<div class="notice err">${esc(msg)}</div>` : "";
}

$("#logoutBtn").addEventListener("click", () => logout());

/* ---------- Tabs ---------- */
function switchTab(name) {
    document.querySelectorAll(".admin-section").forEach((s) => s.classList.add("hidden"));
    $("#tab-" + name).classList.remove("hidden");
    document.querySelectorAll(".tab-link").forEach((a) => a.classList.remove("active"));
    const active = document.querySelector(`.tab-link[data-tab="${name}"]`);
    if (active) active.classList.add("active");
}
document.querySelectorAll(".tab-link").forEach((a) => {
    a.addEventListener("click", (e) => {
        e.preventDefault();
        switchTab(a.dataset.tab);
    });
});

/* ---------- Students ---------- */
let allStudents = [];

const STATUS_ORDER = { pending: 0, shortlisted: 1, selected: 2, rejected: 3 };

async function loadStudents() {
    allStudents = await api("/api/students");
    renderStudents();
}

function renderStudents() {
    const q = ($("#studentSearch").value || "").toLowerCase().trim();
    const filter = $("#studentStatusFilter").value;
    const filtered = allStudents
        .filter((s) => {
            const matchesQuery = (s.name + " " + s.phone + " " + s.section + " " + (s.department || "") + " " +
                (s.domain || "") + " " + (s.languages || []).join(" ") + " " + (s.techstack || []).join(" "))
                .toLowerCase().includes(q);
            const matchesStatus = !filter || s.status === filter;
            return matchesQuery && matchesStatus;
        })
        .sort((a, b) => (STATUS_ORDER[a.status] || 0) - (STATUS_ORDER[b.status] || 0));

    const body = $("#studentsBody");
    if (!filtered.length) {
        body.innerHTML = `<tr><td colspan="5" class="empty-state">No students found.</td></tr>`;
        return;
    }
    body.innerHTML = filtered.map((s) => `
        <tr>
            <td>
                <div class="student-main">${esc(s.name)} <span class="badge theme">${esc(s.gender || "")}</span></div>
                <div class="student-sub">${esc(s.phone || "")}${s.github ? " · " + esc(s.github) : ""}</div>
            </td>
            <td>
                <div class="student-main">${esc(s.department || "—")}</div>
                <div class="student-sub">Section ${esc(s.section || "—")} · ${esc(s.domain || "—")}</div>
            </td>
            <td>
                <div class="skill-list">
                    ${(s.languages || []).map((k) => `<span class="skill-pill">${esc(k)}</span>`).join("")}
                    ${(s.techstack || []).map((k) => `<span class="skill-pill" style="background:#fff1e3; color:#b85e00;">${esc(k)}</span>`).join("")}
                </div>
                ${(s.techstack || []).length === 0 && (s.languages || []).length === 0 ? "<span class='student-sub'>No tech stack listed</span>" : ""}
            </td>
            <td>
                <select class="status-select" data-status="${esc(s.status)}" data-id="${s.id}">
                    <option value="pending" ${s.status === "pending" ? "selected" : ""}>Pending</option>
                    <option value="shortlisted" ${s.status === "shortlisted" ? "selected" : ""}>Shortlisted</option>
                    <option value="selected" ${s.status === "selected" ? "selected" : ""}>Selected</option>
                    <option value="rejected" ${s.status === "rejected" ? "selected" : ""}>Rejected</option>
                </select>
            </td>
            <td>
                <div class="row-actions">
                    <button class="icon-btn danger" data-delete="student" data-id="${s.id}">Delete</button>
                </div>
            </td>
        </tr>`).join("");

    body.querySelectorAll(".status-select").forEach((sel) => {
        sel.addEventListener("change", async () => {
            const id = sel.dataset.id;
            sel.dataset.status = sel.value;
            try {
                await api(`/api/students/${id}/status`, {
                    method: "PATCH",
                    body: JSON.stringify({ status: sel.value }),
                });
            } catch (err) { alert(err.message); }
        });
    });
    body.querySelectorAll("[data-delete=student]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this student registration?")) return;
            try {
                await api(`/api/students/${btn.dataset.id}`, { method: "DELETE" });
                loadStudents();
            } catch (err) { alert(err.message); }
        });
    });
}

$("#studentSearch").addEventListener("input", renderStudents);
$("#studentStatusFilter").addEventListener("change", renderStudents);

/* ---------- Problems ---------- */
async function loadProblems() {
    const problems = await api("/api/problems");
    const list = $("#problemsList");
    if (!problems.length) {
        list.innerHTML = `<div class="admin-item"><div><div class="meta">No problem statements yet.</div></div></div>`;
        return;
    }
    list.innerHTML = problems.map((p) => `
        <div class="admin-item">
            <div>
                <div class="main">${esc(p.title)}</div>
                <div class="meta">${esc(p.theme)} · ${esc(p.org)} · ${esc(p.difficulty)}</div>
                <div class="desc">${esc(p.description)}</div>
            </div>
            <div class="actions">
                <button class="icon-btn danger" data-delete="problem" data-id="${p.id}">Delete</button>
            </div>
        </div>`).join("");
    list.querySelectorAll("[data-delete=problem]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this problem statement?")) return;
            try {
                await api(`/api/problems/${btn.dataset.id}`, { method: "DELETE" });
                loadProblems();
            } catch (err) { alert(err.message); }
        });
    });
}

$("#problemForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#problemFormNotice");
    notice.innerHTML = "";
    try {
        await api("/api/problems", {
            method: "POST",
            body: JSON.stringify({
                title: $("#pTitle").value,
                theme: $("#pTheme").value || "General",
                org: $("#pOrg").value || "Internal",
                difficulty: $("#pDifficulty").value,
                description: $("#pDescription").value,
            }),
        });
        notice.innerHTML = `<div class="notice ok">Problem statement added.</div>`;
        e.target.reset();
        loadProblems();
    } catch (err) { notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; }
});

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

/* ---------- Teams ---------- */
async function loadTeams() {
    const teams = await api("/api/teams");
    const list = $("#teamsList");
    if (!teams.length) {
        list.innerHTML = `<div class="admin-item"><div><div class="meta">No teams yet.</div></div></div>`;
        return;
    }
    list.innerHTML = teams.map((t) => {
        const stats = teamStats(t.members || []);
        const validBadge = stats.valid
            ? `<span class="badge status-selected">Valid team</span>`
            : `<span class="badge status-rejected">Does not meet rules</span>`;
        return `
        <div class="admin-item">
            <div>
                <div class="main">${esc(t.name)} ${validBadge}</div>
                <div class="meta">${t.problemId ? "Problem: " + esc(t.problemTitle || t.problemId) : "No problem assigned"} · ${stats.count}/6 members · ${stats.girls} girls · ${stats.departments} departments</div>
                <div class="badges">
                    ${(t.members || []).map((m) => `<span class="skill-pill">${esc(m.name)} · ${esc(m.gender || "—")} · ${esc(m.department || "—")} · ${esc(m.role || "")}</span>`).join("")}
                    ${(t.lookingFor || []).map((l) => `<span class="skill-pill" style="background:#fff1e3; color:#b85e00;">Need: ${esc(l)}</span>`).join("")}
                </div>
            </div>
            <div class="actions">
                <button class="icon-btn danger" data-delete="team" data-id="${t.id}">Delete</button>
            </div>
        </div>`;
    }).join("");
    list.querySelectorAll("[data-delete=team]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this team listing?")) return;
            try {
                await api(`/api/teams/${btn.dataset.id}`, { method: "DELETE" });
                loadTeams();
            } catch (err) { alert(err.message); }
        });
    });
}

/* ---------- Announcements ---------- */
async function loadAnnouncements() {
    const items = await api("/api/announcements");
    const list = $("#announcementsList");
    if (!items.length) {
        list.innerHTML = `<div class="admin-item"><div><div class="meta">No announcements yet.</div></div></div>`;
        return;
    }
    list.innerHTML = items.map((a) => `
        <div class="admin-item">
            <div>
                <div class="main">${esc(a.title)}</div>
                <div class="meta">${esc(a.date || "")}</div>
                <div class="desc">${esc(a.body)}</div>
            </div>
            <div class="actions">
                <button class="icon-btn danger" data-delete="announcement" data-id="${a.id}">Delete</button>
            </div>
        </div>`).join("");
    list.querySelectorAll("[data-delete=announcement]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this announcement?")) return;
            try {
                await api(`/api/announcements/${btn.dataset.id}`, { method: "DELETE" });
                loadAnnouncements();
            } catch (err) { alert(err.message); }
        });
    });
}

$("#announceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#announceFormNotice");
    notice.innerHTML = "";
    try {
        await api("/api/announcements", {
            method: "POST",
            body: JSON.stringify({
                title: $("#aTitle").value,
                body: $("#aBody").value,
                date: $("#aDate").value || new Date().toISOString().slice(0, 10),
            }),
        });
        notice.innerHTML = `<div class="notice ok">Announcement posted.</div>`;
        e.target.reset();
        loadAnnouncements();
    } catch (err) { notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; }
});

/* ---------- Timeline ---------- */
async function loadTimeline() {
    const items = await api("/api/timeline");
    const list = $("#timelineList");
    if (!items.length) {
        list.innerHTML = `<div class="admin-item"><div><div class="meta">No timeline events yet.</div></div></div>`;
        return;
    }
    list.innerHTML = items.map((t) => `
        <div class="admin-item">
            <div>
                <div class="main">${esc(t.date)} — ${esc(t.title)}</div>
                <div class="desc">${esc(t.detail)}</div>
            </div>
            <div class="actions">
                <button class="icon-btn danger" data-delete="timeline" data-id="${t.id}">Delete</button>
            </div>
        </div>`).join("");
    list.querySelectorAll("[data-delete=timeline]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            if (!confirm("Delete this timeline event?")) return;
            try {
                await api(`/api/timeline/${btn.dataset.id}`, { method: "DELETE" });
                loadTimeline();
            } catch (err) { alert(err.message); }
        });
    });
}

$("#timelineForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#timelineFormNotice");
    notice.innerHTML = "";
    try {
        await api("/api/timeline", {
            method: "POST",
            body: JSON.stringify({
                date: $("#tDate").value,
                title: $("#tTitle").value,
                detail: $("#tDetail").value,
            }),
        });
        notice.innerHTML = `<div class="notice ok">Timeline event added.</div>`;
        e.target.reset();
        loadTimeline();
    } catch (err) { notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`; }
});

/* ---------- Init ---------- */
async function loadAll() {
    try {
        await Promise.all([loadStudents(), loadProblems(), loadTeams(), loadAnnouncements(), loadTimeline()]);
    } catch (e) { /* auth errors already handled */ }
}

if (getToken()) {
    // verify token still valid
    api("/api/students").then(enterDashboard).catch(() => {});
}
