"""Quick review: go through new CVs one at a time. Shortlist / Maybe later / Not selected."""
import streamlit as st

import api
import ui

jid = st.session_state.get("job_id")
if not jid:
    st.info("Open a job first, then click Start quick review.")
    st.stop()
job = api.get(f"/jobs/{jid}")
rec = st.session_state.user["role"] in ("Admin", "Recruiter")
st.session_state.view_ctx = {"job_id": jid}

# fix the queue when the review starts, so moving people doesn't reshuffle it
qkey = f"rvq{jid}"
if qkey not in st.session_state or st.session_state.pop("rv_restart", False) or st.session_state.get("rv_start"):
    ranked = api.get(f"/match/job/{jid}")
    q = [r["candidate_id"] for r in ranked if r["stage"] in ("Applied", "Screening")]
    first = st.session_state.pop("rv_start", None)
    if first in q:  # start from the person the recruiter clicked
        q.remove(first)
        q.insert(0, first)
    st.session_state[qkey] = q
    st.session_state[f"rvdone{jid}"] = {}
queue = st.session_state[qkey]
done = st.session_state[f"rvdone{jid}"]
left = [c for c in queue if c not in done]

if st.button(f"← {job['title']}", type="tertiary"):
    ui.open_job(jid)

# ------------------------------------------------------------ finished
if not left:
    ui.header("Review done", sub=job["title"])
    n = lambda k: sum(v == k for v in done.values())  # noqa: E731
    with st.container(border=True):
        if not queue:
            st.markdown("Nobody is waiting for review on this job.")
        else:
            ui.html_block(f'<div class="okbox" style="font-size:1rem">You reviewed {len(done)} '
                          f'{"person" if len(done) == 1 else "people"}: {n("Shortlisted")} shortlisted · '
                          f'{n("Screening")} maybe later · {n("Rejected")} not selected.</div>')
            if n("Rejected"):
                st.markdown(f"{n('Rejected')} polite 'not selected' email(s) are drafted. They are **not sent** "
                            "until you press Send on Home.")
        a, b, c = st.columns(3)
        if a.button("Book interviews", type="primary", width="stretch", disabled=not n("Shortlisted")):
            ui.open_job(jid)
        if b.button("Send emails", width="stretch"):
            ui.go("dashboard")
        if c.button("Review again", width="stretch"):
            st.session_state["rv_restart"] = True
            st.rerun()
    st.stop()

# ------------------------------------------------------------ one person
cid = left[0]
pos = len(done) + 1
m = api.get(f"/match/job/{jid}/candidate/{cid}")
c = api.get(f"/candidates/{cid}")
flags = api.get(f"/smart/flags/{cid}", job_id=jid)
nm = ui.name(c["name"], cid)

h1, h2 = st.columns([4, 1.4], vertical_alignment="center")
with h1:
    ui.header("Quick review", sub=f"{job['title']} · person {pos} of {len(queue)}")
h2.progress(len(done) / max(1, len(queue)), text=f"{len(done)} done")

with st.container(border=True):
    sub = " · ".join(v for v in [c["headline"], c["location"], f'{c["years"]:g} years', c["education"]] if v)
    ui.html_block(f'<div class="prow">{ui.avatar(nm, m["score"], 60)}<div><span style="font-size:1.55rem;font-weight:700">'
                  f'{ui.esc(nm)}</span> &nbsp;{ui.score_chip(m["score"])}<br><span class="muted">{ui.esc(sub)}</span>'
                  f'</div></div>')
    ui.html_block(ui.has_missing(m["rows"]))
    l, r = st.columns([1.1, 1], gap="medium")
    with l:
        st.markdown("**Proof from the CV**")
        proof = [x for x in m["rows"] if x["status"] == "Proven" and x["evidence"]][:4]
        if not proof:
            st.markdown('<p class="muted small">No clear examples in the CV. Skills are only listed.</p>',
                        unsafe_allow_html=True)
        for x in proof:
            ui.html_block(f'<div class="ev"><b>{ui.esc(x["skill"])}</b>: "{ui.esc(x["evidence"][:150])}"</div>')
        if m.get("criteria"):
            st.markdown("**Your rules**")
            ui.html_block("".join(f'<div class="small">{"✓" if x["status"] == "met" else "✗" if x["status"] == "not met" else "½"} '
                                  f'{ui.esc(x["text"])}</div>' for x in m["criteria"]))
    with r:
        st.markdown("**Things to check**")
        ui.html_block(ui.flags_html(flags))
    with st.expander("Read the full CV"):
        ui.html_block(f'<div class="resume">{ui.highlight(c["cv_text"], [x["evidence"] for x in m["rows"] if x["status"] == "Proven"])}</div>')

    def act(stage: str):
        if m["stage"] != stage:
            ui.move(m["application_id"], stage, c["name"], cid)
        done[cid] = stage
        st.rerun()

    a, b, d = st.columns(3)
    if a.button("✗  Not selected", width="stretch", disabled=not rec, key=f"no{cid}"):
        act("Rejected")
    if b.button("Maybe later", width="stretch", disabled=not rec, key=f"mb{cid}"):
        act("Screening")
    if d.button("✓  Shortlist", type="primary", width="stretch", disabled=not rec, key=f"ok{cid}"):
        act("Shortlisted")
    st.caption("Nothing is sent to the candidate from here. 'Not selected' only drafts a polite email. You press Send.")
