/* ==========================================================================
   College SIH 2026 - Dashboard (dashboard.js)
   ========================================================================== */

const TOKEN_KEY = "sih2026_token";
const token = sessionStorage.getItem(TOKEN_KEY);
if (!token) window.location.href = "index.html#auth";

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    headers["Authorization"] = "Bearer " + token;
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
        sessionStorage.removeItem(TOKEN_KEY);
        window.location.href = "index.html#auth";
        throw new Error(data.error || "Session expired");
    }
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
}

const TEAM_SIZE = 6;
const MIN_GIRLS = 2;
const MIN_DEPARTMENTS = 2;

let me = null;          // my profile + team
let teams = [];
let invites = { incoming: [], sent: [] };
let users = [];

/* ---------- Tabs ---------- */
document.addEventListener("click", (e) => {
    const link = e.target.closest(".tab-link");
    if (link) {
        e.preventDefault();
        switchTab(link.dataset.tab);
    }
});
function switchTab(name) {
    document.querySelectorAll(".dash-section").forEach((s) => s.classList.remove("active"));
    $("#t-" + name).classList.add("active");
    document.querySelectorAll(".tab-link").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
}

/* ---------- Team helpers ---------- */
function teamStats(members) {
    const count = (members || []).filter((m) => m && m.name).length;
    const girls = (members || []).filter((m) => m && m.gender === "Female").length;
    const departments = new Set((members || []).filter((m) => m && m.department).map((m) => m.department)).size;
    return {
        count, girls, departments,
        valid: count === TEAM_SIZE && girls >= MIN_GIRLS && departments >= MIN_DEPARTMENTS,
    };
}

function renderMemberPills(members) {
    return (members || [])
        .map((m) => `<span class="team-member">${esc(m.name)}<span class="role">· ${esc(m.gender || "")} · ${esc(m.department || "")}</span></span>`)
        .join("");
}

function statsBadges(stats) {
    const valid = stats.valid
        ? `<span class="badge status-selected">Valid team</span>`
        : (stats.count === TEAM_SIZE
            ? `<span class="badge status-rejected">Does not meet rules</span>`
            : `<span class="badge status-pending">${stats.count}/${TEAM_SIZE} members</span>`);
    return `
        <div class="team-stats">
            <span class="badge theme">${stats.count}/${TEAM_SIZE} members</span>
            <span class="badge ${stats.girls >= MIN_GIRLS ? "status-selected" : "status-rejected"}">${stats.girls} girls</span>
            <span class="badge ${stats.departments >= MIN_DEPARTMENTS ? "status-selected" : "status-rejected"}">${stats.departments} departments</span>
            ${valid}
        </div>`;
}

/* ---------- My team ---------- */
function myTeam() {
    return me && me.team ? teams.find((t) => t.id === me.team.id) || me.team : null;
}

async function renderMyTeam() {
    const team = myTeam();
    $("#noTeamBlock").classList.toggle("hidden", !!team);
    $("#myTeamBlock").classList.toggle("hidden", !team);

    if (team) {
        const stats = teamStats(team.members || []);
        const isLeader = team.leaderId === me.id;
        const members = (team.members || []).map((m) => {
            const isMe = m.userId === me.id;
            const removeBtn = isLeader && !isMe
                ? `<button class="icon-btn danger" data-remove="${m.userId}">Remove</button>`
                : "";
            return `
                <div class="team-member">
                    ${esc(m.name)}${isMe ? " (you)" : ""}
                    <span class="role">· ${esc(m.gender || "")} · ${esc(m.department || "")} · ${esc(m.role || "")}</span>
                    ${removeBtn}
                </div>`;
        }).join("");

        const looking = (team.lookingFor || []).join(", ");
        const leaderBtn = isLeader
            ? `<button class="btn btn-ghost" id="disbandBtn">Disband Team</button>`
            : `<button class="btn btn-ghost" id="leaveBtn">Leave Team</button>`;

        $("#myTeamCard").innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap;">
                <div>
                    <h3>${esc(team.name)} ${isLeader ? '<span class="badge status-shortlisted">Leader</span>' : ""}</h3>
                    <span class="problem-link">${team.problemId ? "Problem: " + esc(team.problemTitle || team.problemId) : "No problem statement assigned yet"}</span>
                </div>
                <div style="display:flex; gap:8px;">${leaderBtn}</div>
            </div>
            <div class="team-members">${members}</div>
            ${statsBadges(stats)}
            <p class="looking-for">${looking ? "<strong>Looking for:</strong> " + esc(looking) : ""}</p>
            <p style="font-size:0.82rem; color:var(--muted); margin-top:10px;">
                Use the <a href="#t-find" class="tab-link" data-tab="find" style="color:var(--saffron); font-weight:600;">Find Members</a> tab to search
                tech stacks and invite teammates. Fill the team to ${TEAM_SIZE} members to become valid.
            </p>`;

        const leaveBtn = $("#leaveBtn");
        if (leaveBtn) leaveBtn.addEventListener("click", async () => {
            if (!confirm("Leave this team?")) return;
            try {
                await api(`/api/teams/${team.id}/leave`, { method: "POST" });
                loadAll();
            } catch (err) { alert(err.message); }
        });
        const disbandBtn = $("#disbandBtn");
        if (disbandBtn) disbandBtn.addEventListener("click", async () => {
            if (!confirm("Disband this team? This cannot be undone.")) return;
            try {
                await api(`/api/teams/${team.id}`, { method: "DELETE" });
                loadAll();
            } catch (err) { alert(err.message); }
        });
        document.querySelectorAll("#myTeamCard [data-remove]").forEach((btn) => {
            btn.addEventListener("click", async () => {
                if (!confirm("Remove this member from the team?")) return;
                try {
                    await api(`/api/teams/${team.id}/remove`, { method: "PATCH", body: JSON.stringify({ userId: btn.dataset.remove }) });
                    loadAll();
                } catch (err) { alert(err.message); }
            });
        });

        renderInvites(team);
    }
}

/* ---------- Invites ---------- */
function renderInvites(team) {
    const box = $("#invitesBox");
    const incoming = invites.incoming;
    const sent = invites.sent;

    let html = "";

    const incomingItems = incoming.map((inv) => {
        const isMyTeam = inv.teamId === team.id;
        const fromLeaderInvite = inv.fromUserId === team.leaderId;
        const who = isMyTeam && !fromLeaderInvite
            ? `${esc(inv.fromName)} requested to join <strong>${esc(inv.teamName)}</strong>`
            : `<strong>${esc(inv.teamName)}</strong> invited you to join`;
        const actions = inv.status === "pending"
            ? `<div class="invite-actions">
                    <button class="btn btn-navy" data-accept="${inv.id}" style="padding:8px 14px; font-size:0.82rem;">Accept</button>
                    <button class="btn btn-ghost" data-reject="${inv.id}" style="padding:8px 14px; font-size:0.82rem;">Reject</button>
                </div>`
            : `<span class="status-pill ${inv.status === "accepted" ? "done" : "no"}">${esc(inv.status)}</span>`;
        return `<div class="invite-item"><div><div class="main">${who}</div></div>${actions}</div>`;
    }).join("");

    const sentItems = sent.map((inv) => {
        let desc;
        const isLeaderOfTeam = inv.teamId === team.id && team.leaderId === me.id;
        if (isLeaderOfTeam) desc = `You invited <strong>${esc(inv.toName)}</strong> to <strong>${esc(inv.teamName)}</strong>`;
        else desc = `You requested to join <strong>${esc(inv.teamName)}</strong>`;
        return `<div class="invite-item"><div><div class="main">${desc}</div></div>
                <span class="status-pill ${inv.status === "accepted" ? "done" : inv.status === "rejected" ? "no" : ""}">${esc(inv.status)}</span></div>`;
    }).join("");

    if (incoming.length) {
        html += `<div class="invite-block"><h4>Invitations &amp; Join Requests</h4>${incomingItems}</div>`;
    }
    if (sent.length) {
        html += `<div class="invite-block"><h4>Sent Invites &amp; Requests</h4>${sentItems}</div>`;
    }
    if (!incoming.length && !sent.length) {
        html = `<div class="empty-state">No pending invites or join requests.</div>`;
    }

    box.innerHTML = html;

    box.querySelectorAll("[data-accept]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            try {
                await api(`/api/invites/${btn.dataset.accept}/accept`, { method: "POST" });
                loadAll();
            } catch (err) { alert(err.message); }
        });
    });
    box.querySelectorAll("[data-reject]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            try {
                await api(`/api/invites/${btn.dataset.reject}/reject`, { method: "POST" });
                loadAll();
            } catch (err) { alert(err.message); }
        });
    });
}

/* ---------- Browse teams ---------- */
async function renderTeams() {
    const grid = $("#teamsGrid");
    if (!teams.length) {
        grid.innerHTML = `<div class="empty-state">No teams yet. Create the first one from the My Team tab.</div>`;
        return;
    }
    grid.innerHTML = teams.map((t) => {
        const stats = teamStats(t.members || []);
        const inTeam = me && me.team && me.team.id === t.id;
        const isMember = (t.members || []).some((m) => m.userId === me.id);
        let action = "";
        if (inTeam || isMember) {
            action = `<button class="btn btn-ghost" disabled>You're in this team</button>`;
        } else if (me && me.team) {
            action = `<button class="btn btn-ghost" disabled>Join another team? Leave yours first</button>`;
        } else if (stats.count >= TEAM_SIZE) {
            action = `<button class="btn btn-ghost" disabled>Team full</button>`;
        } else {
            action = `<button class="btn btn-navy" data-join="${t.id}">Request to Join</button>`;
        }
        const looking = (t.lookingFor || []).join(", ");
        return `
            <div class="team-card">
                <h3>${esc(t.name)} <span class="badge status-shortlisted">${esc((t.members || []).find((m) => m.userId === t.leaderId)?.role || "Team Leader")}</span></h3>
                <span class="problem-link">${t.problemId ? "Problem: " + esc(t.problemTitle || t.problemId) : "No problem statement assigned yet"}</span>
                <div class="team-members">${renderMemberPills(t.members)}</div>
                ${statsBadges(stats)}
                <p class="looking-for">${looking ? "<strong>Looking for:</strong> " + esc(looking) : ""}</p>
                ${action}
            </div>`;
    }).join("");

    grid.querySelectorAll("[data-join]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            try {
                await api(`/api/teams/${btn.dataset.join}/join`, { method: "POST" });
                alert("Join request sent to the team leader!");
                loadAll();
            } catch (err) { alert(err.message); }
        });
    });
}

/* ---------- Find members ---------- */
async function searchUsers(q) {
    const grid = $("#usersGrid");
    grid.innerHTML = `<div class="empty-state">Searching...</div>`;
    try {
        users = await api("/api/users?q=" + encodeURIComponent(q));
        renderUsers();
    } catch (e) {
        grid.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`;
    }
}

function renderUsers() {
    const grid = $("#usersGrid");
    if (!users.length) {
        grid.innerHTML = `<div class="empty-state">No students match that search. Try another tech stack.</div>`;
        return;
    }

    const myTeamObj = myTeam();
    grid.innerHTML = users.map((u) => {
        let action;
        if (!myTeamObj) {
            action = `<button class="btn btn-ghost" disabled>Create a team first</button>`;
        } else if (u.team) {
            action = `<button class="btn btn-ghost" disabled>Already in "${esc(u.team.name)}"</button>`;
        } else if ((myTeamObj.members || []).length >= TEAM_SIZE) {
            action = `<button class="btn btn-ghost" disabled>Your team is full</button>`;
        } else if ((myTeamObj.members || []).some((m) => m.userId === u.id)) {
            action = `<button class="btn btn-ghost" disabled>In your team</button>`;
        } else {
            action = `<button class="btn btn-navy" data-invite="${u.id}">Invite to ${esc(myTeamObj.name)}</button>`;
        }
        return `
            <div class="user-card">
                <div class="top">
                    <div>
                        <h3>${esc(u.name)} <span class="badge theme">${esc(u.gender)}</span></h3>
                        <div class="meta">${esc(u.department)} · Section ${esc(u.section)}</div>
                        <div class="meta">Domain: ${esc(u.domain || "—")}</div>
                    </div>
                    <div style="text-align:right;">
                        ${u.team ? `<span class="badge status-shortlisted">In a team</span>` : `<span class="badge status-pending">Available</span>`}
                    </div>
                </div>
                <div class="pills">
                    ${(u.languages || []).map((l) => `<span class="skill-pill">${esc(l)}</span>`).join("")}
                    ${(u.techstack || []).map((s) => `<span class="skill-pill" style="background:#fff1e3; color:#b85e00;">${esc(s)}</span>`).join("")}
                </div>
                ${u.github ? `<a class="github" href="https://${esc(u.github)}" target="_blank" rel="noopener">${esc(u.github)}</a>` : ""}
                ${action}
            </div>`;
    }).join("");

    grid.querySelectorAll("[data-invite]").forEach((btn) => {
        btn.addEventListener("click", async () => {
            try {
                await api("/api/invites", {
                    method: "POST",
                    body: JSON.stringify({ teamId: myTeam().id, userId: btn.dataset.invite }),
                });
                alert("Invite sent! They'll see it on their dashboard.");
            } catch (err) { alert(err.message); }
        });
    });
}

$("#searchBtn").addEventListener("click", () => searchUsers($("#userSearch").value));
$("#userSearch").addEventListener("keydown", (e) => { if (e.key === "Enter") searchUsers($("#userSearch").value); });
document.querySelectorAll(".search-hint .chip").forEach((chip) => {
    chip.addEventListener("click", () => {
        $("#userSearch").value = chip.dataset.q;
        searchUsers(chip.dataset.q);
    });
});

/* ---------- Create team ---------- */
async function populateProblemSelect() {
    try {
        const problems = await api("/api/problems");
        $("#ctProblem").innerHTML =
            `<option value="">— No problem statement yet —</option>` +
            problems.map((p) => `<option value="${p.id}">${esc(p.theme)} — ${esc(p.title)}</option>`).join("");
    } catch (e) { /* ignore */ }
}

$("#createTeamForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const notice = $("#createTeamNotice");
    notice.innerHTML = "";
    try {
        await api("/api/teams", {
            method: "POST",
            body: JSON.stringify({
                name: $("#ctName").value,
                problemId: $("#ctProblem").value,
                problemTitle: $("#ctProblem").selectedOptions[0]?.text || "",
                lookingFor: ($("#ctLooking").value || "").split(",").map((s) => s.trim()).filter(Boolean),
                created: new Date().toISOString(),
            }),
        });
        notice.innerHTML = `<div class="notice ok">Team created! Now use Find Members to invite your squad.</div>`;
        e.target.reset();
        loadAll();
    } catch (err) {
        notice.innerHTML = `<div class="notice err">${esc(err.message)}</div>`;
    }
});

/* ---------- Header ---------- */
$("#logoutBtn").addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    window.location.href = "index.html";
});

/* ---------- Load ---------- */
async function loadAll() {
    const [profile, allTeams, myInvites] = await Promise.all([
        api("/api/me"),
        api("/api/teams"),
        api("/api/invites/mine"),
    ]);
    me = profile;
    teams = allTeams;
    invites = myInvites;

    $("#userName").textContent = me.name;
    $("#userDept").textContent = me.department + (me.team ? " · " + me.team.name : "");

    renderMyTeam();
    renderTeams();
    renderUsers();
}

populateProblemSelect();
loadAll().catch((e) => console.error(e));
