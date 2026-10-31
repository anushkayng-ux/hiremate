"""Dashboard and analytics numbers."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date

from .. import db
from ..core import ml
from . import interviews, recruit


def dashboard() -> dict:
    jobs = recruit.list_jobs(status="Open")
    apps = db.rows("SELECT a.*, c.name, j.title FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                   "JOIN jobs j ON j.id=a.job_id")
    upcoming = interviews.list_all("upcoming")
    needs = []
    for a in apps:
        if a["stage"] == "Applied":
            needs.append({"kind": "Screen", "text": f"Screen {a['name']} for {a['title']}", **_ids(a)})
        elif a["stage"] == "Shortlisted":
            needs.append({"kind": "Schedule", "text": f"Schedule an interview with {a['name']} ({a['title']})", **_ids(a)})
    for iv in interviews.list_all("past"):
        if not iv["has_feedback"] and iv["status"] != "Cancelled":
            needs.append({"kind": "Feedback", "text": f"Add interview feedback for {iv['candidate']}",
                          "job_id": iv["job_id"], "candidate_id": iv["candidate_id"],
                          "name": iv["candidate"], "job": iv["job_title"]})
    for a in apps:
        if a["stage"] == "Interview" and db.one("SELECT id FROM interview_feedback WHERE application_id=?", (a["id"],)):
            needs.append({"kind": "Decide", "text": f"Decide on {a['name']} for {a['title']} (feedback is in)", **_ids(a)})
    roles = []
    for j in jobs:
        top = db.one("SELECT c.id, c.name, m.score FROM applications a JOIN candidates c ON c.id=a.candidate_id "
                     "JOIN match_results m ON m.application_id=a.id WHERE a.job_id=? AND a.stage!='Rejected' "
                     "ORDER BY m.score DESC LIMIT 1", (j["id"],))
        roles.append({"id": j["id"], "title": j["title"], "location": j["location"], "applicants": j["applicants"],
                      "stage_counts": j["stage_counts"], "top": top})
    order = {"Decide": 0, "Feedback": 1, "Schedule": 2, "Screen": 3}
    return {
        "kpis": {"open_roles": len(jobs), "applications": len(apps),
                 "to_screen": sum(a["stage"] == "Applied" for a in apps), "interviews_ahead": len(upcoming)},
        "needs": sorted(needs, key=lambda n: order[n["kind"]])[:8],
        "upcoming": upcoming[:5], "roles": roles, "today": str(date.today()),
    }


def _ids(a: dict) -> dict:
    return {"job_id": a["job_id"], "candidate_id": a["candidate_id"], "application_id": a["id"],
            "name": a["name"], "job": a["title"]}


def analytics() -> dict:
    jobs = recruit.list_jobs()
    apps = db.rows("SELECT a.stage, a.job_id, m.score, m.details_json FROM applications a "
                   "LEFT JOIN match_results m ON m.application_id=a.id")
    funnel_order = ["Applied", "Screening", "Shortlisted", "Interview", "Selected"]
    reached = {s: 0 for s in funnel_order}
    for a in apps:
        if a["stage"] == "Rejected":
            continue
        for s in funnel_order[: funnel_order.index(a["stage"]) + 1]:
            reached[s] += 1
    missing = Counter()
    for a in apps:
        if a["details_json"]:
            missing.update(json.loads(a["details_json"]).get("missing_must", []))
    by_job = []
    for j in jobs:
        sc = [a["score"] for a in apps if a["job_id"] == j["id"] and a["score"] is not None]
        by_job.append({"job": j["short"], "applications": j["applicants"],
                       "avg_match": round(sum(sc) / len(sc)) if sc else 0, **j["stage_counts"]})
    total = len(apps) or 1
    shortlisted = sum(a["stage"] in ("Shortlisted", "Interview", "Selected") for a in apps)
    cands = db.rows("SELECT id, name, cv_text FROM candidates")
    return {
        "by_job": by_job, "funnel": [{"stage": s, "count": reached[s]} for s in funnel_order],
        "missing_skills": [{"skill": s, "count": n} for s, n in missing.most_common(8)],
        "rates": {"shortlist_rate": round(shortlisted / total * 100),
                  "interviews_done": db.one("SELECT COUNT(*) n FROM interviews WHERE status='Done'")["n"],
                  "selected": sum(a["stage"] == "Selected" for a in apps),
                  "rejected": sum(a["stage"] == "Rejected" for a in apps)},
        "talent_groups": ml.clusters(cands),
        "model": {"logistic_regression_train_accuracy": round(ml.lr_accuracy(), 2)},
    }
