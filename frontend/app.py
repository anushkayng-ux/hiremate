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


def _signin_recruiter():
    with st.form("login", border=True):
        email = st.text_input("Work email", value="muskan@hiremate.demo")
        pw = st.text_input("Password", type="password", placeholder="recruit123")
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
    st.caption("Demo: muskan@hiremate.demo (Admin), recruiter@hiremate.demo, interviewer@hiremate.demo · password recruit123")


def _signin_candidate():
    have, new = st.tabs(["I have an account", "New here? Apply with your CV"])
    with have:
        with st.form("clogin", border=True):
            email = st.text_input("Your email", value="arjun.mehta@example.com")
            pw = st.text_input("Password", type="password", placeholder="candidate123")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                try:
                    r = api.portal_login(email, pw)
                    st.session_state.token = r["token"]
                    st.session_state.cand = r["candidate"]
                    st.rerun()
                except api.ApiError as e:
                    st.error(e.detail if e.status else "Can't reach the server.")
        st.caption("Demo: every sample candidate can sign in with their email (e.g. arjun.mehta@example.com, "
                   "priya.nair@example.com) and password candidate123.")
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
            if st.form_submit_button("Create account and apply", type="primary", width="stretch"):
                if not (name and email and pw and f):
                    st.error("Fill in every box and add your CV.")
                else:
                    try:
                        r = api.portal_signup(name, email, pw, job, f)
                        st.session_state.token = r["token"]
                        st.session_state.cand = r["candidate"]
                        st.rerun()
                    except api.ApiError as e:
                        st.error(e.detail)


def login_page():
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown('<div style="height:5vh"></div><p class="eyb">Vishal Mega Mart · Careers & HR</p>', unsafe_allow_html=True)
        st.markdown("# Welcome to HireMate")
        who = st.segmented_control("I am", ["Recruiter", "Candidate"], default="Recruiter", label_visibility="collapsed") \
            or "Recruiter"
        if who == "Recruiter":
            st.markdown('<p class="muted">Recruiter portal: jobs, CVs, matching, interviews and emails, with AI.</p>',
                        unsafe_allow_html=True)
            _signin_recruiter()
        else:
            st.markdown('<p class="muted">Candidate portal: see your applications, read and reply to messages, '
                        'confirm interviews and apply for jobs.</p>', unsafe_allow_html=True)
            _signin_candidate()
        st.caption("All data is synthetic.")


if "token" not in st.session_state:
    st.navigation([st.Page(login_page, title="Sign in")], position="hidden").run()
    st.stop()

# ---------------------------------------------------------------- candidate portal (separate menu, no recruiter pages)
if "cand" in st.session_state:
    P = Path(__file__).parent / "portal"
    cp = [st.Page(P / "applications.py", title="My applications", icon=":material/work_history:", default=True),
          st.Page(P / "messages.py", title="Messages", icon=":material/mail:", url_path="messages"),
          st.Page(P / "jobs.py", title="Open jobs", icon=":material/search:", url_path="open-jobs"),
          st.Page(P / "profile.py", title="My profile", icon=":material/person:", url_path="profile")]
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
    "settings": st.Page(V / "settings.py", title="Settings", icon=":material/settings:"),
    # reached from buttons, not from the menu (keeps the menu to 5 items)
    "knowledge": st.Page(V / "knowledge.py", title="Documents", url_path="documents", visibility="hidden"),
    "analytics": st.Page(V / "analytics.py", title="Reports", url_path="reports", visibility="hidden"),
    "screening": st.Page(V / "screening.py", title="Compare", url_path="compare", visibility="hidden"),
    "asha": st.Page(V / "ask_ai.py", title="Ask AI", url_path="ask-ai", visibility="hidden"),
    "job": st.Page(V / "job.py", title="Job", url_path="job", visibility="hidden"),
    "review": st.Page(V / "review.py", title="Quick review", url_path="review", visibility="hidden"),
    "candidate": st.Page(V / "candidate.py", title="Candidate", url_path="candidate", visibility="hidden"),
}
ui.PAGES.update(pages)

st.logo(str(Path(__file__).parent / "logo.svg"), size="large")

nav = st.navigation([pages[k] for k in ("dashboard", "jobs", "candidates", "interviews", "settings", "knowledge",
                                         "analytics", "screening", "asha", "job", "review", "candidate")])

with st.sidebar:
    u = st.session_state.user
    st.markdown('<div class="help"><b style="color:#0F172A">Need help?</b><br>Click <b>Ask AI</b> (bottom right) '
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
nav.run()
_TOTAL = (time.perf_counter() - _T0) * 1000

# Floating "Ask AI" button, bottom-right on every page. Opens the chat window, no page change.
if nav is not pages["asha"]:
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
