import streamlit as st

import api
import ui
import widgets

rec = st.session_state.user["role"] in ("Admin", "Recruiter")
jobs = api.get("/jobs")
h1, h2 = st.columns([4, 1.2], vertical_alignment="center")
with h1:
    ui.header("Candidates", sub="Everyone who sent a CV, for all jobs.")
ui.ai_note("candidates")
if h2.button("Add CVs", icon=":material/add:", type="primary", width="stretch", disabled=not rec):
    widgets.upload_cvs()

a, b = st.columns([3, 1.4], vertical_alignment="bottom")
q = a.text_input("Search", placeholder="Search by name, role or any word in the CV", label_visibility="collapsed")
skill = b.text_input("Skill", placeholder="Has skill, e.g. Excel", label_visibility="collapsed")
more = st.toggle("More filters")
city = job = stage = edu = None
min_years = None
if more:
    f1, f2, f3, f4, f5 = st.columns(5)
    city = f1.text_input("City") or None
    jm = {"Any job": None} | {j["title"]: j["id"] for j in jobs}
    job = jm[f2.selectbox("Job", list(jm))]
    stage = f3.selectbox("Stage", ["Any", *ui.STAGES], format_func=lambda x: ui.LABEL.get(x, x))
    stage = None if stage == "Any" else stage
    min_years = f4.number_input("Min years", 0.0, 30.0, 0.0, 0.5) or None
    edu = f5.selectbox("Education", ["Any", "Postgraduate", "Graduate", "Diploma", "Class 12", "Other"])
    edu = None if edu == "Any" else edu

cs = ui.safe(api.get, "/candidates", q=q, skill=skill, city=city, job_id=job, stage=stage, min_years=min_years,
             edu_level=edu) or []
st.caption(f"{len(cs)} candidate{'s' if len(cs) != 1 else ''}")
if not cs:
    ui.html_block('<div class="emptycol">No one matches. Try another word, or click <b>Add CVs</b>.</div>')
for x in cs[:60]:
    nm = ui.name(x["name"], x["id"])
    with st.container(border=True):
        l, m_, r = st.columns([3.2, 3, 0.9], vertical_alignment="center")
        l.markdown(f'<div class="prow">{ui.avatar(nm, size=40)}<div><span class="pname">{ui.esc(nm)}</span><br>'
                   f'<span class="muted small">{ui.esc(x["headline"])} · {ui.esc(x["location"])} · {x["years"]:g} yrs</span>'
                   f'</div></div>', unsafe_allow_html=True)
        m_.markdown(" ".join(f'<span class="small">{ui.esc(a["job_title"].split(" /")[0])}</span> {ui.stage_pill(a["stage"])}'
                             for a in x["applications"]) or '<span class="muted small">Not in any job yet</span>',
                    unsafe_allow_html=True)
        if r.button("View", key=f"c{x['id']}", width="stretch"):
            ui.open_candidate(x["id"], x["applications"][0]["job_id"] if x["applications"] else None)
