"""One job: its candidates best-first, each with one next-step button."""
import streamlit as st

import api
import ui
import widgets

jobs = ui.safe(api.get, "/jobs") or []
if not jobs:
    st.info("No jobs yet.")
    st.stop()
ids = [j["id"] for j in jobs]
jid = st.session_state.get("job_id") if st.session_state.get("job_id") in ids else ids[0]
job = api.get(f"/jobs/{jid}")
rec = st.session_state.user["role"] in ("Admin", "Recruiter")
st.session_state.view_ctx = {"job_id": jid}

if st.button("← All jobs", type="tertiary"):
    ui.go("jobs")
h1, h2, h3, h4 = st.columns([3.4, 1, 1.1, 1.1], vertical_alignment="center")
with h1:
    ui.header(job["title"], sub=f"{job['location']}  ·  {job['min_years']:g}+ years  ·  {job['status']}")
if h2.button("Ask AI", icon=":material/auto_awesome:", width="stretch"):
    import chat
    chat.open_window(f"Who matches {job['short']}? Show skills and gaps.")
with h3.popover("More", icon=":material/more_horiz:", width="stretch", disabled=not rec):
    new_status = st.radio("Job status", ["Open", "Paused", "Closed"],
                          index=["Open", "Paused", "Closed"].index(job["status"]) if job["status"] in ("Open", "Paused", "Closed") else 0)
    if new_status != job["status"]:
        api.patch(f"/jobs/{jid}", json={"status": new_status})
        st.rerun()
    if st.button("Delete this job"):
        st.session_state.confirm_del_job = True
    if st.session_state.get("confirm_del_job"):
        st.warning("This removes the job and its candidate list.")
        if st.button("Yes, delete", type="primary"):
            api.delete(f"/jobs/{jid}")
            st.session_state.pop("confirm_del_job")
            ui.toast_next("Job deleted")
            ui.go("jobs")
if h4.button("Add CVs", icon=":material/add:", type="primary", width="stretch", disabled=not rec):
    widgets.upload_cvs(jid)

ranked = ui.safe(api.get, f"/match/job/{jid}") or []

# ------------------------------------------------------------ "do this next" (one thing, in plain words)
nx = api.get(f"/smart/next/{jid}")
with st.container(key="nextbox"):
    a, b = st.columns([4, 1.4], vertical_alignment="center")
    a.markdown(f'<div class="nextbar"><span class="eyb" style="color:#2563EB">Do this next</span><br>'
               f'<b style="font-size:1.05rem">{ui.esc(nx["text"])}</b></div>', unsafe_allow_html=True)
    if nx.get("button") and b.button(nx["button"], type="primary", width="stretch", key="nextgo", disabled=not rec):
        if nx["kind"] == "review":
            ui.go("review", job_id=jid, rv_restart=True)
        elif nx["kind"] == "add":
            widgets.upload_cvs(jid)
        else:
            st.session_state["cand_tab"] = "Interview" if nx["kind"] == "book" else "Overview"
            ui.open_candidate(nx["candidate_id"], jid)
n_rules = len(api.get("/criteria", job_id=jid, scope="job"))
VIEWS = ["Candidates", "Job details", f"Your rules ({n_rules})", "Find more people"]
view = st.segmented_control("View", VIEWS, default=VIEWS[0], key=f"jobview{jid}", label_visibility="collapsed") or VIEWS[0]
if view.startswith("Your rules"):
    view = "Your rules"

# ------------------------------------------------------------ candidates
if view == "Candidates":
    counts = {s: sum(r["stage"] == s for r in ranked) for s in ui.STAGES}
    opts = ["All"] + ui.FLOW + ["Rejected"]
    fmt = lambda s: (f"All  {len([r for r in ranked if r['stage'] != 'Rejected'])}" if s == "All"
                     else f"{ui.LABEL[s]}  {counts.get(s, 0)}")
    pick = st.segmented_control("Stage", opts, default="All", format_func=fmt, key=f"stage{jid}",
                                label_visibility="collapsed") or "All"
    ui.html_block(f'<p class="muted small" style="margin:0">Best match first. Must-have skills: '
                  f'<b>{ui.esc(" · ".join(job["must"]) or "none set")}</b> · {job["min_years"]:g}+ years</p>')
    rows = [r for r in ranked if (r["stage"] != "Rejected" if pick == "All" else r["stage"] == pick)]
    if not rows:
        ui.html_block('<div class="emptycol">No one here yet.'
                      + (' Click <b>Add CVs</b> to add people.' if pick == "All" else "") + '</div>')
    for i, r in enumerate(rows, 1):
        nm = ui.name(r["name"], r["candidate_id"])
        with st.container(border=True):
            x, y, z = st.columns([5, 0.9, 1.3], vertical_alignment="center")
            sub = " · ".join(v for v in [r.get("headline"), r.get("location"), f'{r["years"]:g} yrs'] if v)
            rule = ("" if not r.get("criteria") or r["meets_criteria"]
                    else ' <span class="pill" style="background:#FEE2E2;color:#B91C1C">Misses your rule</span>')
            x.markdown(f'<div class="prow"><b style="color:#94A3B8;width:1rem">{i}</b>{ui.avatar(nm, r["score"])}<div>'
                       f'<span class="pname">{ui.esc(nm)}</span> &nbsp;{ui.score_chip(r["score"])} {ui.stage_pill(r["stage"])}'
                       f'{rule}<br><span class="muted small">{ui.esc(sub)}</span></div></div>', unsafe_allow_html=True)
            if y.button("View", key=f"v{r['candidate_id']}", width="stretch"):
                ui.open_candidate(r["candidate_id"], jid)
            with z:
                ui.next_step_button(r, jid, f"nx{r['application_id']}", rec)
            ui.html_block(f'<div style="padding-left:3.6rem">{ui.has_missing(r["rows"])}</div>')
    short = [r for r in ranked if r["stage"] in ("Shortlisted", "Interview", "Selected")]
    if short:
        st.download_button(f"Share shortlist ({len(short)}) with the store manager", data=widgets.shortlist_html(job, short),
                           file_name=f"Shortlist - {job['title'].split(' /')[0]}.html", mime="text/html",
                           icon=":material/share:", help="A one-page summary. Open it and print to PDF, or send it as it is.")
    if len(rows) >= 2:
        with st.expander("Compare people side by side"):
            pk = st.multiselect("Pick 2 or 3", [r["candidate_id"] for r in rows], max_selections=3,
                                format_func=lambda c: ui.name(next(r["name"] for r in rows if r["candidate_id"] == c), c))
            if st.button("Compare", disabled=len(pk) < 2):
                widgets.compare(jid, pk)
    with st.expander("Advanced: how the score is worked out"):
        if ranked:
            w = ranked[0]["weights"]
            st.caption(f"Score = skills {w['skills']} + CV text {w['text']} + experience {w['exp']}. "
                       "Good fit = 70%+, Okay fit = 50–69%, Weak fit = below 50%. AI never rejects anyone on its own.")
            for r in ranked:
                ui.html_block(f'<span class="small"><b>{ui.esc(ui.name(r["name"], r["candidate_id"]))}</b> · '
                              f'skills {r["skill_score"]} · text {r["text_score"]} · experience {r["exp_score"]} · '
                              f'shortlist chance {round(r["shortlist_chance"] * 100)}%</span>')

# ------------------------------------------------------------ requirements
if view == "Job details":
    left, right = st.columns([1.4, 1], gap="large")
    with left:
        with st.form("req"):
            title = st.text_input("Title", job["title"])
            l1, l2 = st.columns(2)
            loc = l1.text_input("Location", job["location"])
            yrs = l2.number_input("Minimum years", 0.0, 30.0, float(job["min_years"]), 0.5)
            qual = st.text_input("Qualification", job["qualification"] or "")
            must = st.multiselect("Must-have skills (count double)", job["must"], default=job["must"],
                                  accept_new_options=True)
            nice = st.multiselect("Nice-to-have skills", job["nice"], default=job["nice"], accept_new_options=True)
            if st.form_submit_button("Save changes", type="primary", disabled=not rec):
                api.patch(f"/jobs/{jid}", json={"title": title, "location": loc, "min_years": yrs,
                                                "qualification": qual, "must": must, "nice": nice})
                ui.toast_next("Saved. Candidates re-ranked.")
                st.rerun()
    with right:
        st.markdown("**Tips to improve this job post**")
        for f in api.get(f"/jobs/{jid}/check"):
            (st.success if f["level"] == "good" else st.warning if f["level"] == "warn" else st.error)(
                f"{f['title']} — {f['fix']}")
        with st.expander("Full job description"):
            st.text(job["description"])

# ------------------------------------------------------------ rules
if view == "Your rules":
    st.markdown('<p class="muted">Your own rules for this job, on top of skills and years. Write them in plain English. '
                '<b>Must</b> rules put people who miss them at the bottom (never auto-rejected). '
                '<b>Bonus/penalty</b> rules add or take away points.</p>', unsafe_allow_html=True)
    widgets.criteria_editor(jid, f"jc{jid}", rec)

# ------------------------------------------------------------ talent pool
if view == "Find more people":
    sug = ui.safe(api.get, f"/match/job/{jid}", scope="suggested") or []
    if not sug:
        st.info("Everyone in the talent pool is already in this job.")
    for r in sug:
        with st.container(border=True):
            x, y, z = st.columns([3, 3, 1], vertical_alignment="center")
            x.markdown(f'<b>{ui.esc(ui.name(r["name"], r["candidate_id"]))}</b> {ui.score_chip(r["score"])}<br>'
                       f'<span class="muted small">{ui.esc(r["headline"])}</span>', unsafe_allow_html=True)
            y.markdown(ui.skill_chips([w for w in r["rows"] if w["must"]]), unsafe_allow_html=True)
            if z.button("Add", key=f"add{r['candidate_id']}", width="stretch", disabled=not rec):
                api.post("/applications", json={"job_id": jid, "candidate_id": r["candidate_id"]})
                ui.toast_next(f"Added {r['name']}")
                st.rerun()
