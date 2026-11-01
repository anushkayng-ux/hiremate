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
    for col, (lbl, em) in zip((a, b, c), [("Admin", "muskan@hiremate.demo"), ("Recruiter", "recruiter@hiremate.demo"),
                                           ("Interviewer", "interviewer@hiremate.demo")]):
        col.button(lbl, key=f"d_{lbl}", width="stretch", on_click=_fill, args=("r_email", "r_pw", em, "recruit123"))
    st.session_state.setdefault("r_email", "muskan@hiremate.demo")
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
    have, new = st.tabs(["I have an account", "New here? Apply with your CV"])
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
    left, right = st.columns([1.05, 1], gap="large", vertical_alignment="center")
    with left:
        st.markdown(
            '<div class="hero"><p class="eyb" style="color:#BFDBFE">Vishal Mega Mart · Careers & HR</p>'
            '<h1 style="color:#fff;margin:.2rem 0 .6rem;font-size:2.4rem;line-height:1.15">Hire the right people,<br>faster.</h1>'
            '<p style="color:#DBEAFE;font-size:1.05rem;margin:0 0 1.2rem">HireMate reads CVs, ranks candidates, '
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
        st.caption("All data is synthetic. Demo only.")


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
st.session_state["_nav_key"] = next((k for k, p in pages.items() if p is nav), "dashboard")
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
