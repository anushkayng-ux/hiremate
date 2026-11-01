"""HireMate Plus: shared pieces used by the Plus page, the candidate Insights tab, Home and the portal."""
from __future__ import annotations

import streamlit as st

import api
import ui

LEVEL = {"High": ("#B42318", "#FDE6E3"), "Medium": ("#7A4D00", "#FFF1BF"), "Low": ("#0A5A43", "#DDF1E8")}
COMMUTE = {"ok": ("#0A5A43", "#DDF1E8"), "long": ("#7A4D00", "#FFF1BF"), "very long": ("#B42318", "#FDE6E3"),
           "unknown": ("#5A566E", "#EEEDF3")}
SALARY = {"ok": ("#0A5A43", "#DDF1E8"), "low": ("#5A566E", "#EEEDF3"), "negotiate": ("#7A4D00", "#FFF1BF"),
          "high": ("#B42318", "#FDE6E3"), "unknown": ("#5A566E", "#EEEDF3")}


def chip(text: str, fg: str, bg: str) -> str:
    return f'<span class="pill" style="color:{fg};background:{bg}">{ui.esc(text)}</span>'


def plus_badge() -> str:
    return '<span class="badge">Plus</span>'


def section(title: str, sub: str = "") -> None:
    ui.html_block(f'<h3 style="margin:.2rem 0 0">{ui.esc(title)}</h3>'
                  + (f'<p class="muted small" style="margin:.1rem 0 .3rem">{ui.esc(sub)}</p>' if sub else ""))


def rupees(n) -> str:
    return f"₹{int(n):,}" if n else "—"


# ------------------------------------------------------------------ Home: the 9 AM briefing card
def briefing_card() -> None:
    b = ui.safe(api.get, "/plus/briefing")
    if not b:
        return
    with st.container(border=True, key="plusbrief"):
        a, c = st.columns([5, 1.2], vertical_alignment="top")
        a.markdown(f"{plus_badge()} <b>Your briefing for today</b>", unsafe_allow_html=True)
        a.markdown(b["text"])
        if c.button("Open Plus", icon=":material/rocket_launch:", width="stretch", key="openplus"):
            ui.go("plus")


# ------------------------------------------------------------------ candidate page: Insights tab
def candidate_insights(cid: int, jid: int, cname: str, rec: bool) -> None:
    p = ui.safe(api.get, f"/plus/candidate/{cid}", job_id=jid)
    if not p:
        return
    left, right = st.columns([1, 1], gap="medium")
    with left:
        # risk
        r = p.get("risk")
        if r:
            with st.container(border=True):
                fg, bg = LEVEL[r["level"]]
                st.markdown(f"### Dropout risk &nbsp;{chip(r['level'] + ' · ' + str(r['risk']), fg, bg)}",
                            unsafe_allow_html=True)
                for x in r["reasons"]:
                    ui.html_block(f'<div class="small">• {ui.esc(x["reason"])}</div>')
                if not r["reasons"]:
                    ui.html_block('<div class="small muted">No warning signs.</div>')
                ui.html_block(f'<div class="note" style="margin-top:.4rem">Next: {ui.esc(r["next"])}</div>')
                if r["reasons"] and st.button("Write a check-in message", key="nudge", icon=":material/chat:"):
                    st.session_state["_nudge"] = api.get(f"/plus/dropout/{r['application_id']}/nudge")["text"]
                if st.session_state.get("_nudge"):
                    st.text_area("Check-in message (copy to WhatsApp or an email)", st.session_state["_nudge"], height=110)
        # commute + salary
        with st.container(border=True):
            st.markdown("### Practical fit")
            cm = p["commute"]
            fg, bg = COMMUTE[cm["level"]]
            ui.html_block(f'<div class="qa"><b style="width:6.5rem">Commute</b><div>'
                          + (chip(f"~{cm['minutes']} min · {cm['km']} km", fg, bg) + f'<br><span class="small muted">'
                             f'{ui.esc(cm["from"])} → {ui.esc(cm["to"])}. {ui.esc(cm["text"])}</span>' if cm["known"]
                             else f'<span class="small muted">{ui.esc(cm["text"])}</span>') + "</div></div>")
            sf = p.get("salary")
            if sf:
                fg, bg = SALARY[sf["level"]]
                ui.html_block(f'<div class="qa"><b style="width:6.5rem">Salary</b><div>'
                              + chip(f"Expects {rupees(sf['expected'])}" if sf["expected"] else "Not asked yet", fg, bg)
                              + f'<br><span class="small muted">Band {rupees(sf["min"])}–{rupees(sf["max"])} a month. '
                                f'{ui.esc(sf["text"])}</span></div></div>')
            tr = p["train"]
            ui.html_block(f'<div class="qa"><b style="width:6.5rem">Hire &amp; train</b><div>'
                          + (chip(f"{tr['weeks']:g} weeks to learn", "#0A5A43", "#DDF1E8") if tr["trainable"] else "")
                          + f'<br><span class="small muted">{ui.esc(tr["text"])}</span>'
                          + "".join(f'<div class="small">• {ui.esc(m["skill"])}: {m["weeks"]:g} wk · {ui.esc(m["how"])}</div>'
                                    for m in tr["missing"]) + "</div></div>")
        # success profile
        sp = p["success"]
        with st.container(border=True):
            st.markdown(f"### Success profile &nbsp;{chip(str(sp.get('matches', 0)) + ' of ' + str(len(sp['traits'])), '#2B2350', '#E7E3F6')}",
                        unsafe_allow_html=True)
            st.caption(f"Compared with {sp['basis']}.")
            for k, v in (sp.get("candidate") or {}).items():
                ui.html_block(f'<div class="small">{"✓" if v else "✗"} {ui.esc(k)}</div>')
        # elsewhere
        for e in p.get("elsewhere") or []:
            with st.container(border=True):
                st.markdown(f"### Better fit elsewhere")
                ui.html_block(f'<div class="small">{ui.esc(cname)} scores <b>{e["to_score"]}%</b> for <b>{ui.esc(e["to_job"])}</b> '
                              f'vs {e["from_score"]}% for {ui.esc(e["from_job"])}.</div>')
                if st.button(f"Add to {e['to_job']}", key=f"bf{e['to_job_id']}", type="primary", disabled=not rec):
                    api.post("/plus/best-fit/move", json={"job_id": e["to_job_id"], "candidate_id": cid})
                    ui.toast_next(f"Added to {e['to_job']}")
                    st.rerun()
    with right:
        # why not
        wn = p["why_not"]
        with st.container(border=True):
            st.markdown("### Why this score?")
            for x in wn["reasons"]:
                ui.html_block(f'<div class="small">• {ui.esc(x)}</div>')
            if wn.get("best_fix") and wn["best_fix"]["gain"] > 0:
                f = wn["best_fix"]
                ui.html_block(f'<div class="note" style="margin-top:.4rem">Biggest single change: <b>{ui.esc(f["what"])}</b> '
                              f'would take the score from {wn["score"]}% to {f["new_score"]}% (+{f["gain"]}).</div>')
        # integrity
        ig = p["integrity"]
        with st.container(border=True):
            st.markdown("### CV integrity check")
            if ig["ok"]:
                ui.html_block('<div class="okbox">Nothing looks inconsistent.</div>')
            for x in ig["flags"]:
                ui.html_block(f'<div class="flag">⚠ {ui.esc(x)}</div>')
        # career path
        cp = p["career"]
        with st.container(border=True):
            st.markdown("### Career path")
            st.caption(cp["story"])
            if cp["roles"]:
                import altair as alt
                import pandas as pd
                df = pd.DataFrame([{"role": f'{r["role"]} · {r["org"].split(",")[0]}', "start": f'{r["start"] // 12}-{r["start"] % 12 + 1:02d}-01',
                                    "end": f'{r["end"] // 12}-{r["end"] % 12 + 1:02d}-28', "level": r["level"],
                                    "from": r["start_label"], "to": r["end_label"]} for r in cp["roles"]])
                ch = alt.Chart(df).mark_bar(cornerRadius=4, height=16).encode(
                    x=alt.X("start:T", title=None), x2="end:T", y=alt.Y("role:N", sort=None, title=None),
                    color=alt.Color("level:Q", scale=alt.Scale(range=["#D4D2DE", "#2B2350"]), legend=None),
                    tooltip=["role", "from", "to"]).properties(height=34 * len(df) + 20)
                st.altair_chart(ch, width="stretch")
        # panel
        pn = p["panel"]
        if pn["raters"]:
            with st.container(border=True):
                st.markdown("### Panel agreement")
                for g in pn["gaps"]:
                    ui.html_block(f'<div class="flag">⚠ {ui.esc(g["text"])}</div>')
                if not pn["gaps"]:
                    ui.html_block('<div class="okbox">' + ("Interviewers agree." if len(pn["raters"]) > 1 else
                                                          "One rating so far. Add a second rater below.") + "</div>")
                with st.expander("Add another interviewer's ratings"):
                    with st.form("panel"):
                        who = st.text_input("Interviewer", "Second interviewer (HR)")
                        skills = sorted({s for r in pn["raters"] for s in r["scores"]})
                        sc = {s: st.slider(s, 1, 5, 3, key=f"pn{s}") for s in skills}
                        if st.form_submit_button("Save ratings"):
                            api.post("/plus/panel", json={"job_id": jid, "candidate_id": cid, "rater": who, "scores": sc})
                            st.rerun()
        # portal results
        if p.get("screening") or p.get("test"):
            with st.container(border=True):
                st.markdown("### Candidate's own answers")
                s = p.get("screening")
                if s:
                    st.markdown(f"**AI chat screening:** {s['total']}%")
                    for it in s["items"]:
                        with st.expander(f"{it['score']}/5 · {it['question'][:60]}"):
                            st.write(it["answer"] or "—")
                            st.caption(it["why"])
                t = p.get("test")
                if t:
                    st.markdown(f"**Billing test:** {t['score']}/{t['total']} correct in {t['seconds'] // 60}m {t['seconds'] % 60}s")
        # second opinion + decision journal
        with st.container(border=True):
            st.markdown("### Before you decide")
            if st.button("Get a second opinion", icon=":material/balance:", key="2nd"):
                st.session_state[f"2nd{cid}{jid}"] = api.get("/plus/second-opinion", job_id=jid, candidate_id=cid)
            so = st.session_state.get(f"2nd{cid}{jid}")
            if so:
                st.markdown(f"**{so['side']}**")
                st.markdown(so["text"] or "\n".join(f"- {x}" for x in so["points"]))
            with st.form("decision", clear_on_submit=True):
                d = st.selectbox("Decision", ["Shortlist", "Interview", "Hire", "Not selected", "Hold"])
                why = st.text_input("Why, in one line", placeholder="e.g. Strong billing test; commute is fine")
                if st.form_submit_button("Save to decision journal", disabled=not rec):
                    if ui.safe(api.post, "/plus/decision", json={"job_id": jid, "candidate_id": cid, "decision": d,
                                                                 "reason": why}):
                        ui.toast_next("Saved to the decision journal")
                        st.rerun()
        # ask the CV
        with st.container(border=True):
            st.markdown("### Ask the CV")
            q = st.text_input("Question", placeholder="Has she handled cash? How big was the team?", key=f"askcv{cid}")
            if q:
                a = api.post(f"/plus/ask-cv/{cid}", json={"question": q})
                st.markdown(a["answer"])
                for x in a["quotes"]:
                    ui.html_block(f'<div class="ev">"{ui.esc(x)}"</div>')
        # joining checklist (after an accepted offer)
        jn = p.get("joining")
        if jn and jn["open"]:
            with st.container(border=True):
                st.markdown(f"### Joining documents · {jn['done']}/{jn['total']} checked")
                for it in jn["items"]:
                    a, b = st.columns([4, 1.4], vertical_alignment="center")
                    a.markdown(f"{'✅' if it['verified'] else '📄' if it['uploaded'] else '⬜'} {it['doc']}")
                    if it["uploaded"] and not it["verified"] and b.button("Mark checked", key=f"vf{it['doc']}", disabled=not rec):
                        api.post(f"/plus/joining/{jn['application_id']}/verify?doc={it['doc']}")
                        st.rerun()


# ------------------------------------------------------------------ blind first look (used by ui.name)
@st.cache_data(ttl=5, show_spinner=False)
def _blind_state(token: str) -> tuple[bool, tuple]:
    try:
        r = api._session().get(api.API_URL + "/plus/blind-first", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
        return bool(r["on"]), tuple(r["revealed"])
    except Exception:  # noqa: BLE001
        return False, ()


def hidden(cid: int | None) -> bool:
    tok = st.session_state.get("token")
    if not tok or not cid or "user" not in st.session_state:
        return False
    on, rev = _blind_state(tok)
    return on and cid not in rev
