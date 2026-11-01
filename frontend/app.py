"""HireMate frontend. Run: streamlit run frontend/app.py"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

import time  # noqa: E402

import api  # noqa: E402

_T0 = time.perf_counter()
api.STATS.update(n=0, ms=0.0, calls=[])
import chat  # noqa: E402,F401
import ui  # noqa: E402

st.set_page_config(page_title="HireMate", page_icon="✦", layout="wide", initial_sidebar_state="expanded")
ui.setup()


def _fill(ek, pk, email, pw):
    st.session_state[ek], st.session_state[pk] = email, pw


def _signin_recruiter():
    st.markdown('<p class="small muted" style="margin:.2rem 0">Try a demo account (one click):</p>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    for col, (lbl, em) in zip((a, b, c), [("Admin", "admin@hiremate.demo"), ("Recruiter", "recruiter@hiremate.demo"),
                                           ("Interviewer", "interviewer@hiremate.demo")]):
        col.button(lbl, key=f"d_{lbl}", width="stretch", on_click=_fill, args=("r_email", "r_pw", em, "recruit123"))
    st.session_state.setdefault("r_email", "admin@hiremate.demo")
    st.session_state.setdefault("r_pw", "recruit123")
    with st.form("login", border=True):
        email = st.text_input("Work email", key="r_email")
        pw = st.text_input("Password", type="password", key="r_pw")
        if st.form_submit_button("Sign in", type="primary", width="stretch"):
            try:
                r = api.login(email, pw)
                st.session_state.token = r["token"]
                st.session_state.user = r["user"]
                st.rerun()
            except api.ApiError as e:
                st.error(e.detail if e.status else "Can't reach the server.")
            except Exception:  # noqa: BLE001
                st.error("Can't reach the HireMate server. Is the backend running?")


def _signin_candidate():
    have, new, nocv = st.tabs(["I have an account", "New here? Apply with your CV", "No CV? Answer 6 questions"])
    with nocv:  # HireMate Plus: build a CV from simple answers, then sign up with it
        _signup_without_cv()
    with have:
        st.markdown('<p class="small muted" style="margin:.2rem 0">Try a demo candidate (one click):</p>', unsafe_allow_html=True)
        a, b = st.columns(2)
        for col, (lbl, em) in zip((a, b), [("Arjun Mehta", "arjun.mehta@example.com"), ("Priya Nair", "priya.nair@example.com")]):
            col.button(lbl, key=f"dc_{lbl}", width="stretch", on_click=_fill, args=("c_email", "c_pw", em, "candidate123"))
        st.session_state.setdefault("c_email", "arjun.mehta@example.com")
        st.session_state.setdefault("c_pw", "candidate123")
        with st.form("clogin", border=True):
            email = st.text_input("Your email", key="c_email")
            pw = st.text_input("Password", type="password", key="c_pw")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                try:
                    r = api.portal_login(email, pw)
                    st.session_state.token = r["token"]
                    st.session_state.cand = r["candidate"]
                    st.rerun()
                except api.ApiError as e:
                    st.error(e.detail if e.status else "Can't reach the server.")
    with new:
        try:
            jobs = api.public_jobs()
        except Exception:  # noqa: BLE001
            jobs = []
        with st.form("signup", border=True):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            pw = st.text_input("Make a password (6+ characters)", type="password")
            jm = {"Just create my profile": None} | {f"{j['title']} · {j['location']}": j["id"] for j in jobs}
            job = jm[st.selectbox("Apply for", list(jm))]
            f = st.file_uploader("Your CV (PDF, Word or text)", type=["pdf", "docx", "txt"])
            heard = st.selectbox("How did you hear about this job?", ["Our careers page", "Naukri", "LinkedIn", "Indeed",
                                                                        "Apna", "A friend who works here", "Walk-in / store notice"])
            ok = st.checkbox("I agree that the HR team may store and read my CV to consider me for jobs, and keep it "
                             "for up to 6 months. I can delete it any time from my profile.")
            if st.form_submit_button("Create account and apply", type="primary", width="stretch"):
                if not (name and email and pw and f):
                    st.error("Fill in every box and add your CV.")
                elif not ok:
                    st.error("Tick the privacy box so we can read your CV.")
                else:
                    src = {"Our careers page": "Candidate portal", "A friend who works here": "Referral",
                           "Walk-in / store notice": "Walk-in"}.get(heard, heard)
                    try:
                        r = api.portal_signup(name, email, pw, job, f, consent=ok, source=src)
                        st.session_state.token = r["token"]
                        st.session_state.cand = r["candidate"]
                        st.rerun()
                    except api.ApiError as e:
                        st.error(e.detail)


def _signup_without_cv():
    try:
        qs = api._session().get(api.API_URL + "/portal/plus/cv-questions", timeout=15).json()
        jobs = api.public_jobs()
    except Exception:  # noqa: BLE001
        st.error("Can't reach the HireMate server.")
        return
    with st.form("nocv", border=True):
        st.caption("Answer in Hindi or English. We write a clean CV for you.")
        ans = {q["key"]: (st.text_area(q["q"], placeholder=q["hint"], height=70) if q["key"] in ("jobs", "daily", "proud")
                          else st.text_input(q["q"], placeholder=q["hint"])) for q in qs}
        email = st.text_input("Email (to sign in later)")
        pw = st.text_input("Make a password (6+ characters)", type="password")
        jm = {"Just create my profile": None} | {f"{j['title']} · {j['location']}": j["id"] for j in jobs}
        job = jm[st.selectbox("Apply for", list(jm))]
        ok = st.checkbox("I agree that the HR team may store and read my details to consider me for jobs, and keep "
                         "them for up to 6 months. I can delete them any time from my profile.")
        if st.form_submit_button("Write my CV and apply", type="primary", width="stretch"):
            if not (ans.get("name") and email and pw and ok):
                st.error("Fill in your name, email, password and tick the privacy box.")
                return
            try:
                cv = api._session().post(api.API_URL + "/portal/plus/build-cv", json={"answers": ans}, timeout=60).json()
                data = {"name": ans["name"], "email": email, "password": pw, "consent": "true", "text": cv["text"],
                        "source": "Candidate portal"}
                if job:
                    data["job_id"] = str(job)
                r = api._session().post(api.API_URL + "/portal/signup", data=data, timeout=120)
                if r.status_code != 200:
                    st.error(r.json().get("detail", "Sign-up failed"))
                    return
                st.session_state.token = r.json()["token"]
                st.session_state.cand = r.json()["candidate"]
                st.rerun()
            except Exception:  # noqa: BLE001
                st.error("Something went wrong. Please try again.")


LOGIN_CSS = """<style>
.block-container{max-width:1180px!important;padding-top:1.4rem!important}
.hero{min-height:calc(100vh - 5.5rem);display:flex;flex-direction:column;justify-content:center;padding:2.8rem 2.5rem!important;border-radius:26px!important}
.hero h1{font-size:2.9rem!important;line-height:1.1!important}
.hero p{font-size:1.1rem}
.hero .hp{font-size:1.02rem!important;padding:.75rem 1rem!important;margin:.5rem 0!important}
.eyb{font-size:.8rem}
</style>"""


def login_page():
    st.markdown(LOGIN_CSS, unsafe_allow_html=True)
    left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            '<div class="hero"><span class="score" style="background:#FFD23F;color:#2B2350">Good fit · 82%</span>'
            '<h1 style="color:#fff;margin:.2rem 0 .6rem;font-size:2.4rem;line-height:1.15">Hire the right people,<br>faster.</h1>'
            '<p style="color:#D6D1EE;font-size:1.05rem;margin:0 0 1.2rem">HireMate reads CVs, ranks candidates, '
            'writes interview questions and drafts emails. You stay in charge.</p>'
            '<div class="hp">✓ &nbsp;Upload CVs and job descriptions</div>'
            '<div class="hp">✓ &nbsp;Best match first, with skills and gaps</div>'
            '<div class="hp">✓ &nbsp;AI drafts emails. You press Send</div>'
            '<div class="hp">✓ &nbsp;Candidates reply in their own portal</div></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<p class="eyb">Sign in</p>', unsafe_allow_html=True)
        st.markdown("## Welcome to HireMate")
        who = st.segmented_control("I am", ["Recruiter", "Candidate"], default="Recruiter", label_visibility="collapsed") \
            or "Recruiter"
        if who == "Recruiter":
            _signin_recruiter()
        else:
            _signin_candidate()
        st.caption("HireMate · HR recruitment prototype · all data is synthetic.")


if "token" not in st.session_state:
    st.navigation([st.Page(login_page, title="Sign in")], position="hidden").run()
    st.stop()

# ---------------------------------------------------------------- candidate portal (separate menu, no recruiter pages)
if "cand" in st.session_state:
    P = Path(__file__).parent / "portal"
    cp = [st.Page(P / "applications.py", title="My applications", icon=":material/work_history:", default=True),
          st.Page(P / "messages.py", title="Messages", icon=":material/mail:", url_path="messages"),
          st.Page(P / "jobs.py", title="Open jobs", icon=":material/search:", url_path="open-jobs"),
          st.Page(P / "profile.py", title="My profile", icon=":material/person:", url_path="profile"),
          # HireMate Plus (frontend/plus/)
          st.Page(Path(__file__).parent / "plus" / "portal_steps.py", title="My next steps", icon=":material/checklist:",
                  url_path="next-steps"),
          st.Page(Path(__file__).parent / "plus" / "portal_cv.py", title="Improve my CV", icon=":material/edit_note:",
                  url_path="improve-cv")]
    st.logo(str(Path(__file__).parent / "logo.svg"), size="large")
    nav = st.navigation(cp)
    with st.sidebar:
        cnd = st.session_state.cand
        st.markdown(f'<div class="prow" style="margin:.6rem 0 .3rem">{ui.avatar(cnd["name"], size=34)}<div>'
                    f'<b class="small">{ui.esc(cnd["name"])}</b><br><span class="muted small">Candidate</span>'
                    f'</div></div>', unsafe_allow_html=True)
        if st.button("Sign out", width="stretch"):
            st.session_state.clear()
            st.rerun()
    ui.show_toast()
    nav.run()
    st.stop()

V = Path(__file__).parent / "views"
pages = {
    "dashboard": st.Page(V / "dashboard.py", title="Home", icon=":material/home:", default=True),
    "jobs": st.Page(V / "jobs.py", title="Jobs", icon=":material/work:"),
    "candidates": st.Page(V / "candidates.py", title="Candidates", icon=":material/group:"),
    "interviews": st.Page(V / "interviews.py", title="Interviews", icon=":material/event:"),
    "plus": st.Page(Path(__file__).parent / "plus" / "hub.py", title="Plus", icon=":material/rocket_launch:", url_path="plus"),
    "settings": st.Page(V / "settings.py", title="Settings", icon=":material/settings:"),
    # reached from buttons, not from the menu
    "knowledge": st.Page(V / "knowledge.py", title="Documents", url_path="documents", visibility="hidden"),
    "analytics": st.Page(V / "analytics.py", title="Reports", url_path="reports", visibility="hidden"),
    "screening": st.Page(V / "screening.py", title="Compare", url_path="compare", visibility="hidden"),
    "team": st.Page(V / "team.py", title="Team", url_path="team", visibility="hidden"),
    "logs": st.Page(V / "logs.py", title="Logs", icon=":material/receipt_long:", url_path="logs"),
    "assistant": st.Page(V / "ask_ai.py", title="Ask AI", url_path="ask-ai", visibility="hidden"),
    "job": st.Page(V / "job.py", title="Job", url_path="job", visibility="hidden"),
    "review": st.Page(V / "review.py", title="Quick review", url_path="review", visibility="hidden"),
    "candidate": st.Page(V / "candidate.py", title="Candidate", url_path="candidate", visibility="hidden"),
}
ui.PAGES.update(pages)

st.logo(str(Path(__file__).parent / "logo.svg"), size="large")

_role = st.session_state.user["role"]
_keys = ["dashboard", "jobs", "candidates", "interviews", "plus"]
if _role in ("Admin", "Recruiter"):       # Settings, Documents, Team: Admin and Recruiter only
    _keys += ["settings", "knowledge", "team"]
if _role == "Admin":                      # Logs: Admin only
    _keys += ["logs"]
_keys += ["analytics", "screening", "assistant", "job", "review", "candidate"]
for _k in ("settings", "knowledge", "team", "logs"):
    if _k not in _keys:
        ui.PAGES.pop(_k, None)
nav = st.navigation([pages[k] for k in _keys])

with st.sidebar:
    u = st.session_state.user
    st.markdown('<div class="help"><b style="color:#1E1B33">Need help?</b><br>Click <b>Ask AI</b> (bottom right) '
                'and type what you want, e.g. "Who fits Store Manager?"</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="prow" style="margin:.6rem 0 .3rem">{ui.avatar(u["name"], size=34)}<div>'
                f'<b class="small">{ui.esc(u["name"])}</b><br><span class="muted small">{ui.esc(u["role"])}</span>'
                f'</div></div>', unsafe_allow_html=True)
    if st.button("Sign out", width="stretch"):
        st.session_state.clear()
        st.rerun()

ui.show_toast()
ui.show_undo()
st.session_state.view_ctx = {}  # pages fill this with the job / candidate on screen
st.session_state["_nav_key"] = next((k for k, p in pages.items() if p is nav), "dashboard")
nav.run()
_TOTAL = (time.perf_counter() - _T0) * 1000

# Floating "Ask AI" button, bottom-right on every page. Opens the chat window, no page change.
if nav is not pages["assistant"]:
    with st.container(key="askfab"):
        if st.button("Ask AI", icon=":material/auto_awesome:", type="primary", key="fab"):
            chat.open_window()

# timing log (helps find slow pages): frontend/timing.log
try:
    with open(Path(__file__).parent / "timing.log", "a", encoding="utf-8") as _f:
        _f.write(f"{time.strftime('%H:%M:%S')} page={nav.title} total={_TOTAL:.0f}ms api={api.STATS['ms']:.0f}ms "
                 f"calls={api.STATS['n']} :: {'; '.join(api.STATS['calls'])}\n")
except Exception:  # noqa: BLE001
    pass
