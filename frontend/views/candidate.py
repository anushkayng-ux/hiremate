from datetime import date, datetime, time, timedelta

import streamlit as st

import api
import ui

cid = st.session_state.get("cand_id")
if not cid:
    st.info("Pick a candidate from the Candidates page.")
    st.stop()
c = ui.safe(api.get, f"/candidates/{cid}")
if not c:
    st.stop()
rec = st.session_state.user["role"] in ("Admin", "Recruiter")
jobs = api.get("/jobs")
applied = [a["job_id"] for a in c["applications"]]
jid = st.session_state.get("cand_job") or (applied[0] if applied else jobs[0]["id"])
nm = ui.name(c["name"], c["id"])

if st.button(f"← {next((j['title'] for j in jobs if j['id'] == jid), 'Back')}", type="tertiary"):
    ui.open_job(jid) if jid in applied else ui.go("candidates")
order = applied + [j["id"] for j in jobs if j["id"] not in applied]
st.session_state.cand_job = jid
st.session_state.view_ctx = {"candidate_id": cid, "job_id": jid}
m = api.get(f"/match/job/{jid}/candidate/{cid}")

with st.container(border=True):
    x, y, z = st.columns([4, 1.2, 1.5], vertical_alignment="center")
    sub = " · ".join(v for v in [c["headline"], c["location"], f'{c["years"]:g} years', c["education"]] if v)
    x.markdown(f'<div class="prow">{ui.avatar(nm, m["score"], 60)}<div><span style="font-size:1.6rem;font-weight:700">'
               f'{ui.esc(nm)}</span> &nbsp;{ui.score_chip(m["score"])}<br><span class="muted">{ui.esc(sub)}</span>'
               f'</div></div>', unsafe_allow_html=True)
    if m["stage"]:
        if m["stage"] not in ("Rejected", "Selected") and y.button("Not selected", width="stretch", disabled=not rec):
            st.session_state.confirm_rej = True
        if m["stage"] == "Rejected" and y.button("Bring back", width="stretch", disabled=not rec):
            api.patch(f"/applications/{m['application_id']}", json={"stage": "Screening"})
            st.rerun()
        with z:
            ui.next_step_button({**m, "name": c["name"], "candidate_id": cid}, jid, "nextbig", rec)
    elif z.button("Add to this job", type="primary", width="stretch", disabled=not rec):
        api.post("/applications", json={"job_id": jid, "candidate_id": cid})
        st.rerun()
    ui.html_block(ui.stepper(m["stage"]) if m["stage"] else
                  '<p class="muted small">Not in this job yet. Click <b>Add to this job</b>.</p>')
    if st.session_state.get("confirm_rej"):
        st.warning(f"Mark {nm} as not selected for this job? A polite email will be drafted for you. "
                   "Nothing is sent until you press Send.")
        p, q, _ = st.columns([1, 1, 3])
        if p.button("Yes, not selected", type="primary"):
            ui.move(m["application_id"], "Rejected", c["name"], cid)
            st.session_state.pop("confirm_rej")
            st.rerun()
        if q.button("Cancel"):
            st.session_state.pop("confirm_rej")
            st.rerun()
    if len(jobs) > 1:
        with st.popover("Look at another job for this person", icon=":material/swap_horiz:"):
            pick = st.radio("Job", order, index=order.index(jid) if jid in order else 0,
                            format_func=lambda i: next(j["title"] for j in jobs if j["id"] == i)
                            + ("" if i in applied else " (not added)"), label_visibility="collapsed")
            if pick != jid:
                st.session_state.cand_job = pick
                st.rerun()

TABS = ["Overview", "Interview", "Emails", "Notes"]
want = st.session_state.pop("cand_tab", None)
if want in TABS:
    st.session_state["ctab"] = want
tab = st.segmented_control("Section", TABS, default="Overview", key="ctab", label_visibility="collapsed") or "Overview"

# ------------------------------------------------------------ overview
if tab == "Overview":
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        flags = api.get(f"/smart/flags/{cid}", job_id=jid)
        with st.container(border=True):
            st.markdown("### Things to check" + (f" &nbsp;<span class='pill' style='background:#FFEDD5;color:#9A3412'>"
                                                 f"{sum(f['level'] == 'warn' for f in flags)}</span>"
                                                 if any(f["level"] == "warn" for f in flags) else ""), unsafe_allow_html=True)
            ui.html_block(ui.flags_html(flags))
        with st.container(border=True):
            st.markdown("### Why this match")
            must = [r for r in m["rows"] if r["must"]] or m["rows"]
            got = [r for r in must if r["status"] != "Missing"]
            ui.html_block(f'<p class="small" style="color:{"#15803D" if len(got) == len(must) else "#B45309"};font-weight:600;margin:0">'
                          f'Has {len(got)} of {len(must)} must-have skills</p>')
            for r in must:
                ok = r["status"] != "Missing"
                proof = (f'"{ui.esc(r["evidence"][:140])}"' if r["evidence"] else
                         "Only listed in skills, no example in the CV" if ok else "Not found in the CV")
                ui.html_block(f'<div class="prow" style="align-items:flex-start;margin:.35rem 0">'
                              f'<span class="{"has" if ok else "miss"}" style="margin:0">{"✓" if ok else "✗"}</span><div>'
                              f'<b class="small">{ui.esc(r["skill"])}</b><br><span class="muted small">{proof}</span></div></div>')
            ok_y = m["years"] >= m["min_years"]
            ui.html_block(f'<div class="{"okbox" if ok_y else "warnbox"}">Experience: {m["years"]:g} years. '
                          f'The job needs {m["min_years"]:g}+. {"✓" if ok_y else "✗"}</div>')
            if m.get("criteria"):
                ui.html_block('<p class="small" style="margin:.6rem 0 .2rem"><b>Your rules</b></p>' + "".join(
                    f'<div class="small" style="margin:.15rem 0">{"✓" if x["status"] == "met" else "½" if x["status"] == "partly" else "✗" if x["status"] == "not met" else "?"} '
                    f'{ui.esc(x["text"])} <span class="muted">· {ui.esc(x["evidence"][:100]) or x["status"]}</span></div>'
                    for x in m["criteria"]))
            if m["tips"]:
                ui.html_block('<p class="small" style="margin:.6rem 0 0"><b>To check in the interview</b><br>' +
                              "<br>".join("• " + ui.esc(t) for t in m["tips"]) + "</p>")
        with st.container(border=True):
            key = f"sum{cid}-{jid}"
            a, b = st.columns([3, 1.3], vertical_alignment="center")
            a.markdown("### Quick summary")
            if b.button("Write with AI" if key not in st.session_state else "Rewrite", key="sumbtn", width="stretch"):
                with st.spinner("Reading the CV…"):
                    st.session_state[key] = api.get("/ai/summary", job_id=jid, candidate_id=cid)
            if key in st.session_state:
                s = st.session_state[key]
                st.markdown(s["text"])
                st.caption("Written by AI from the CV." if s["ai"] else "Simple version (AI not answering; check Settings → AI model → Test).")
            else:
                st.markdown('<p class="muted small">Click <b>Write with AI</b> for a short summary of this person.</p>',
                            unsafe_allow_html=True)
    with right:
        with st.container(border=True):
            a, b = st.columns([1, 2], vertical_alignment="center")
            a.markdown("### CV")
            b.markdown('<p class="muted small" style="text-align:right;margin:0">Yellow = proof for a skill</p>',
                       unsafe_allow_html=True)
            ui.html_block(f'<div class="resume">{ui.highlight(c["cv_text"], [r["evidence"] for r in m["rows"] if r["status"] == "Proven"])}</div>')
        with st.expander("Advanced details"):
            fam = ", ".join(f"{f} {round(p * 100)}%" for f, p in c["family"])
            st.caption(f"Score parts: skills {m['skill_score']} · CV text {m['text_score']} · experience {m['exp_score']}. "
                       f"Job family guess: {fam}. Shortlist chance from past decisions: {round(m['shortlist_chance'] * 100)}%.")
            ui.html_block(ui.skill_chips(m["rows"]))
            sim = api.get(f"/candidates/{cid}/similar")
            if sim:
                st.markdown("**Similar people**")
                for s in sim:
                    if st.button(f"{ui.name(s['name'], s['id'])} · {s['headline']}", key=f"sim{s['id']}"):
                        ui.open_candidate(s["id"], jid)
            if c["roles"]:
                st.markdown("**Work history**")
                for r in c["roles"]:
                    st.markdown(f"{r['role']}, {r['org']} · {r['dates']}")

# ------------------------------------------------------------ interview
if tab == "Interview":
    if not m["stage"]:
        st.info("Add this candidate to the job first.")
    else:
        ivs = api.get("/interviews", candidate_id=cid, job_id=jid)
        cur = next((i for i in reversed(ivs) if i["status"] == "Scheduled"), ivs[-1] if ivs else None)
        left, right = st.columns([1, 1.3], gap="large")
        with left:
            st.markdown("### 1. Book the interview")
            if cur:
                ui.html_block(f'<div class="okbox">Booked: {ui.fmt_date(cur["date"])}, {ui.fmt_time(cur["time"])} · '
                              f'{ui.esc(cur["mode"])} · {ui.esc(cur["interviewer"])} · {cur["status"]}</div>')
                resp = cur.get("candidate_response")
                ui.html_block(f'<div class="{"okbox" if resp == "Confirmed" else "flag" if resp else "flag info"}" style="margin-top:.3rem">'
                              + (f'Candidate: {ui.esc(resp)}' + (f' · "{ui.esc(cur.get("candidate_note"))}"' if cur.get("candidate_note") else "")
                                 if resp else "Candidate has not answered yet. They confirm from their portal.") + '</div>')
            if rec and not (cur and cur["status"] == "Scheduled"):
                st.markdown('<p class="small" style="margin:.3rem 0 .2rem"><b>Free times</b> · one click books it and '
                            'writes the invite email (you press Send)</p>', unsafe_allow_html=True)
                who = st.text_input("Interviewer", "Store Manager", key=f"ivwho{cid}")
                mode_q = st.radio("How", ["In person", "Video call", "Phone"], horizontal=True, key=f"ivmode{cid}")
                sl = api.get("/smart/slots", job_id=jid, candidate_id=cid, interviewer=who)
                for i, sl_ in zip(st.columns(len(sl) or 1), sl):
                    if i.button(sl_["label"], key=f"slot{sl_['date']}{sl_['time']}", width="stretch", type="primary"):
                        r = ui.safe(api.post, "/smart/book", json={"job_id": jid, "candidate_id": cid, "date": sl_["date"],
                                                                     "time": sl_["time"], "mode": mode_q, "interviewer": who})
                        if r:
                            ui.toast_next(f"Booked {sl_['label']}. Invite email drafted. Check it and press Send in the Emails tab.")
                            st.rerun()
            if rec:
                with st.expander("Pick another time" if not cur or cur["status"] != "Scheduled" else "Change the time"), st.form("sched"):
                    x, y = st.columns(2)
                    dflt = date.today() + timedelta(days=2)
                    dd = x.date_input("Date", date.fromisoformat(cur["date"]) if cur else dflt)
                    tt = y.time_input("Time", value=datetime.strptime(cur["time"], "%H:%M").time() if cur else time(11, 0), step=900)
                    mode = x.selectbox("Mode", ["In person", "Video call", "Phone"])
                    who = y.text_input("Interviewer", cur["interviewer"] if cur else "Area Manager")
                    if st.form_submit_button("Reschedule" if cur and cur["status"] == "Scheduled" else "Schedule",
                                             type="primary"):
                        r = ui.safe(api.post, "/smart/book", json={"job_id": jid, "candidate_id": cid, "date": str(dd),
                                                                     "time": tt.strftime("%H:%M") if tt else "11:00",
                                                                     "mode": mode, "interviewer": who})
                        if r:
                            ui.toast_next("Interview booked. Invite email drafted. Check it and press Send in the Emails tab.")
                            st.rerun()
            st.markdown(f"### 3. After the interview: rate {c['name'].split()[0]} for {next((j['title'] for j in jobs if j['id'] == jid), 'this job')}")
            if m["stage"] not in ("Interview", "Selected", "Rejected") and not cur:
                st.markdown('<p class="muted small">This opens after you book the interview.</p>', unsafe_allow_html=True)
            else:
                fb = api.get("/interviews/feedback", job_id=jid, candidate_id=cid)
                with st.form("fb"):
                    scores = {}
                    st.caption("One interview, one job. Rate each must-have skill for this job: 1 = weak, 5 = strong.")
                    for s in [r["skill"] for r in m["rows"] if r["must"]][:6]:
                        scores[s] = st.slider(f"{s} skill", 1, 5, int((fb or {}).get("scores", {}).get(s, 3)))
                    text = st.text_area("Feedback", (fb or {}).get("text", ""), placeholder="What went well, any concerns, your recommendation")
                    if st.form_submit_button("Save feedback", type="primary"):
                        api.post("/interviews/feedback", json={"job_id": jid, "candidate_id": cid, "scores": scores, "text": text})
                        ui.toast_next("Feedback saved")
                        st.rerun()
                if fb:
                    st.caption(f"Last feedback by {fb['by_name']} · readiness {fb['readiness'] or '—'}%")
                    if st.button("Summarize feedback with AI"):
                        st.session_state[f"fbs{cid}{jid}"] = api.get("/ai/feedback-summary", job_id=jid, candidate_id=cid)["text"]
                    if st.session_state.get(f"fbs{cid}{jid}"):
                        st.markdown(st.session_state[f"fbs{cid}{jid}"])
        with right:
            st.markdown("### 2. Questions to ask")
            qk = f"q{cid}-{jid}"
            if cur and cur.get("questions") and qk not in st.session_state:
                st.session_state[qk] = cur["questions"]
            if st.button("Write questions with AI" if qk not in st.session_state else "Regenerate"):
                with st.spinner("Writing questions from the CV and the job…"):
                    st.session_state[qk] = api.get("/ai/questions", job_id=jid, candidate_id=cid)["questions"]
            for i, q in enumerate(st.session_state.get(qk, [])):
                with st.container(border=True):
                    ui.html_block(f'<span class="eyb">{ui.esc(q.get("type"))} · {ui.esc(q.get("skill", ""))}</span><br>'
                                  f'{ui.esc(q.get("question"))}<br><span class="muted small">Follow-up: '
                                  f'{ui.esc(q.get("follow_up", ""))}<br>Good answer: {ui.esc(q.get("good_answer", ""))}</span>')
            st.markdown("### Practical task (optional)")
            ak = f"as{cid}-{jid}"
            if cur and cur.get("assessment") and ak not in st.session_state:
                st.session_state[ak] = cur["assessment"]
            if st.button("Write a task with AI" if ak not in st.session_state else "Regenerate assessment"):
                st.session_state[ak] = api.get("/ai/assessment", job_id=jid, candidate_id=cid)["text"]
            if st.session_state.get(ak):
                st.text(st.session_state[ak])

# ------------------------------------------------------------ emails
if tab == "Emails":
    # 1) drafts waiting for you  2) the conversation (what was sent, what the candidate replied)
    types = api.get("/emails/types")
    if rec:
        with st.container(border=True):
            st.markdown("### Write a new email with AI")
            x, y, z = st.columns([2, 1, 1], vertical_alignment="bottom")
            et = x.selectbox("What kind of email?", list(types), format_func=lambda k: types[k])
            lang = y.selectbox("Language", ["English", "Hindi"])
            if z.button("Write draft", icon=":material/auto_awesome:", type="primary", width="stretch"):
                with st.spinner("AI is writing the email…"):
                    r = ui.safe(api.post, "/emails", json={"job_id": jid, "candidate_id": cid, "type": et, "lang": lang})
                if r:
                    ui.toast_next("Draft ready below. Read it, edit if needed, then press Send." if r.get("ai")
                                  else "Draft ready (simple template: add an AI key in Settings for AI-written emails).")
                st.rerun()
    drafts = [e for e in api.get("/emails", candidate_id=cid, job_id=jid, status="Draft")]
    for e in drafts:
        with st.container(border=True):
            ui.html_block(f'<span class="pill" style="background:#FEF3C7;color:#92400E">Draft · not sent</span> '
                          f'<b>{ui.esc(e["type_label"])}</b> <span class="muted small">to {ui.esc(e["to_email"] or "no email in CV")}'
                          f'</span>')
            if rec:
                subj = st.text_input("Subject", e["subject"], key=f"s{e['id']}")
                body = st.text_area("Message", e["body"], height=220, key=f"b{e['id']}")
                p, q, r_ = st.columns([1, 1, 1.3])
                if p.button("Delete draft", key=f"dl{e['id']}", width="stretch"):
                    api.delete(f"/emails/{e['id']}")
                    st.rerun()
                if q.button("Save", key=f"sv{e['id']}", width="stretch"):
                    api.patch(f"/emails/{e['id']}", json={"subject": subj, "body": body})
                    ui.toast_next("Saved")
                    st.rerun()
                if r_.button("Send", icon=":material/send:", key=f"sd{e['id']}", type="primary", width="stretch",
                             disabled=not e["to_email"]):
                    api.patch(f"/emails/{e['id']}", json={"subject": subj, "body": body})
                    ui.safe(api.post, f"/emails/{e['id']}/send")
                    ui.toast_next(f"Sent to {c['name']}. It is in their candidate portal now.")
                    st.rerun()
    th = api.get("/emails/thread/list", job_id=jid, candidate_id=cid)
    st.markdown("### Conversation")
    if not th:
        st.markdown('<p class="muted small">Nothing sent yet.</p>', unsafe_allow_html=True)
    for e in th:
        mine = e["direction"] == "out"
        when = ui.fmt_ts(e.get("sent_at") or e["created_at"])
        style = ("background:#FFFFFF;border:1px solid #E2E8F0;margin-right:12%" if mine
                 else "background:#EFF6FF;border:1px solid #BFDBFE;margin-left:12%")
        who = f'You sent · {ui.esc(e["type_label"])}' if mine else f'{ui.esc(c["name"])} replied'
        ui.html_block(f'<div style="{style};border-radius:12px;padding:.8rem 1rem;margin:.35rem 0">'
                      f'<span class="eyb" style="color:{"#64748B" if mine else "#1D4ED8"}">{who} · {when}</span><br>'
                      f'<b>{ui.esc(e["subject"])}</b><div class="small" style="white-space:pre-wrap;margin-top:.3rem">'
                      f'{ui.esc(e["body"])}</div></div>')
        if not mine and rec:
            if not e.get("read_at"):
                api.post(f"/emails/{e['id']}/read")
            if st.button("Reply with AI", icon=":material/auto_awesome:", key=f"rp{e['id']}"):
                with st.spinner("AI is writing a reply…"):
                    ui.safe(api.post, f"/emails/{e['id']}/ai-reply")
                ui.toast_next("Reply drafted above. Check it and press Send.")
                st.rerun()

# ------------------------------------------------------------ notes
if tab == "Notes":
    with st.form("note", clear_on_submit=True):
        n = st.text_area("Add a note", placeholder="Visible to your team")
        if st.form_submit_button("Save note") and n.strip():
            api.post(f"/candidates/{cid}/notes", json={"text": n, "job_id": jid})
            st.rerun()
    for n in api.get(f"/candidates/{cid}/notes"):
        ui.html_block(f'<p class="small" style="margin:.2rem 0">{ui.esc(n["text"])}<br><span class="muted">'
                      f'{ui.esc(n["by_name"])} · {ui.fmt_ts(n["created_at"])}</span></p>')
    st.markdown("**Activity**")
    for l in api.get(f"/candidates/{cid}/activity"):
        ui.html_block(f'<p class="small muted" style="margin:.1rem 0">{ui.fmt_ts(l["created_at"])} · '
                      f'<b style="color:#0F172A">{ui.esc(l["action"])}</b> {ui.esc(l["detail"] or "")}'
                      f'{" · " + ui.esc(l["job_title"]) if l["job_title"] else ""} · {ui.esc(l["by_name"])}</p>')
    if rec:
        with st.expander("Delete candidate"):
            st.warning("This removes the candidate from every job.")
            if st.button("Delete permanently"):
                api.delete(f"/candidates/{cid}")
                ui.toast_next("Candidate deleted")
                ui.go("candidates")
