# College SIH 2026 — Selection & Team Formation Portal

A self-contained website for running your college's internal Smart India Hackathon (SIH) 2026 selection process. Built with plain HTML/CSS/JS frontend and a **zero-dependency Python backend** (Python standard library only — no Node.js, no npm, no pip installs).

## Features

- **Accounts & Login** — students register with Name, Section, Department, Domain, Language, Gender, GitHub link, and Phone number, then log in with phone + password.
- **Problem Statements** — browse, search, and filter SIH problem statements by theme/domain.
- **Team Formation Dashboard** — after login, create a team, browse all teams and members, request to join a team, or leave/disband your own.
- **Invite by Tech Stack** — search students by tech stack (frontend, ML, UI/UX, backend...), language, name, or department, then send them a team invitation. Invitations and join requests are accepted/rejected from the dashboard.
- **Enforced Team Rules** — every team must have **exactly 6 members**, **at least 2 female members**, and **members from at least 2 departments**. Rules are enforced by the API whenever a member is added.
- **Selection Management** — admin dashboard to shortlist / select / reject candidates.
- **Timeline & Announcements** — key dates and admin-posted notices shown on the main site.
- **Admin Dashboard** — password-protected management for students, problems, teams, announcements, and timeline.

## Quick Start

Requires Python 3 (no third-party packages).

```
python server.py
```

Then open:

- Main site:  http://localhost:8000/
- Dashboard:  http://localhost:8000/dashboard.html
- Admin:      http://localhost:8000/admin.html

Default admin password: **sih2026admin**

Sample student accounts (all seeded with password **sih2026**):
- Aarav Sharma — `9876500001` (leader of Team CodeSprint)
- Priya Patel — `9876500002`
- Rohan Verma — `9876500003`
- ... any of the 10 seeded users `9876500001`–`9876500010`

> Change the password by setting an environment variable:
> `set ADMIN_PASSWORD=your-strong-password` (Windows) before running `python server.py`.

## Team Formation Rules (enforced)

The portal enforces the college's SIH 2026 team rules on the backend whenever a
member joins a team (via invites or join requests):

1. A team must have **exactly 6 members**.
2. At least **2 members must be Female**.
3. Members must come from **at least 2 departments** (from the 10 listed below).

Teams below 6 members are allowed while they're being filled, but the 6th member
can only be added if all rules are satisfied. Departments:
- Electrical and Electronics Engineering
- Electronics and Communication Engineering
- Computer Science Engineering
- Information Technology
- Instrumentation and Control Engineering
- Mechanical Engineering
- Civil Engineering
- Biomedical Engineering
- Mechatronics
- Artificial Intelligence and Data Science

Student registration also collects **gender** and **department** so teams can be validated.

## Project Structure

```
server.py            Python backend (REST API + static file server)
public/
  index.html         Main student-facing site
  admin.html         Admin dashboard
  style.css          Shared styles
  admin.css          Admin-specific styles
  app.js             Main site logic
  admin.js           Admin dashboard logic
data/                JSON data files (auto-created on first run)
  problems.json      Problem statements
  students.json      Registered students + selection status
  teams.json         Team listings
  announcements.json Notices
  timeline.json      Key dates
```

## API Overview

| Method | Endpoint                          | Description                        | Auth |
|--------|-----------------------------------|------------------------------------|------|
| POST   | `/api/auth/register`              | Create account, returns session    | —    |
| POST   | `/api/auth/login`                 | Phone + password login             | —    |
| GET    | `/api/me`                         | My profile + team                  | user |
| PATCH  | `/api/me`                         | Update profile                     | user |
| GET    | `/api/users?q=frontend ml`        | Search students by tech stack etc. | user |
| GET    | `/api/teams`                      | List teams (+ stats)               | —    |
| POST   | `/api/teams`                      | Create team (you become leader)    | user |
| POST   | `/api/teams/{id}/join`            | Request to join a team             | user |
| POST   | `/api/teams/{id}/leave`           | Leave team (leader disbands)       | user |
| PATCH  | `/api/teams/{id}/remove`          | Leader removes a member            | user |
| DELETE | `/api/teams/{id}`                 | Delete/disband team                | user* |
| POST   | `/api/invites`                    | Team member invites a user         | user |
| GET    | `/api/invites/mine`               | My incoming/sent invites           | user |
| POST   | `/api/invites/{id}/accept`        | Accept invite / join request       | user |
| POST   | `/api/invites/{id}/reject`        | Reject invite / join request       | user |
| POST   | `/api/login`                      | Admin password → admin token       | —    |
| GET    | `/api/students`                   | List registrations (no hashes)     | admin|
| PATCH  | `/api/students/{id}/status`       | Update selection status            | admin|
| DELETE | `/api/students/{id}`              | Delete a registration              | admin|
| GET    | `/api/problems`                   | List problem statements            | —    |
| POST   | `/api/problems`                   | Add a problem statement            | admin|
| DELETE | `/api/problems/{id}`              | Delete a problem statement         | admin|
| GET    | `/api/announcements`              | List announcements                 | —    |
| POST   | `/api/announcements`              | Post an announcement               | admin|
| DELETE | `/api/announcements/{id}`         | Delete an announcement             | admin|
| GET    | `/api/timeline`                   | List timeline events               | —    |
| POST   | `/api/timeline`                   | Add a timeline event               | admin|
| DELETE | `/api/timeline/{id}`              | Delete a timeline event            | admin|
| GET    | `/api/stats`                      | Public counters                    | —    |

User endpoints require `Authorization: Bearer <token>` from login/register.
Admin endpoints require the token from `/api/login`.
\* team DELETE also allowed for the team leader.

## Data

All data lives in the `data/` folder as human-readable JSON. On first run, sample
placeholder data (problems, students, teams, announcements, timeline) is seeded
automatically. Edit the JSON files directly or use the admin dashboard to replace
the placeholders with your real content. Data is persisted across server restarts.

## Notes

- Storage is JSON files — perfect for a single-machine college portal. For a multi-admin
  deployment, swap the data layer for a database.
- Sample data is for demonstration; replace it with your actual problem statements and students.
