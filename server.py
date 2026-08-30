"""
College SIH 2026 - Selection & Team Formation Portal
Backend server built entirely on the Python standard library.
No external dependencies required.

Run:
    python server.py

Then open http://localhost:8000  (admin: http://localhost:8000/admin.html)
Default admin password: sih2026admin  (change ADMIN_PASSWORD below)
Seed user accounts all use password: sih2026
"""

import json
import os
import re
import uuid
import hashlib
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DATA_DIR = os.path.join(BASE_DIR, "data")

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8000"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "sih2026admin")
PASSWORD_SALT = os.environ.get("PASSWORD_SALT", "sih2026-salt")

# ---------------------------------------------------------------------------
# Constants & team formation rules
# ---------------------------------------------------------------------------

DEPARTMENTS = [
    "Electrical and Electronics Engineering",
    "Electronics and Communication Engineering",
    "Computer Science Engineering",
    "Information Technology",
    "Instrumentation and Control Engineering",
    "Mechanical Engineering",
    "Civil Engineering",
    "Biomedical Engineering",
    "Mechatronics",
    "Artificial Intelligence and Data Science",
]

TEAM_SIZE = 6            # exactly 6 members per SIH rules
MIN_GIRLS = 2            # at least 2 female members
MIN_DEPARTMENTS = 2      # members from at least 2 departments

GENDERS = ["Male", "Female", "Other"]

STATUSES = ["pending", "shortlisted", "selected", "rejected"]


def hash_password(password):
    return hashlib.sha256((PASSWORD_SALT + password).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def _u(pid, name, section, dept, domain, langs, stack, gender, github, phone, status, in_team=True):
    return {
        "id": pid,
        "name": name,
        "section": section,
        "department": dept,
        "domain": domain,
        "languages": langs,
        "techstack": stack,
        "gender": gender,
        "github": github,
        "phone": phone,
        "password_hash": hash_password("sih2026"),
        "status": status,
        "teamId": "",
        "registered": "2026-07-28T10:30:00Z",
    }


SEEDS = {
    "problems": [
        {
            "id": "ps-001",
            "title": "AI-based Crop Disease Detection",
            "theme": "Agriculture & FoodTech",
            "org": "Ministry of Agriculture",
            "difficulty": "Hard",
            "description": "Build a solution that detects crop diseases from field images and provides treatment recommendations in regional languages.",
        },
        {
            "id": "ps-002",
            "title": "Smart Traffic Management System",
            "theme": "Smart Automation",
            "org": "Ministry of Road Transport",
            "difficulty": "Medium",
            "description": "Develop an intelligent traffic signal control system using live traffic density data to reduce congestion in metro cities.",
        },
        {
            "id": "ps-003",
            "title": "Rural Healthcare Telemedicine Platform",
            "theme": "Healthcare",
            "org": "Ministry of Health & Family Welfare",
            "difficulty": "Hard",
            "description": "Create a low-bandwidth telemedicine platform connecting rural patients with doctors, including e-prescription and record keeping.",
        },
        {
            "id": "ps-004",
            "title": "Waste Segregation & Recycling Assistant",
            "theme": "Sustainability",
            "org": "Swachh Bharat Mission",
            "difficulty": "Medium",
            "description": "Design a computer-vision based app that identifies waste type and guides users on correct segregation and recycling.",
        },
        {
            "id": "ps-005",
            "title": "Personalised Learning Companion for Students",
            "theme": "Education & Skill Development",
            "org": "Ministry of Education",
            "difficulty": "Medium",
            "description": "Develop an AI tutor that adapts content difficulty to each student and generates practice questions from NCERT syllabus.",
        },
        {
            "id": "ps-006",
            "title": "FinTech Literacy & Micro-Lending App",
            "theme": "FinTech",
            "org": "Ministry of Finance",
            "difficulty": "Easy",
            "description": "Build a mobile-first financial literacy app with micro-lending for small business owners in tier-2 and tier-3 cities.",
        },
        {
            "id": "ps-007",
            "title": "Disaster Alert & Relief Coordination",
            "theme": "Social Impact",
            "org": "NDMA",
            "difficulty": "Hard",
            "description": "Create a real-time disaster alerting and relief coordination dashboard that aggregates data from multiple government APIs.",
        },
    ],
    "students": [
        _u("st-001", "Aarav Sharma", "B", "Computer Science Engineering", "Artificial Intelligence",
           ["Python", "Java"], ["Machine Learning", "Deep Learning", "NLP"], "Male",
           "github.com/aaravs", "9876500001", "shortlisted"),
        _u("st-002", "Priya Patel", "A", "Computer Science Engineering", "FinTech",
           ["JavaScript", "TypeScript"], ["React", "Frontend", "UI/UX"], "Female",
           "github.com/priyap", "9876500002", "pending"),
        _u("st-003", "Rohan Verma", "C", "Electronics and Communication Engineering", "Smart Automation",
           ["C++", "C"], ["IoT", "Embedded", "Arduino"], "Male",
           "github.com/rohanv", "9876500003", "selected"),
        _u("st-004", "Sneha Iyer", "A", "Information Technology", "Healthcare",
           ["Dart", "SQL"], ["Flutter", "Mobile", "Firebase"], "Female",
           "github.com/snehai", "9876500004", "rejected"),
        _u("st-005", "Meera Nair", "B", "Instrumentation and Control Engineering", "Healthcare",
           ["Python", "C"], ["Sensors", "Hardware", "Signal Processing"], "Female",
           "github.com/meeran", "9876500005", "shortlisted"),
        _u("st-006", "Kabir Singh", "C", "Mechanical Engineering", "Sustainability",
           ["MATLAB", "SolidWorks"], ["CAD", "3D Design", "Simulation"], "Male",
           "github.com/kabirs", "9876500006", "shortlisted"),
        _u("st-007", "Ananya Gupta", "A", "Computer Science Engineering", "AI",
           ["Python", "JavaScript"], ["Machine Learning", "Frontend", "Backend"], "Female",
           "github.com/ananyag", "9876500007", "pending"),
        _u("st-008", "Vikram Rao", "B", "Information Technology", "Cyber Security",
           ["Python", "Go"], ["Backend", "Networking", "Security"], "Male",
           "github.com/vikramr", "9876500008", "pending"),
        _u("st-009", "Ishita Das", "A", "Electronics and Communication Engineering", "Smart Automation",
           ["Python", "C++"], ["Computer Vision", "AI", "Embedded"], "Female",
           "github.com/ishitad", "9876500009", "pending"),
        _u("st-010", "Dev Menon", "C", "Mechatronics", "Robotics",
           ["C++", "ROS"], ["Robotics", "Control Systems", "CAD"], "Male",
           "github.com/devm", "9876500010", "pending"),
    ],
    "teams": [
        {
            "id": "tm-001",
            "name": "Team CodeSprint",
            "leaderId": "st-001",
            "problemId": "ps-002",
            "problemTitle": "Smart Traffic Management System",
            "members": [
                {"userId": "st-001", "name": "Aarav Sharma", "gender": "Male", "department": "Computer Science Engineering", "role": "Team Leader"},
                {"userId": "st-002", "name": "Priya Patel", "gender": "Female", "department": "Computer Science Engineering", "role": "UI/UX Designer"},
                {"userId": "st-003", "name": "Rohan Verma", "gender": "Male", "department": "Electronics and Communication Engineering", "role": "IoT Developer"},
                {"userId": "st-004", "name": "Sneha Iyer", "gender": "Female", "department": "Information Technology", "role": "Frontend Developer"},
                {"userId": "st-005", "name": "Meera Nair", "gender": "Female", "department": "Instrumentation and Control Engineering", "role": "Hardware Engineer"},
                {"userId": "st-006", "name": "Kabir Singh", "gender": "Male", "department": "Mechanical Engineering", "role": "CAD Designer"},
            ],
            "lookingFor": [],
            "created": "2026-07-30T11:00:00Z",
        },
        {
            "id": "tm-002",
            "name": "Team Innovators",
            "leaderId": "st-007",
            "problemId": "ps-001",
            "problemTitle": "AI-based Crop Disease Detection",
            "members": [
                {"userId": "st-007", "name": "Ananya Gupta", "gender": "Female", "department": "Computer Science Engineering", "role": "Team Leader"},
                {"userId": "st-008", "name": "Vikram Rao", "gender": "Male", "department": "Information Technology", "role": "Backend Developer"},
            ],
            "lookingFor": ["Frontend Developer", "ML Engineer", "UI/UX Designer"],
            "created": "2026-08-01T09:00:00Z",
        },
    ],
    "invites": [],
    "announcements": [
        {
            "id": "an-001",
            "title": "Registrations for SIH 2026 Internal Round are Open",
            "body": "The internal selection round for Smart India Hackathon 2026 has started. Register before the deadline to participate.",
            "date": "2026-08-01",
        },
        {
            "id": "an-002",
            "title": "Team Formation Workshop on 10th August",
            "body": "Join our team-formation workshop to meet fellow hackers and build your dream team. Venue: Main Auditorium, 3 PM.",
            "date": "2026-08-03",
        },
    ],
    "timeline": [
        {"id": "tl-001", "date": "2026-08-01", "title": "Registration Opens", "detail": "Students can register with their skills and interests."},
        {"id": "tl-002", "date": "2026-08-15", "title": "Registration Deadline", "detail": "Last date to submit the registration form."},
        {"id": "tl-003", "date": "2026-08-20", "title": "Internal Screening", "detail": "Evaluation of registrations and shortlisting."},
        {"id": "tl-004", "date": "2026-08-25", "title": "Team Formation", "detail": "Shortlisted students form teams around problem statements."},
        {"id": "tl-005", "date": "2026-09-05", "title": "Internal Hackathon", "detail": "Internal hackathon to select teams for SIH 2026."},
        {"id": "tl-006", "date": "2026-09-20", "title": "Final Team Announcement", "detail": "Winning teams represent the college at SIH 2026."},
    ],
}


# ---------------------------------------------------------------------------
# Data layer (JSON file storage)
# ---------------------------------------------------------------------------

def _data_path(name):
    return os.path.join(DATA_DIR, name + ".json")


def load(name):
    path = _data_path(name)
    if not os.path.exists(path):
        data = SEEDS.get(name, [])
        save(name, data)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return SEEDS.get(name, [])


def save(name, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_data_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def public_user(u):
    if not u:
        return None
    out = {k: v for k, v in u.items() if k != "password_hash"}
    return out


# ---------------------------------------------------------------------------
# Auth / sessions
# ---------------------------------------------------------------------------

_sessions = {}          # token -> user id
_admin_tokens = set()


def _make_session(user_id):
    token = uuid.uuid4().hex
    _sessions[token] = user_id
    return token


def _current_user(auth_header):
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    uid = _sessions.get(auth_header[7:])
    if not uid:
        return None
    for u in load("students"):
        if u["id"] == uid:
            return u
    return None


def _is_admin(auth_header):
    if not auth_header:
        return False
    if auth_header.startswith("Bearer "):
        return auth_header[7:] in _admin_tokens
    return False


def _find_team_of_user(uid):
    for t in load("teams"):
        for m in t.get("members", []):
            if m.get("userId") == uid:
                return t
    return None


def _team_stats(members):
    count = len(members)
    girls = sum(1 for m in members if m.get("gender") == "Female")
    departments = len({m.get("department") for m in members if m.get("department")})
    return {
        "count": count,
        "girls": girls,
        "departments": departments,
        "valid": count == TEAM_SIZE and girls >= MIN_GIRLS and departments >= MIN_DEPARTMENTS,
    }


def _add_member_error(team, new_member):
    """Return an error string if adding new_member violates rules, else None."""
    for m in team.get("members", []):
        if m.get("userId") == new_member.get("userId"):
            return "This person is already in the team"
    members = team.get("members", []) + [new_member]
    if len(members) > TEAM_SIZE:
        return f"A team cannot have more than {TEAM_SIZE} members"
    if len(members) == TEAM_SIZE:
        stats = _team_stats(members)
        if stats["girls"] < MIN_GIRLS:
            return f"Team would have fewer than {MIN_GIRLS} female members"
        if stats["departments"] < MIN_DEPARTMENTS:
            return f"Team would need members from at least {MIN_DEPARTMENTS} departments"
    return None


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "SIHPortal/1.0"

    def log_message(self, fmt, *args):
        pass  # quiet logs

    # -- helpers -----------------------------------------------------------
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message, status=400):
        self._send_json({"error": message}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        rel = path.lstrip("/")
        full = os.path.realpath(os.path.join(PUBLIC_DIR, rel))
        if not full.startswith(os.path.realpath(PUBLIC_DIR)):
            self.send_error(403)
            return
        if not os.path.isfile(full):
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(full)
        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- routing -----------------------------------------------------------
    def _route(self, method, path, query, body):
        if path in ("/", ""):
            if method == "GET":
                self._serve_static("/index.html")
            else:
                self._send_error_json("Method not allowed", 405)
            return

        segments = [s for s in path.split("/") if s]

        if segments[0] == "api":
            return self._route_api(method, segments[1:], query, body)
        if method == "GET":
            self._serve_static(path)
        else:
            self._send_error_json("Method not allowed", 405)

    def _route_api(self, method, segments, query, body):
        if not segments:
            return self._send_error_json("Not found", 404)

        head = segments[0]

        if head == "health":
            return self._send_json({"status": "ok"})

        if head == "stats":
            return self._send_json({
                "problems": len(load("problems")),
                "students": len(load("students")),
                "teams": len(load("teams")),
                "themes": len({p["theme"] for p in load("problems")}),
            })

        if head == "login" and method == "POST":  # admin login
            if body.get("password") == ADMIN_PASSWORD:
                token = uuid.uuid4().hex
                _admin_tokens.add(token)
                return self._send_json({"token": token})
            return self._send_error_json("Invalid password", 401)

        if head == "auth":
            return self._handle_auth(method, segments[1:], body)

        if head == "me":
            return self._handle_me(method, segments[1:], body)

        if head == "users":
            return self._handle_users(method, segments[1:], body)

        if head == "invites":
            return self._handle_invites(method, segments[1:], body)

        if head in ("problems", "students", "teams", "announcements", "timeline"):
            return self._handle_collection(head, method, segments, body)

        return self._send_error_json("Not found", 404)

    # -- auth --------------------------------------------------------------
    def _handle_auth(self, method, segments, body):
        if not segments or method != "POST":
            return self._send_error_json("Not found", 404)
        action = segments[0]

        if action == "register":
            required = ["name", "section", "department", "gender", "phone", "password"]
            for field in required:
                if not body.get(field):
                    return self._send_error_json(f"{field} is required")
            if body["department"] not in DEPARTMENTS:
                return self._send_error_json("Invalid department")
            if body["gender"] not in GENDERS:
                return self._send_error_json("Invalid gender")
            if len(body.get("password", "")) < 4:
                return self._send_error_json("Password must be at least 4 characters")
            users = load("students")
            if any(u["phone"] == body["phone"] for u in users):
                return self._send_error_json("Phone number already registered", 409)

            user = {
                "id": new_id("st"),
                "name": body["name"].strip(),
                "section": body["section"].strip(),
                "department": body["department"],
                "domain": body.get("domain", "").strip(),
                "languages": [x.strip() for x in body.get("languages", []) if x.strip()],
                "techstack": [x.strip() for x in body.get("techstack", []) if x.strip()],
                "gender": body["gender"],
                "github": body.get("github", "").strip(),
                "phone": body["phone"].strip(),
                "password_hash": hash_password(body["password"]),
                "status": "pending",
                "teamId": "",
                "registered": body.get("registered", ""),
            }
            users.append(user)
            save("students", users)
            return self._send_json({"token": _make_session(user["id"]), "user": public_user(user)}, 201)

        if action == "login":
            phone = (body.get("phone") or "").strip()
            password = body.get("password") or ""
            for u in load("students"):
                if u["phone"] == phone:
                    if u["password_hash"] == hash_password(password):
                        return self._send_json({"token": _make_session(u["id"]), "user": public_user(u)})
                    return self._send_error_json("Invalid phone or password", 401)
            return self._send_error_json("Invalid phone or password", 401)

        return self._send_error_json("Not found", 404)

    # -- me ----------------------------------------------------------------
    def _handle_me(self, method, segments, body):
        user = _current_user(self.headers.get("Authorization"))
        if not user:
            return self._send_error_json("Authentication required", 401)

        if method == "GET":
            team = _find_team_of_user(user["id"])
            profile = public_user(user)
            profile["team"] = {
                "id": team["id"],
                "name": team["name"],
                "leaderId": team.get("leaderId"),
                "role": next((m.get("role") for m in team.get("members", []) if m.get("userId") == user["id"]), ""),
                "stats": _team_stats(team.get("members", [])),
            } if team else None
            return self._send_json(profile)

        if method == "PATCH":
            users = load("students")
            idx = next((i for i, u in enumerate(users) if u["id"] == user["id"]), None)
            if idx is None:
                return self._send_error_json("User not found", 404)
            for field in ("name", "section", "department", "domain", "gender", "github"):
                if field in body:
                    users[idx][field] = body[field]
            for field in ("languages", "techstack"):
                if field in body and isinstance(body[field], list):
                    users[idx][field] = [x.strip() for x in body[field] if x.strip()]
            save("students", users)
            return self._send_json(public_user(users[idx]))

        return self._send_error_json("Method not allowed", 405)

    # -- users search ------------------------------------------------------
    def _handle_users(self, method, segments, body):
        user = _current_user(self.headers.get("Authorization"))
        if not user:
            return self._send_error_json("Authentication required", 401)
        if method != "GET":
            return self._send_error_json("Method not allowed", 405)

        q = ((self.path.split("?", 1)[1]) if "?" in self.path else "")
        qs = parse_qs(q)
        raw = (qs.get("q", [""])[0] or "").lower().strip()
        terms = [t for t in raw.split() if t]
        result = []
        for u in load("students"):
            if u["id"] == user["id"]:
                continue  # don't show yourself
            haystack = " ".join([
                u.get("name", ""), u.get("section", ""), u.get("department", ""),
                u.get("domain", ""), u.get("github", ""),
                *u.get("languages", []), *u.get("techstack", []),
            ]).lower()
            if terms and not all(t in haystack for t in terms):
                continue
            team = _find_team_of_user(u["id"])
            prof = public_user(u)
            prof["team"] = {"id": team["id"], "name": team["name"]} if team else None
            result.append(prof)
        return self._send_json(result)

    # -- invites -----------------------------------------------------------
    def _handle_invites(self, method, segments, body):
        user = _current_user(self.headers.get("Authorization"))
        if not user:
            return self._send_error_json("Authentication required", 401)
        invites = load("invites")
        teams = load("teams")
        users = load("students")

        def user_by_id(uid):
            return next((u for u in users if u["id"] == uid), None)

        if method == "GET" and len(segments) == 1 and segments[0] == "mine":
            incoming = []
            sent = []
            for inv in invites:
                if inv["toUserId"] == user["id"]:
                    incoming.append(inv)
                elif inv["fromUserId"] == user["id"]:
                    sent.append(inv)
            return self._send_json({
                "incoming": incoming,
                "sent": sent,
            })

        if method == "POST" and len(segments) > 1 and segments[1] in ("accept", "reject"):
            invite = next((inv for inv in invites if inv["id"] == segments[0]), None)
            if not invite:
                return self._send_error_json("Invite not found", 404)
            if invite["toUserId"] != user["id"]:
                return self._send_error_json("This invite is not for you", 403)
            if invite["status"] != "pending":
                return self._send_error_json("Invite already handled")

            if segments[1] == "reject":
                invite["status"] = "rejected"
                save("invites", invites)
                return self._send_json(invite)

            # accept
            team = next((t for t in teams if t["id"] == invite["teamId"]), None)
            if not team:
                return self._send_error_json("Team no longer exists", 404)

            is_leader = team.get("leaderId") == user["id"]
            if is_leader:
                # leader approves a join request -> add the requester (fromUser)
                person = user_by_id(invite["fromUserId"])
            else:
                # member approves an invitation -> add themselves
                person = user

            if not person:
                return self._send_error_json("User not found", 404)
            if _find_team_of_user(person["id"]):
                return self._send_error_json(f"{person['name']} is already in a team")

            new_member = {
                "userId": person["id"],
                "name": person["name"],
                "gender": person["gender"],
                "department": person["department"],
                "role": body.get("role", "Member"),
            }
            err = _add_member_error(team, new_member)
            if err:
                return self._send_error_json(err, 409)

            team["members"].append(new_member)
            invite["status"] = "accepted"
            # mark other pending invites involving this person as accepted/rejected
            for inv in invites:
                if inv["status"] == "pending" and inv["teamId"] == team["id"] and (
                    inv["toUserId"] == person["id"] or inv["fromUserId"] == person["id"]
                ):
                    inv["status"] = "accepted" if inv["id"] == invite["id"] else "rejected"
            save("teams", teams)
            save("invites", invites)
            return self._send_json({"invite": invite, "team": team})

        if method == "POST":
            team = next((t for t in teams if t["id"] == body.get("teamId")), None)
            if not team:
                return self._send_error_json("Team not found", 404)
            is_member = any(m.get("userId") == user["id"] for m in team.get("members", []))
            if not is_member:
                return self._send_error_json("Only team members can invite others", 403)
            target = user_by_id(body.get("userId"))
            if not target:
                return self._send_error_json("User not found", 404)
            if target["id"] == user["id"]:
                return self._send_error_json("You cannot invite yourself")
            if _find_team_of_user(target["id"]):
                return self._send_error_json(f"{target['name']} is already in a team")
            if any(m.get("userId") == target["id"] for m in team.get("members", [])):
                return self._send_error_json("Already a team member")
            if len(team.get("members", [])) >= TEAM_SIZE:
                return self._send_error_json(f"Team is full ({TEAM_SIZE} members)")
            if any(inv["toUserId"] == target["id"] and inv["teamId"] == team["id"] and inv["status"] == "pending" for inv in invites):
                return self._send_error_json("Invite already pending")

            invites.append({
                "id": new_id("iv"),
                "teamId": team["id"],
                "teamName": team["name"],
                "fromUserId": user["id"],
                "fromName": user["name"],
                "toUserId": target["id"],
                "toName": target["name"],
                "status": "pending",
                "created": body.get("created", ""),
            })
            save("invites", invites)
            return self._send_json(invites[-1], 201)

        return self._send_error_json("Not found", 404)

    # -- collections -------------------------------------------------------
    def _handle_collection(self, collection, method, segments, body):
        if collection == "problems":
            return self._handle_problems(method, segments, body)
        if collection == "students":
            return self._handle_students(method, segments, body)
        if collection == "teams":
            return self._handle_teams(method, segments, body)
        if collection == "announcements":
            return self._handle_announcements(method, segments, body)
        if collection == "timeline":
            return self._handle_timeline(method, segments, body)
        return self._send_error_json("Not found", 404)

    def _handle_problems(self, method, segments, body):
        problems = load("problems")
        if method == "GET":
            return self._send_json(problems)
        if not _is_admin(self.headers.get("Authorization")):
            return self._send_error_json("Admin access required", 401)
        if method == "POST":
            if not body.get("title") or not body.get("description"):
                return self._send_error_json("Title and description are required")
            problems.append({
                "id": new_id("ps"),
                "title": body["title"],
                "theme": body.get("theme", "General"),
                "org": body.get("org", "Internal"),
                "difficulty": body.get("difficulty", "Medium"),
                "description": body["description"],
            })
            save("problems", problems)
            return self._send_json(problems[-1], 201)
        if method == "DELETE" and len(segments) > 1:
            pid = segments[1]
            problems = [p for p in problems if p["id"] != pid]
            save("problems", problems)
            return self._send_json({"ok": True})
        return self._send_error_json("Method not allowed", 405)

    def _handle_students(self, method, segments, body):
        if not _is_admin(self.headers.get("Authorization")):
            return self._send_error_json("Admin access required", 401)
        students = load("students")
        if method == "GET":
            return self._send_json([public_user(s) for s in students])
        if method == "PATCH" and len(segments) > 2 and segments[2] == "status":
            sid = segments[1]
            status = body.get("status")
            if status not in STATUSES:
                return self._send_error_json("Invalid status")
            for s in students:
                if s["id"] == sid:
                    s["status"] = status
                    save("students", students)
                    return self._send_json(public_user(s))
            return self._send_error_json("Student not found", 404)
        if method == "DELETE" and len(segments) > 1:
            sid = segments[1]
            students = [s for s in students if s["id"] != sid]
            save("students", students)
            return self._send_json({"ok": True})
        return self._send_error_json("Method not allowed", 405)

    def _handle_teams(self, method, segments, body):
        teams = load("teams")
        auth = self.headers.get("Authorization")
        user = _current_user(auth)
        is_admin = _is_admin(auth)

        if method == "GET":
            return self._send_json([{**t, "stats": _team_stats(t.get("members", []))} for t in teams])

        # ---- sub-routes: join / leave / remove (must be checked before generic create) ----
        if method == "POST" and len(segments) > 2 and segments[2] == "join":
            if not user:
                return self._send_error_json("Authentication required", 401)
            team = next((t for t in teams if t["id"] == segments[1]), None)
            if not team:
                return self._send_error_json("Team not found", 404)
            if _find_team_of_user(user["id"]):
                return self._send_error_json("You are already in a team")
            if any(m.get("userId") == user["id"] for m in team.get("members", [])):
                return self._send_error_json("You are already a team member")
            if len(team.get("members", [])) >= TEAM_SIZE:
                return self._send_error_json(f"Team is full ({TEAM_SIZE} members)")
            invites = load("invites")
            if any(inv["teamId"] == team["id"] and inv["fromUserId"] == user["id"] and inv["status"] == "pending" for inv in invites):
                return self._send_error_json("Join request already pending")
            invites.append({
                "id": new_id("iv"),
                "teamId": team["id"],
                "teamName": team["name"],
                "fromUserId": user["id"],
                "fromName": user["name"],
                "toUserId": team["leaderId"],
                "toName": next((m.get("name") for m in team.get("members", []) if m.get("userId") == team["leaderId"]), "Team Leader"),
                "status": "pending",
                "created": body.get("created", ""),
            })
            save("invites", invites)
            return self._send_json(invites[-1], 201)

        if method == "POST" and len(segments) > 2 and segments[2] == "leave":
            if not user:
                return self._send_error_json("Authentication required", 401)
            team = next((t for t in teams if t["id"] == segments[1]), None)
            if not team:
                return self._send_error_json("Team not found", 404)
            if team["leaderId"] == user["id"]:
                teams = [t for t in teams if t["id"] != team["id"]]
                save("teams", teams)
                return self._send_json({"ok": True, "disbanded": True})
            team["members"] = [m for m in team.get("members", []) if m.get("userId") != user["id"]]
            save("teams", teams)
            return self._send_json({"ok": True, "disbanded": False})

        if method == "PATCH" and len(segments) > 2 and segments[2] == "remove":
            if not user:
                return self._send_error_json("Authentication required", 401)
            team = next((t for t in teams if t["id"] == segments[1]), None)
            if not team:
                return self._send_error_json("Team not found", 404)
            if team["leaderId"] != user["id"]:
                return self._send_error_json("Only the team leader can remove members", 403)
            team["members"] = [m for m in team.get("members", []) if m.get("userId") != body.get("userId")]
            save("teams", teams)
            return self._send_json({"ok": True})

        if method == "POST":
            if not user:
                return self._send_error_json("Authentication required", 401)
            if _find_team_of_user(user["id"]):
                return self._send_error_json("You are already in a team")
            if not body.get("name"):
                return self._send_error_json("Team name is required")
            problem = None
            if body.get("problemId"):
                for p in load("problems"):
                    if p["id"] == body["problemId"]:
                        problem = p
                        break
            member = {
                "userId": user["id"],
                "name": user["name"],
                "gender": user["gender"],
                "department": user["department"],
                "role": "Team Leader",
            }
            teams.append({
                "id": new_id("tm"),
                "name": body["name"].strip(),
                "leaderId": user["id"],
                "problemId": body.get("problemId", ""),
                "problemTitle": problem["title"] if problem else body.get("problemTitle", ""),
                "members": [member],
                "lookingFor": [x.strip() for x in body.get("lookingFor", []) if x.strip()],
                "created": body.get("created", ""),
            })
            save("teams", teams)
            return self._send_json(teams[-1], 201)

        if method == "DELETE" and len(segments) > 1:
            team = next((t for t in teams if t["id"] == segments[1]), None)
            if not (is_admin or (team and team.get("leaderId") == user["id"] if user else False)):
                return self._send_error_json("Admin or team leader access required", 403)
            teams = [t for t in teams if t["id"] != segments[1]]
            save("teams", teams)
            return self._send_json({"ok": True})

        return self._send_error_json("Method not allowed", 405)

    def _handle_announcements(self, method, segments, body):
        items = load("announcements")
        if method == "GET":
            return self._send_json(items)
        if not _is_admin(self.headers.get("Authorization")):
            return self._send_error_json("Admin access required", 401)
        if method == "POST":
            if not body.get("title"):
                return self._send_error_json("Title is required")
            items.append({
                "id": new_id("an"),
                "title": body["title"],
                "body": body.get("body", ""),
                "date": body.get("date", ""),
            })
            save("announcements", items)
            return self._send_json(items[-1], 201)
        if method == "DELETE" and len(segments) > 1:
            aid = segments[1]
            items = [a for a in items if a["id"] != aid]
            save("announcements", items)
            return self._send_json({"ok": True})
        return self._send_error_json("Method not allowed", 405)

    def _handle_timeline(self, method, segments, body):
        items = load("timeline")
        if method == "GET":
            return self._send_json(items)
        if not _is_admin(self.headers.get("Authorization")):
            return self._send_error_json("Admin access required", 401)
        if method == "POST":
            if not body.get("title") or not body.get("date"):
                return self._send_error_json("Date and title are required")
            items.append({
                "id": new_id("tl"),
                "date": body["date"],
                "title": body["title"],
                "detail": body.get("detail", ""),
            })
            items.sort(key=lambda x: x.get("date", ""))
            save("timeline", items)
            return self._send_json(items[-1], 201)
        if method == "DELETE" and len(segments) > 1:
            tid = segments[1]
            items = [t for t in items if t["id"] != tid]
            save("timeline", items)
            return self._send_json({"ok": True})
        return self._send_error_json("Method not allowed", 405)

    # -- entry points ------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        self._route("GET", parsed.path, parse_qs(parsed.query), {})

    def do_POST(self):
        parsed = urlparse(self.path)
        self._route("POST", parsed.path, parse_qs(parsed.query), self._read_body())

    def do_PATCH(self):
        parsed = urlparse(self.path)
        self._route("PATCH", parsed.path, parse_qs(parsed.query), self._read_body())

    def do_DELETE(self):
        parsed = urlparse(self.path)
        self._route("DELETE", parsed.path, parse_qs(parsed.query), self._read_body())


def main():
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 60)
    print("  College SIH 2026 - Selection & Team Formation Portal")
    print(f"  Main site : http://localhost:{PORT}/")
    print(f"  Dashboard : http://localhost:{PORT}/dashboard.html")
    print(f"  Admin     : http://localhost:{PORT}/admin.html")
    print(f"  Admin pw  : {ADMIN_PASSWORD}")
    print("  Seed login: 9876500001 / sih2026")
    print("  Press Ctrl+C to stop.")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
