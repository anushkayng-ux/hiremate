"""Dialogs shared by several pages."""
from __future__ import annotations

import streamlit as st

import api
import ui


@st.dialog("Add candidates", width="large")
def upload_cvs(job_id: int | None = None):
    jobs = api.get("/jobs")
    opts = {"Talent pool only": None} | {j["title"]: j["id"] for j in jobs}
    pre = next((t for t, i in opts.items() if i == job_id), "Talent pool only")
    a_, b_ = st.columns(2)
    target = a_.selectbox("Add to", list(opts), index=list(opts).index(pre))
    srcs = ui.safe(api.get, "/x/sources") or ["Recruiter upload"]
    source = b_.selectbox("Where did these CVs come from?", srcs, help="Used for the 'Where good hires come from' report.")
    ref = st.text_input("Referred by (employee name)") if source == "Referral" else None
    tab1, tab2 = st.tabs(["Upload CVs", "Paste text"])
    with tab1:
        fs = st.file_uploader("PDF, Word or text. You can pick many at once.", type=["pdf", "docx", "txt"],
                              accept_multiple_files=True, key="cvfiles")
        if fs:
            prev = ui.safe(api.post, "/candidates/preview", files=[("files", (f.name, f.getvalue())) for f in fs]) or []
            keep = []
            for p, f in zip(prev, fs):
                with st.container(border=True):
                    if not p["ok"]:
                        st.error(f"{p['file_name']}: {p['error']}")
                        continue
                    proven = [k for k, v in p["skills"].items() if v["status"] == "Proven"]
                    ui.html_block(f'<b>{ui.esc(p["name"])}</b> · {ui.esc(p["headline"])}<br>'
                                  f'<span class="muted small">{p["years"]:g} yrs · {ui.esc(p["location"])} · '
                                  f'{ui.esc(p["edu_level"])} · proven: {ui.esc(", ".join(proven[:5]) or "none")}</span>')
                    if p["duplicate"]:
                        choices = ["Skip", "Add anyway"] + (["Use the existing profile for this job"] if opts[target] else [])
                        choice = st.radio(f"Looks like {p['duplicate']['name']} is already in your talent pool.",
                                          choices, horizontal=True, key=f"dup{f.name}")
                        if choice == "Add anyway":
                            keep.append((f, True))
                        elif choice.startswith("Use"):
                            keep.append((p["duplicate"]["id"], None))
                    else:
                        keep.append((f, False))
            if st.button(f"Add {len(keep)} candidate{'s' if len(keep) != 1 else ''}", type="primary", disabled=not keep):
                added = 0
                for f, dup in keep:
                    if dup is None:
                        added += bool(ui.safe(api.post, "/applications", json={"job_id": opts[target], "candidate_id": f,
                                                                               "source": source, "referred_by": ref}))
                        continue
                    res = ui.safe(api.post, "/candidates/upload", files=[("files", (f.name, f.getvalue()))],
                                  data={"allow_duplicate": str(dup).lower(), "source": source, "referred_by": ref or "",
                                        **({"job_id": opts[target]} if opts[target] else {})})
                    added += sum(1 for r in res or [] if r["ok"])
                ui.toast_next(f"Added {added} candidate{'s' if added != 1 else ''}")
                st.rerun()
    with tab2:
        txt = st.text_area("CV text", height=220, key="cvtext")
        if st.button("Add candidate", type="primary", disabled=len(txt or "") < 20):
            c = ui.safe(api.post, "/candidates", json={"text": txt, "job_id": opts[target]})
            if c:
                ui.toast_next(f"Added {c['name']}")
                st.rerun()


@st.dialog("Compare candidates", width="large")
def compare(job_id: int, ids: list[int]):
    res = ui.safe(api.get, "/match/compare", job_id=job_id, ids=",".join(map(str, ids))) or []
    if not res:
        return
    cols = st.columns(len(res))
    best = max(r["score"] for r in res)
    for col, r in zip(cols, res):
        with col.container(border=True):
            ui.html_block(f'<b>{ui.esc(ui.name(r["name"], r["candidate_id"]))}</b>'
                          f'{" · <span class=eyb>Leads</span>" if r["score"] == best else ""}<br>'
                          f'{ui.score_chip(r["score"])} <span class="muted small">skills {r["skill_score"]} · text '
                          f'{r["text_score"]} · exp {r["exp_score"]}</span><br><br>'
                          f'<span class="small">{r["years"]:g} yrs (asks {r["min_years"]:g}+) · {ui.stage_pill(r["stage"])}</span>'
                          f'<br><br>{ui.skill_chips(r["rows"])}<br><br>'
                          f'<span class="small muted">Missing must-haves: {ui.esc(", ".join(r["missing_must"]) or "None")}</span>')


KIND_LABEL = {"must": "Must have", "bonus": "Bonus (+ points)", "penalty": "Penalty (− points)"}
CHECK_LABEL = {"skill": "Skill in CV", "city": "City", "years": "Years of experience", "education": "Education level",
               "keyword": "Word or phrase in CV", "custom": "Anything else (AI reads the CV)"}
EXAMPLES = ["Must live in Delhi NCR", "Prefer Hindi speakers +5 points", "Must be graduate",
            "Prefer candidates with festive season experience +10 points", "Avoid less than 1 years +5 points"]


def criteria_editor(job_id: int | None, key: str, can_edit: bool = True) -> None:
    """Add / view / switch off / delete screening rules. job_id None = rules for all jobs."""
    rules = api.get("/criteria", job_id=job_id, scope="job" if job_id else "global")
    if can_edit:
        with st.container(border=True):
            st.markdown("**Add a rule** — write it in plain English")
            nk = st.session_state.get(f"{key}_n", 0)  # new key after each add, so the box clears
            txt = st.text_input("Rule", key=f"{key}_txt{nk}", label_visibility="collapsed",
                                placeholder="e.g. Must live in Delhi NCR · Prefer Hindi speakers +5 points")
            st.caption("Examples: " + " · ".join(EXAMPLES))
            if txt and len(txt) > 2:
                p = api.post("/criteria/preview", json={"text": txt})
                a, b, c, d = st.columns([1.2, 1.5, 1.6, 0.9])
                kinds, checks = list(KIND_LABEL), list(CHECK_LABEL)
                kind = a.selectbox("Type", kinds, index=kinds.index(p["kind"]), format_func=KIND_LABEL.get,
                                   key=f"{key}_k{txt}")
                chk = b.selectbox("Check", checks, index=checks.index(p["check_type"]), format_func=CHECK_LABEL.get,
                                  key=f"{key}_c{txt}")
                hint = {"years": ">=3 or <2", "education": "Class 12 / Diploma / Graduate / Postgraduate",
                        "city": "Noida, Ghaziabad", "skill": "Hindi", "keyword": "festive", "custom": "the rule text"}[chk]
                val = c.text_input("Value", p["value"] if chk == p["check_type"] else "", placeholder=hint,
                                   key=f"{key}_v{txt}{chk}")
                pts = d.number_input("Points", 0, 50, int(p["points"]), 5, key=f"{key}_p{txt}",
                                     disabled=kind == "must")
                st.caption("How it will be checked: " + p["how"] if chk == p["check_type"] and kind == p["kind"]
                           else "Edited by you. Must rules flag people; bonus/penalty change the score.")
                if st.button("Add rule", type="primary", key=f"{key}_add"):
                    r = ui.safe(api.post, "/criteria", json={"text": txt, "job_id": job_id, "kind": kind, "check_type": chk,
                                                             "value": val or None, "points": int(pts)})
                    if r:
                        st.session_state[f"{key}_n"] = nk + 1
                        ui.toast_next("Rule added. Scores updated.")
                        st.rerun()
    if not rules:
        st.markdown('<p class="muted small">No rules yet. Matching uses only the job\'s skills, text and years.</p>',
                    unsafe_allow_html=True)
    for r in rules:
        own = (r["job_id"] == job_id) if job_id else True
        with st.container(border=True):
            x, y, z = st.columns([5, 1.1, 0.9], vertical_alignment="center")
            tag = {"must": "#B42318", "bonus": "#0B6149", "penalty": "#D97706"}[r["kind"]]
            x.markdown(f'<span class="pill" style="background:#EEEDF3;color:{tag}">{KIND_LABEL[r["kind"]]}</span> '
                       f'<b>{ui.esc(r["text"])}</b>{"" if own else " <span class=muted small>· all jobs, set in Settings</span>"}'
                       f'<br><span class="muted small">{ui.esc(r["how"])}</span>', unsafe_allow_html=True)
            if own and can_edit:
                on = y.toggle("On", value=r["active"], key=f"{key}_on{r['id']}")
                if on != r["active"]:
                    api.patch(f"/criteria/{r['id']}", json={"active": on})
                    st.rerun()
                if z.button("Delete", key=f"{key}_del{r['id']}", width="stretch"):
                    api.delete(f"/criteria/{r['id']}")
                    ui.toast_next("Rule removed. Scores updated.")
                    st.rerun()
            else:
                y.markdown("On" if r["active"] else "Off")


def shortlist_html(job: dict, rows: list[dict]) -> str:
    """A clean one-page shortlist to share with the store / hiring manager (print to PDF from the browser)."""
    from datetime import date
    e = ui.esc
    cards = []
    for i, r in enumerate(rows, 1):
        must = [x for x in r["rows"] if x["must"]] or r["rows"]
        has = ", ".join(x["skill"] for x in must if x["status"] != "Missing") or "—"
        miss = ", ".join(x["skill"] for x in must if x["status"] == "Missing") or "Nothing"
        proof = "".join(f"<li>{e(x['evidence'][:140])}</li>" for x in must if x["status"] == "Proven" and x["evidence"])[:900]
        label = ui.fit(r["score"])[0]
        cards.append(f"""<div class="c"><div class="h"><span class="n">{i}. {e(ui.name(r['name'], r['candidate_id']))}</span>
<span class="t">{label} · {r['score']}%</span><span class="s">{e(ui.LABEL.get(r['stage'], r['stage']))}</span></div>
<div class="m">{e(r.get('headline', ''))} · {e(r.get('location', ''))} · {r['years']:g} years</div>
<p><b>Has:</b> {e(has)}<br><b>Missing:</b> {e(miss)}</p>{f'<ul>{proof}</ul>' if proof else ''}</div>""")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Shortlist · {e(job['title'])}</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;color:#1E1B33;max-width:820px;margin:32px auto;padding:0 20px}}
h1{{margin:0;font-size:24px}}.sub{{color:#5A566E;margin:4px 0 20px}}.c{{border:1px solid #E3E2EA;border-radius:12px;padding:14px 18px;margin:12px 0;break-inside:avoid}}
.h{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}.n{{font-weight:700;font-size:17px}}
.t{{background:#DDF1E8;color:#0E7A5C;border-radius:99px;padding:2px 10px;font-size:13px;font-weight:600}}
.s{{background:#E6F4EE;color:#0B6149;border-radius:99px;padding:2px 10px;font-size:13px;font-weight:600}}
.m{{color:#5A566E;font-size:14px;margin-top:4px}}p{{font-size:14px;margin:8px 0}}ul{{margin:4px 0 0 18px;font-size:13px;color:#3D3954}}
.f{{color:#6B6880;font-size:12px;margin-top:24px}}</style></head><body>
<h1>Shortlist: {e(job['title'])}</h1><div class="sub">{e(job['location'])} · {job['min_years']:g}+ years · prepared {date.today():%d %b %Y} with HireMate</div>
{''.join(cards)}<div class="f">Synthetic demo data. Scores help you decide; the hiring team makes every decision.</div></body></html>"""


# ===================================================================== new features (gap review)
def screening_and_source(app_id: int, can_edit: bool) -> None:
    """Answers to the job's screening questions + where the person came from."""
    ans = ui.safe(api.get, f"/x/applications/{app_id}/answers") or {"items": [], "knockout_flags": 0}
    with st.container(border=True):
        n = ans["knockout_flags"]
        st.markdown("### Screening answers" + (f" &nbsp;<span class='pill' style='background:#FFE8D6;color:#9A3412'>"
                                               f"{n} to check</span>" if n else ""), unsafe_allow_html=True)
        if not ans["items"]:
            ui.html_block('<p class="muted small" style="margin:0">This job has no screening questions. '
                          'Add them on the job page under <b>Screening questions</b>.</p>')
        for q in ans["items"]:
            mark = {True: "✓", False: "✗", None: "·"}[q["ok"]]
            col = {True: "#0E7A5C", False: "#B42318", None: "#6B6880"}[q["ok"]]
            ko = ' <span class="pill" style="background:#FFE8D6;color:#9A3412">must</span>' if q["knockout"] else ""
            ui.html_block(f'<div class="qa"><span style="color:{col};font-weight:700;width:1rem">{mark}</span><div>'
                          f'<span class="small">{ui.esc(q["question"])}{ko}</span><br>'
                          f'<b>{ui.esc(q["answer"] if q["answer"] not in (None, "") else "No answer yet")}</b>'
                          + (f' <span class="muted small">(looking for {ui.esc(q["ideal"])})</span>' if q["ideal"] else "")
                          + '</div></div>')
        if n:
            st.caption("A 'must' answer that doesn't match is a flag to talk about, not a rejection. You decide.")
        srcs = ui.safe(api.get, "/x/sources") or []
        with st.popover("Source of this application", icon=":material/call_split:", disabled=not can_edit):
            s_ = st.selectbox("Source", srcs, key=f"srcsel{app_id}")
            r_ = st.text_input("Referred by", key=f"srcref{app_id}") if s_ == "Referral" else None
            if st.button("Save source", type="primary", key=f"srcsave{app_id}"):
                ui.safe(api.patch, f"/x/applications/{app_id}/source", json={"source": s_, "referred_by": r_})
                ui.toast_next(f"Source saved: {s_}")
                st.rerun()


def questions_editor(job_id: int, can_edit: bool) -> None:
    qs = ui.safe(api.get, f"/x/jobs/{job_id}/questions") or []
    st.markdown('<p class="muted">Candidates answer these when they apply in the portal. A <b>must</b> question '
                'flags people whose answer doesn\'t match, so you can check it in a call. Nobody is rejected '
                'automatically.</p>', unsafe_allow_html=True)
    kinds = {"yesno": "Yes / No", "number": "Number", "text": "Short answer"}
    for q in qs:
        with st.container(border=True):
            a, b = st.columns([6, 1], vertical_alignment="center")
            ko = ' <span class="pill" style="background:#FFE8D6;color:#9A3412">must</span>' if q["knockout"] else ""
            a.markdown(f'<b>{ui.esc(q["question"])}</b>{ko}<br><span class="muted small">{kinds.get(q["kind"])}'
                       + (f' · looking for {ui.esc(q["ideal"])}' if q["ideal"] else "") + "</span>",
                       unsafe_allow_html=True)
            if b.button("Remove", key=f"qdel{q['id']}", width="stretch", disabled=not can_edit):
                api.delete(f"/x/questions/{q['id']}")
                st.rerun()
    if not qs:
        ui.html_block('<div class="emptycol">No screening questions yet. Add one below, or use a suggestion.</div>')
    if not can_edit:
        return
    sug = ui.safe(api.get, f"/x/jobs/{job_id}/questions/suggest") or []
    if sug:
        st.markdown("**Suggested from this job**")
        for i, q in enumerate(sug):
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.markdown(f'<span class="small">{ui.esc(q["question"])}</span>', unsafe_allow_html=True)
            if b.button("Add", key=f"qs{job_id}{i}", width="stretch"):
                api.post(f"/x/jobs/{job_id}/questions", json=q)
                st.rerun()
    with st.form(f"qadd{job_id}", clear_on_submit=True):
        st.markdown("**Write your own**")
        q = st.text_input("Question", placeholder="e.g. Do you have a two-wheeler licence?")
        a, b, c = st.columns([1, 1, 1])
        kind = a.selectbox("Answer type", list(kinds), format_func=kinds.get)
        ideal = b.text_input("Looking for", placeholder="Yes, or >= 2")
        ko = c.checkbox("Must (flag if different)")
        if st.form_submit_button("Add question", type="primary"):
            ui.safe(api.post, f"/x/jobs/{job_id}/questions", json={"question": q, "kind": kind, "ideal": ideal,
                                                                     "knockout": ko})
            st.rerun()


def board(ranked: list[dict], job_id: int, can_edit: bool) -> None:
    """Pipeline board: one column per stage, move people with the arrow."""
    cols = st.columns(len(ui.FLOW), gap="small")
    ko = {int(k): v for k, v in (ui.safe(api.get, f"/x/jobs/{job_id}/knockouts") or {}).items()}
    for col, stg in zip(cols, ui.FLOW):
        people = [r for r in ranked if r["stage"] == stg]
        with col:
            ui.html_block(f'<div class="bhead"><span>{ui.LABEL[stg]}</span><b>{len(people)}</b></div>')
            if not people:
                ui.html_block('<div class="bempty">Nobody here</div>')
            for r in people:
                nm = ui.name(r["name"], r["candidate_id"])
                with st.container(border=True, key=f"bcard{r['application_id']}"):
                    flag = (f'<br><span class="pill" style="background:#FFE8D6;color:#9A3412">{ko[r["candidate_id"]]} '
                            'answer to check</span>' if r["candidate_id"] in ko else "")
                    ui.html_block(f'<b class="small">{ui.esc(nm)}</b><br>{ui.score_chip(r["score"])}{flag}')
                    a, b = st.columns(2, gap="small")
                    if a.button("Open", key=f"bo{r['application_id']}", width="stretch", type="tertiary"):
                        ui.open_candidate(r["candidate_id"], job_id)
                    i = ui.FLOW.index(stg)
                    if i < len(ui.FLOW) - 1 and stg != "Interview" and b.button(
                            "→", key=f"bm{r['application_id']}", width="stretch", disabled=not can_edit,
                            help=f"Move to {ui.LABEL[ui.FLOW[i + 1]]}"):
                        ui.move(r["application_id"], ui.FLOW[i + 1], r["name"], r["candidate_id"])
                        st.rerun()
    rej = [r for r in ranked if r["stage"] == "Rejected"]
    if rej:
        st.caption("Not selected: " + ", ".join(ui.name(r["name"], r["candidate_id"]) for r in rej))


def offer_panel(m: dict, c: dict, job_id: int, can_edit: bool) -> None:
    if not m.get("application_id"):
        st.info("Add this candidate to the job first.")
        return
    offers = ui.safe(api.get, "/x/offers", application_id=m["application_id"]) or []
    o = offers[0] if offers else None
    left, right = st.columns([1, 1.4], gap="large")
    with left:
        st.markdown("### Offer details")
        if m["stage"] not in ("Interview", "Selected") and not o:
            ui.html_block('<div class="flag info">Offers open once the person has had an interview.</div>')
        status = (o or {}).get("status")
        if status and status != "Draft":
            tone = {"Accepted": "okbox", "Declined": "warnbox"}.get(status, "note")
            ui.html_block(f'<div class="{tone}">Offer {status.lower()}'
                          + (f' on {ui.fmt_ts(o["responded_at"])}' if o.get("responded_at") else
                             f' on {ui.fmt_ts(o["sent_at"])}. Waiting for {ui.esc(c["name"].split()[0])} to answer.')
                          + (f' · "{ui.esc(o["candidate_note"])}"' if o.get("candidate_note") else "") + "</div>")
        if can_edit and status in (None, "Draft", "Declined") and m["stage"] in ("Interview", "Selected"):
            from datetime import date, timedelta
            with st.form("offer"):
                desig = st.text_input("Job title on the letter", (o or {}).get("designation") or "")
                a, b = st.columns(2)
                ctc = a.number_input("Yearly CTC (₹)", 60000, 5000000, int((o or {}).get("ctc") or 300000), 6000)
                jd = b.date_input("Joining date", date.fromisoformat(o["joining_date"]) if o else
                                  date.today() + timedelta(days=15))
                rep = a.text_input("Reports to", (o or {}).get("reporting_to") or "Store Manager")
                prob = b.number_input("Probation (months)", 0, 12, int((o or {}).get("probation_months") or 6))
                if st.form_submit_button("Write offer letter", type="primary", icon=":material/auto_awesome:"):
                    r = ui.safe(api.post, "/x/offers", json={"application_id": m["application_id"], "ctc": int(ctc),
                                                             "joining_date": str(jd), "designation": desig or None,
                                                             "reporting_to": rep, "probation_months": int(prob)})
                    if r:
                        ui.toast_next("Offer letter drafted. Read it, then press Send offer.")
                        st.rerun()
            st.caption("The numbers come only from this form. AI may reword the letter but never changes a figure.")
    with right:
        st.markdown("### Letter")
        if not o:
            ui.html_block('<div class="emptycol">Fill in the details and press <b>Write offer letter</b>.</div>')
            return
        if o["status"] == "Draft" and can_edit:
            txt = st.text_area("Offer letter", o["letter"], height=420, label_visibility="collapsed")
            a, b, c_ = st.columns(3)
            if a.button("Save", width="stretch"):
                ui.safe(api.patch, f"/x/offers/{o['id']}", json={"letter": txt})
                ui.toast_next("Saved")
                st.rerun()
            b.download_button("Word file", api.get(f"/x/offers/{o['id']}/docx"), file_name=f"Offer - {c['name']}.docx",
                              width="stretch", icon=":material/download:")
            if c_.button("Send offer", type="primary", width="stretch", icon=":material/send:"):
                ui.safe(api.patch, f"/x/offers/{o['id']}", json={"letter": txt})
                ui.safe(api.post, f"/x/offers/{o['id']}/send")
                ui.toast_next(f"Offer sent. {c['name'].split()[0]} can accept or decline it in the portal.")
                st.rerun()
        else:
            ui.html_block(f'<div class="resume">{ui.esc(o["letter"])}</div>')
            st.download_button("Download Word file", api.get(f"/x/offers/{o['id']}/docx"),
                               file_name=f"Offer - {c['name']}.docx", icon=":material/download:")
