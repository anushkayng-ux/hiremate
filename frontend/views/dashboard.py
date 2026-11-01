"""Home: what to do today, your jobs, upcoming interviews."""
from datetime import date, datetime

import streamlit as st

import api
import ui

d = ui.safe(api.get, "/analytics/dashboard")
if d is None:
    st.stop()
u = st.session_state.user
rec = u["role"] in ("Admin", "Recruiter")
hour = datetime.now().hour
greet = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

h1, h2 = st.columns([4, 1.2], vertical_alignment="center")
with h1:
    ui.header(f"{greet}, {u['name'].split()[0]}", sub=f"{date.today():%A}, {date.today().day} {date.today():%B}. "
                                                      "Here is what needs you today.")
if h2.button("New job", icon=":material/add:", type="primary", width="stretch", disabled=not rec):
    ui.go("jobs", open_create=True)
ui.ai_note("home")

sets = ui.safe(api.get, "/settings") or {}
if rec and not (sets.get("llm") or {}).get("connected"):
    a, b = st.columns([4, 1.2], vertical_alignment="center")
    a.markdown('<div class="flag" style="font-size:.95rem"><b>AI is off.</b> Summaries, interview questions, emails and '
               'answers are using simple templates. Add your free Google Gemini key in Settings to switch AI on '
               '(takes 2 minutes).</div>', unsafe_allow_html=True)
    if b.button("Turn on AI", type="primary", width="stretch"):
        ui.go("settings")

k = d["kpis"]
hired = sum(r["stage_counts"].get("Selected", 0) for r in d["roles"])
for col, (label, v) in zip(st.columns(4), [("Open jobs", k["open_roles"]), ("New applicants to review", k["to_screen"]),
                                           ("Interviews coming up", k["interviews_ahead"]), ("Hired", hired)]):
    with col.container(border=True):
        ui.html_block(f'<div class="kpi">{v}</div><div class="kpil">{label}</div>')

from plus import plus_ui  # noqa: E402  (HireMate Plus)

plus_ui.briefing_card()

# what each to-do is, in plain words, and its button
TODO = {"Screen": ("Review CV", "#B45309", "New applicant. Read the CV and decide."),
        "Schedule": ("Book interview", "#0B6149", "Shortlisted. Book an interview."),
        "Feedback": ("Add feedback", "#7E22CE", "Interview done. Add your feedback."),
        "Decide": ("Decide", "#0E7A5C", "Feedback is in. Hire or not?")}
TAB = {"Screen": "Overview", "Schedule": "Interview", "Feedback": "Interview", "Decide": "Overview"}

left, right = st.columns([1.6, 1], gap="medium")
with left:
    with st.container(border=True):
        st.markdown(f"### To do today &nbsp;<span class='pill' style='background:#0E7A5C;color:#fff'>{len(d['needs'])}</span>",
                    unsafe_allow_html=True)
        if not d["needs"]:
            ui.html_block('<div class="okbox">All done. Nothing needs you right now.</div>')
        for i, n in enumerate(d["needs"]):
            label, color, plain = TODO.get(n["kind"], ("Open", "#3D3954", n["text"]))
            who = f'{ui.name(n.get("name", ""), n["candidate_id"])} · {n.get("job", "")}' if n.get("name") else n["text"]
            a, b = st.columns([4, 1.3], vertical_alignment="center", gap="small")
            a.markdown(f'<div class="prow">{ui.avatar(n.get("name") or "?", size=38)}<div><b>{ui.esc(who)}</b><br><span class="muted small">{plain}</span></div></div>',
                       unsafe_allow_html=True)
            if b.button(label, key=f"need{i}", width="stretch", type="primary" if i == 0 else "secondary"):
                st.session_state["cand_tab"] = TAB.get(n["kind"], "Overview")
                ui.open_candidate(n["candidate_id"], n["job_id"])

    waiting = ui.safe(api.get, "/smart/waiting") or []
    if waiting:
        with st.container(border=True):
            st.markdown(f"### Waiting too long &nbsp;<span class='pill' style='background:#FFEDD5;color:#9A3412'>{len(waiting)}</span>",
                        unsafe_allow_html=True)
            st.markdown('<p class="muted small" style="margin:0">Good candidates leave if they wait. Move these on.</p>',
                        unsafe_allow_html=True)
            for i, w in enumerate(waiting[:5]):
                a, b = st.columns([4, 1.3], vertical_alignment="center", gap="small")
                a.markdown(f'<div class="prow">{ui.avatar(w["name"], size=34)}<div><b>{ui.esc(ui.name(w["name"], w["candidate_id"]))}</b>'
                           f' · {ui.esc(w["job"])}<br><span class="muted small">{w["days"]} days in {ui.LABEL[w["stage"]]}</span>'
                           f'</div></div>', unsafe_allow_html=True)
                if b.button("Open", key=f"wait{i}", width="stretch"):
                    ui.open_candidate(w["candidate_id"], w["job_id"])

    with st.container(border=True):
        st.markdown("### Upcoming interviews")
        if not d["upcoming"]:
            st.markdown('<p class="muted">No interviews booked.</p>', unsafe_allow_html=True)
        for iv in d["upcoming"]:
            ui.html_block(f'<div class="prow" style="margin:.2rem 0">{ui.avatar(iv["candidate"], size=36)}<div>'
                          f'<b>{ui.esc(ui.name(iv["candidate"], iv["candidate_id"]))}</b> · '
                          f'<span class="small">{ui.esc(iv["job_title"])}</span><br>'
                          f'<span class="muted small">{ui.fmt_date(iv["date"])}, {ui.fmt_time(iv["time"])} · '
                          f'{ui.esc(iv["mode"])}</span></div></div>')

with right:
    inbox = ui.safe(api.get, "/emails/inbox/list") or []
    with st.container(border=True):
        st.markdown("### Replies from candidates" + (f" &nbsp;<span class='pill' style='background:#0E7A5C;color:#fff'>{len(inbox)}</span>"
                                                     if inbox else ""), unsafe_allow_html=True)
        if not inbox:
            st.markdown('<p class="muted small" style="margin:0">No new replies. When a candidate replies or confirms '
                        'an interview in their portal, it shows here.</p>', unsafe_allow_html=True)
        for m in inbox[:5]:
            ui.html_block(f'<div class="prow" style="align-items:flex-start;margin:.25rem 0">{ui.avatar(m["candidate"], size=34)}'
                          f'<div><b>{ui.esc(ui.name(m["candidate"], m["candidate_id"]))}</b> · <span class="small">'
                          f'{ui.esc(m["job_title"])}</span><br><span class="small">"{ui.esc(m["body"][:120])}'
                          f'{"…" if len(m["body"]) > 120 else ""}"</span></div></div>')
            a_, b_ = st.columns(2)
            if a_.button("Reply with AI", key=f"air{m['id']}", type="primary", width="stretch", disabled=not rec):
                with st.spinner("AI is writing a reply…"):
                    ui.safe(api.post, f"/emails/{m['id']}/ai-reply")
                st.session_state["cand_tab"] = "Emails"
                ui.open_candidate(m["candidate_id"], m["job_id"])
            if b_.button("Open", key=f"opm{m['id']}", width="stretch"):
                st.session_state["cand_tab"] = "Emails"
                ui.open_candidate(m["candidate_id"], m["job_id"])
    drafts = ui.safe(api.get, "/emails", status="Draft") or []
    with st.container(border=True):
        st.markdown("### Emails ready to send" + (f" &nbsp;<span class='pill' style='background:#0E7A5C;color:#fff'>{len(drafts)}</span>"
                                                  if drafts else ""), unsafe_allow_html=True)
        if not drafts:
            st.markdown('<p class="muted small" style="margin:0">None. AI writes a draft each time you book an '
                        'interview, hire someone, or mark someone not selected. You press Send.</p>', unsafe_allow_html=True)
        for e in drafts[:6]:
            with st.expander(f"{e['type_label']} · {ui.name(e['candidate'], e['candidate_id'])}"):
                st.markdown(f"**{e['subject']}**  \nTo: {e['to_email'] or 'no email in CV'}")
                st.text(e["body"][:1200])
                a_, b_ = st.columns(2)
                if a_.button("Send", icon=":material/send:", key=f"apv{e['id']}", type="primary", width="stretch",
                             disabled=not rec or not e["to_email"]):
                    ui.safe(api.post, f"/emails/{e['id']}/send")
                    ui.toast_next(f"Sent to {e['candidate']}. It is in their candidate portal now.")
                    st.rerun()
                if b_.button("Edit first", key=f"ed{e['id']}", width="stretch"):
                    st.session_state["cand_tab"] = "Emails"
                    ui.open_candidate(e["candidate_id"], e["job_id"])
    with st.container(border=True):
        st.markdown("### Your jobs")
        if not d["roles"]:
            st.markdown('<p class="muted">No open jobs. Click <b>New job</b>.</p>', unsafe_allow_html=True)
        for r in d["roles"]:
            a, b = st.columns([3, 1], vertical_alignment="center", gap="small")
            top = r["top"]
            best = (f'Best: {ui.esc(ui.name(top["name"], top["id"]))} {ui.score_chip(top["score"])}' if top
                    else "No CVs yet")
            a.markdown(f'<b>{ui.esc(r["title"])}</b><br><span class="muted small">{r["applicants"]} people · '
                       f'{ui.esc(r["location"])}</span><br><span class="small">{best}</span>', unsafe_allow_html=True)
            if b.button("Open", key=f"role{r['id']}", width="stretch"):
                ui.open_job(r["id"])
    if st.button("See reports", icon=":material/insights:", width="stretch"):
        ui.go("analytics")
