"""HireMate Plus: everything beyond the 5 core features, on one page in 5 sections."""
import altair as alt
import pandas as pd
import streamlit as st

import api
import ui
from plus import plus_ui as pu

u = st.session_state.user
rec = u["role"] in ("Admin", "Recruiter")
jobs = ui.safe(api.get, "/jobs") or []
JOBS = {j["id"]: j["title"] for j in jobs}

ui.header("HireMate Plus", sub="Smart extras on top of the core: spot risks early, find hidden talent, and save time "
                               "in interviews and messages.")
SECTIONS = ["Today", "Talent pool", "Interviews", "Messages", "Decisions & team"]
sec = st.segmented_control("Section", SECTIONS, default="Today", key="plussec", label_visibility="collapsed") or "Today"


def job_pick(key: str, label: str = "Job") -> int | None:
    if not jobs:
        st.info("No jobs yet.")
        return None
    return st.selectbox(label, list(JOBS), format_func=JOBS.get, key=key)


def cand_pick(job_id: int, key: str) -> int | None:
    ranked = ui.safe(api.get, f"/match/job/{job_id}") or []
    if not ranked:
        st.caption("No candidates in this job yet.")
        return None
    names = {r["candidate_id"]: ui.name(r["name"], r["candidate_id"]) for r in ranked}
    return st.selectbox("Candidate", list(names), format_func=names.get, key=key)


# ====================================================================== TODAY
if sec == "Today":
    b = ui.safe(api.get, "/plus/briefing")
    if b:
        with st.container(border=True):
            st.markdown(f"{pu.plus_badge()} **9 AM briefing**", unsafe_allow_html=True)
            st.markdown(b["text"])
    left, right = st.columns([1.15, 1], gap="medium")
    with left:
        with st.container(border=True):
            pu.section("Might drop out", "People who may disappear, why, and what to send them. Worked out from replies, "
                                         "waiting time, commute, salary and interview confirmations.")
            risks = [r for r in (ui.safe(api.get, "/plus/dropout") or []) if r["level"] != "Low"]
            if not risks:
                ui.html_block('<div class="okbox">Nobody looks at risk right now.</div>')
            for r in risks:
                fg, bg = pu.LEVEL[r["level"]]
                a, c = st.columns([4, 1.2], vertical_alignment="center")
                a.markdown(f'{ui.avatar(r["name"], size=30)} <b>{ui.esc(ui.name(r["name"], r["candidate_id"]))}</b> · '
                           f'{ui.esc(r["job"])} {pu.chip(r["level"] + " " + str(r["risk"]), fg, bg)}<br>'
                           f'<span class="small muted">{ui.esc(" · ".join(x["reason"] for x in r["reasons"]))}</span><br>'
                           f'<span class="small"><b>Do:</b> {ui.esc(r["next"])}</span>', unsafe_allow_html=True)
                if c.button("Open", key=f"dr{r['application_id']}", width="stretch"):
                    st.session_state["cand_tab"] = "Insights"
                    ui.open_candidate(r["candidate_id"], r["job_id"])
        with st.container(border=True):
            pu.section("Offer at risk", "Hesitation spotted in candidate messages.")
            ofr = ui.safe(api.get, "/plus/offer-risk") or []
            if not ofr:
                ui.html_block('<div class="okbox">No worrying messages.</div>')
            for o in ofr:
                ui.html_block(f'<div class="flag"><b>{ui.esc(ui.name(o["name"], o["candidate_id"]))}</b> ({ui.esc(o["job"])}): '
                              f'"{ui.esc(o["quote"])}"<br><span class="small">{ui.esc(o["action"])}</span></div>')
    with right:
        with st.container(border=True):
            pu.section("Better fit elsewhere", "Weak for the job they applied to, strong for another open job.")
            bf = ui.safe(api.get, "/plus/best-fit") or []
            if not bf:
                ui.html_block('<div class="okbox">Everyone is in their best-fitting job.</div>')
            for e in bf:
                a, c = st.columns([4, 1.3], vertical_alignment="center")
                a.markdown(f'<b>{ui.esc(ui.name(e["name"], e["candidate_id"]))}</b><br><span class="small">'
                           f'{ui.esc(e["from_job"])} {ui.score_chip(e["from_score"])} → {ui.esc(e["to_job"])} '
                           f'{ui.score_chip(e["to_score"])}</span>', unsafe_allow_html=True)
                if c.button("Add", key=f"bfm{e['candidate_id']}", type="primary", width="stretch", disabled=not rec):
                    api.post("/plus/best-fit/move", json={"job_id": e["to_job_id"], "candidate_id": e["candidate_id"]})
                    ui.toast_next(f"Added {e['name']} to {e['to_job']}")
                    st.rerun()
        with st.container(border=True):
            pu.section("Hidden gems", "Lower match score, but strong signs: results in numbers, promotions, awards, long stays.")
            gems = ui.safe(api.get, "/plus/hidden-gems") or []
            if not gems:
                st.caption("None found.")
            for g in gems:
                ui.html_block(f'<b>{ui.esc(ui.name(g["name"], g["candidate_id"]))}</b> · {ui.esc(g["job"])} '
                              f'{ui.score_chip(g["score"])}' + "".join(f'<div class="small">✦ {ui.esc(s)}</div>' for s in g["signals"]))
                if st.button("Take another look", key=f"gem{g['candidate_id']}"):
                    st.session_state["cand_tab"] = "Insights"
                    ui.open_candidate(g["candidate_id"], g["job_id"])

# ====================================================================== TALENT POOL
if sec == "Talent pool":
    with st.container(border=True):
        pu.section("Talent pool health", "For each open job: people already in the pipeline, and ready-to-hire people in the pool.")
        ph = ui.safe(api.get, "/plus/pool-health") or []
        cols = st.columns(len(ph) or 1)
        for col, h in zip(cols, ph):
            tone = {"healthy": ("#0A5A43", "#DDF1E8"), "thin": ("#7A4D00", "#FFF1BF"), "empty": ("#B42318", "#FDE6E3")}[h["status"]]
            col.markdown(f'<b>{ui.esc(h["job"])}</b><br>{pu.chip(h["status"].title(), *tone)}<br>'
                         f'<span class="small">{h["in_pipeline"]} in pipeline · {h["ready_in_pool"]} ready · '
                         f'{h["near_in_pool"]} close in the pool</span>', unsafe_allow_html=True)
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            pu.section("Skill demand board", "Skills your open jobs need vs how many people in the pool prove them.")
            sd = ui.safe(api.get, "/plus/skill-demand") or []
            if sd:
                df = pd.DataFrame(sd)
                st.altair_chart(alt.Chart(df).mark_bar(cornerRadius=3).encode(
                    y=alt.Y("skill:N", sort=alt.EncodingSortField("pct"), title=None),
                    x=alt.X("pct:Q", title="% of pool who prove it", scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color("gap:N", scale=alt.Scale(domain=["short", "ok"], range=["#B42318", "#0E7A5C"]),
                                    legend=None), tooltip=["skill", "jobs_need", "people_prove", "pct"]
                ).properties(height=28 * len(df) + 20), width="stretch")
                st.caption("Red = fewer than 1 in 4 people prove it. Post wider, or plan training.")
        with st.container(border=True):
            pu.section("JD reality check", "Is the job asking for things the market doesn't have?")
            jid = job_pick("jdr")
            if jid:
                r = api.get(f"/plus/jd-reality/{jid}")
                for s in r["skills"]:
                    tone = {"rare": ("#B42318", "#FDE6E3"), "ok": ("#7A4D00", "#FFF1BF"), "common": ("#0A5A43", "#DDF1E8")}[s["level"]]
                    ui.html_block(f'<div class="small">{ui.esc(s["skill"])} {pu.chip(str(s["pct"]) + "% prove it", *tone)}</div>')
                for a in r["advice"]:
                    ui.html_block(f'<div class="note" style="margin-top:.3rem">{ui.esc(a)}</div>')
    with right:
        with st.container(border=True):
            pu.section("Re-engage silver list", "This month's 5 past candidates worth contacting again, with a message.")
            for s in ui.safe(api.get, "/plus/silver") or []:
                with st.expander(f"{ui.name(s['name'], s['candidate_id'])} · {s['job']} · {s['score']}%"):
                    st.text_area("Message", s["message"], height=100, key=f"sil{s['candidate_id']}")
        with st.container(border=True):
            pu.section("Bring back past runners-up", "For a job: strong people from other jobs or the pool.")
            jid = job_pick("ru", "Job to fill")
            if jid:
                ru = ui.safe(api.get, f"/plus/runners-up/{jid}") or []
                if not ru:
                    st.caption("Nobody new scores 60%+ for this job.")
                pick = []
                for r in ru:
                    if st.checkbox(f"{ui.name(r['name'], r['candidate_id'])} · {r['score']}% · {r['why']}", key=f"ru{jid}{r['candidate_id']}"):
                        pick.append(r["candidate_id"])
                if ru and st.button(f"Add {len(pick)} and draft invites", type="primary", disabled=not pick or not rec):
                    res = api.post(f"/plus/runners-up/{jid}/invite", json={"candidate_ids": pick})
                    ui.toast_next(res["text"])
                    st.rerun()
        with st.container(border=True):
            pu.section("Duplicate profiles", "Same person, different email or phone.")
            dd = ui.safe(api.get, "/plus/duplicates") or []
            if not dd:
                ui.html_block('<div class="okbox">No duplicates found.</div>')
            for d in dd:
                ui.html_block(f'<b>{ui.esc(d["keep"])}</b> (#{d["keep_id"]}, {ui.esc(d["keep_email"] or "no email")}) and '
                              f'<b>{ui.esc(d["dup"])}</b> (#{d["dup_id"]}, {ui.esc(d["dup_email"] or "no email")})<br>'
                              f'<span class="small muted">{ui.esc(", ".join(d["why"]))} · CV text {d["cv_similarity"]}% alike</span>')
                if st.button(f"Merge #{d['dup_id']} into #{d['keep_id']}", key=f"mg{d['dup_id']}", disabled=not rec):
                    r = ui.safe(api.post, "/plus/duplicates/merge", json={"keep_id": d["keep_id"], "dup_id": d["dup_id"]})
                    if r:
                        ui.toast_next(f"Merged into {r['kept']}")
                        st.rerun()

# ====================================================================== INTERVIEWS
if sec == "Interviews":
    a, b = st.columns(2)
    with a:
        jid = job_pick("ivj")
    with b:
        cid = cand_pick(jid, "ivc") if jid else None
    if jid and cid:
        left, right = st.columns([1.1, 1], gap="medium")
        with left:
            with st.container(border=True):
                pu.section("Live interview helper", "Tick questions as you ask them, jot notes. HireMate suggests what to ask next.")
                bank = api.get(f"/plus/bank/{jid}")
                asked = []
                for q in bank[:8]:
                    if st.checkbox(q["question"], key=f"lv{cid}{q['id']}"):
                        asked.append(q["question"])
                notes = st.text_area("Your notes", key=f"lvn{cid}", height=120,
                                     placeholder="Quick on POS billing. Cash handling good. Nervous with the angry-customer role-play.")
                if st.button("What should I ask next?", icon=":material/lightbulb:"):
                    nq = api.post("/plus/next-question", json={"job_id": jid, "candidate_id": cid, "asked": asked, "notes": notes})
                    ui.html_block(f'<div class="note"><b>{ui.esc(nq["question"])}</b><br><span class="small">{ui.esc(nq["why"])}</span></div>')
            with st.container(border=True):
                pu.section("Notes → scorecard", "Paste rough notes. Ratings come with the line they're based on.")
                n2 = st.text_area("Interview notes", st.session_state.get(f"lvn{cid}", ""), key=f"n2s{cid}", height=110)
                if st.button("Make scorecard", type="primary", disabled=len(n2.strip()) < 10):
                    st.session_state[f"card{cid}"] = api.post("/plus/notes-to-scorecard", json={"job_id": jid, "candidate_id": cid, "notes": n2})
                card = st.session_state.get(f"card{cid}")
                if card:
                    for r in card["rows"]:
                        ui.html_block(f'<div class="qa"><b style="width:2.2rem">{r["rating"] or "–"}/5</b><div><b class="small">'
                                      f'{ui.esc(r["skill"])}</b><br><span class="small muted">{ui.esc(r["reason"])}</span></div></div>')
                    if st.button("Save as interview feedback", disabled=not any(r.get("rating") for r in card["rows"])):
                        api.post("/plus/scorecard/save", json={"job_id": jid, "candidate_id": cid, "notes": n2, "rows": card["rows"]})
                        ui.toast_next("Saved as feedback")
                        st.rerun()
        with right:
            with st.container(border=True):
                pu.section("Role-play scenarios", "Realistic store situations to act out, with what good looks like.")
                for r in api.get(f"/plus/roleplay/{jid}"):
                    with st.expander(f"{r['skill']}: {r['scenario'][:55]}…"):
                        st.markdown(f"**Scenario:** {r['scenario']}")
                        st.markdown(f"**Good answer:** {r['good']}")
                        st.markdown(f"**Red flags:** {r['red_flags']}")
            with st.container(border=True):
                pu.section("Question bank that learns", "Vote on questions after interviews. The best rise to the top for this role.")
                for q in api.get(f"/plus/bank/{jid}"):
                    x, y, z = st.columns([6, .8, .8], vertical_alignment="center")
                    x.markdown(f'<span class="small">{ui.esc(q["question"])}</span> '
                               f'{pu.chip(("+" if q["net"] >= 0 else "") + str(q["net"]), "#2B2350", "#E7E3F6")}',
                               unsafe_allow_html=True)
                    if y.button("👍", key=f"up{q['id']}"):
                        api.post(f"/plus/bank/vote/{q['id']}", json={"useful": True})
                        st.rerun()
                    if z.button("👎", key=f"dn{q['id']}"):
                        api.post(f"/plus/bank/vote/{q['id']}", json={"useful": False})
                        st.rerun()
                c1, c2 = st.columns([3, 1.4], vertical_alignment="bottom")
                newq = c1.text_input("Add your own question", key=f"bq{jid}")
                if c2.button("Add", width="stretch", disabled=len(newq) < 8):
                    api.post(f"/plus/bank/{jid}", json={"question": newq})
                    st.rerun()
                if st.button("Add this candidate's AI questions to the bank"):
                    api.post(f"/plus/bank/{jid}/import/{cid}")
                    st.rerun()

# ====================================================================== MESSAGES
if sec == "Messages":
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            pu.section("Answer candidate questions from policy", "Replies drafted only from your policy documents, with the source.")
            inbox = [e for e in (ui.safe(api.get, "/emails/inbox/list", all="true") or []) if "?" in (e["body"] or "")]
            if not inbox:
                st.caption("No questions from candidates.")
            for e in inbox[:5]:
                with st.expander(f"{ui.name(e['candidate'], e['candidate_id'])}: {e['body'][:70]}…"):
                    st.write(e["body"])
                    if st.button("Answer from policy", key=f"pa{e['id']}"):
                        st.session_state[f"pa{e['id']}"] = api.post(f"/plus/policy-answer/{e['id']}")
                    r = st.session_state.get(f"pa{e['id']}")
                    if r:
                        st.text_area("Reply", r["text"], height=200, key=f"pat{e['id']}")
                        st.caption("Sources: " + (", ".join(r["sources"]) or "none found. HR should check."))
                        if st.button("Save as draft reply", key=f"pad{e['id']}", disabled=not rec):
                            api.post(f"/plus/policy-answer/{e['id']}?draft=true")
                            ui.toast_next("Draft saved. Open the candidate's Emails tab to send it.")
                            st.rerun()
        with st.container(border=True):
            pu.section("Tone switch", "Change any draft to formal, warm, short, Hindi or Hinglish in one click.")
            drafts = [e for e in (ui.safe(api.get, "/emails", status="Draft") or []) if e.get("direction", "out") == "out"]
            if not drafts:
                st.caption("No drafts right now. Drafts appear when you book, hire or write an email.")
            else:
                dm = {e["id"]: f"{ui.name(e['candidate'], e['candidate_id'])} · {e['type_label']}" for e in drafts}
                eid = st.selectbox("Draft", list(dm), format_func=dm.get)
                cur = next(e for e in drafts if e["id"] == eid)
                tone = st.segmented_control("Tone", ["Formal", "Warm", "Short", "Hindi", "Hinglish"], key="tone")
                if tone and st.button(f"Rewrite as {tone}", type="primary", disabled=not rec):
                    ui.safe(api.post, f"/plus/tone/{eid}", json={"tone": tone})
                    st.rerun()
                st.text_area("Current text", cur["body"], height=200, disabled=True, key=f"tt{eid}")
    with right:
        with st.container(border=True):
            pu.section("Bulk update, personal touch", "One update to everyone at a stage, but each mentions their own strength.")
            jid = job_pick("bj")
            stg = st.selectbox("Stage", ui.FLOW, format_func=ui.LABEL.get, key="bs")
            if jid:
                pv = api.get(f"/plus/bulk/{jid}", stage=stg)
                st.caption(f"{len(pv)} people")
                for p in pv[:3]:
                    with st.expander(f"Preview: {ui.name(p['name'], p['candidate_id'])}"):
                        st.text(p["body"])
                if st.button(f"Make {len(pv)} drafts", type="primary", disabled=not pv or not rec):
                    ui.toast_next(api.post(f"/plus/bulk/{jid}?stage={stg}")["text"])
                    st.rerun()
        with st.container(border=True):
            pu.section("Job post writer", "One job, four ready-to-paste posts.")
            jid = job_pick("jp")
            if jid:
                b1, b2 = st.columns(2)
                band = api.get(f"/plus/pay-band/{jid}")
                lo = b1.number_input("Pay from (₹ a month)", 5000, 300000, band["min"], 1000, key=f"lo{jid}")
                hi = b2.number_input("Pay to (₹ a month)", 5000, 300000, band["max"], 1000, key=f"hi{jid}")
                if (lo, hi) != (band["min"], band["max"]) and st.button("Save pay band", disabled=not rec):
                    ui.safe(api.put, f"/plus/pay-band/{jid}", json={"min": int(lo), "max": int(hi)})
                    st.rerun()
                posts = api.get(f"/plus/job-posts/{jid}")["posts"]
                for site, tab in zip(posts, st.tabs(list(posts))):
                    with tab:
                        st.code(posts[site], language=None, wrap_lines=True)
                st.caption("Use the copy icon on each post. The pay band is also used for Salary fit.")

# ====================================================================== DECISIONS & TEAM
if sec == "Decisions & team":
    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True):
            pu.section("Decision journal", "One line on why, for every decision. Good for audits and for learning what works.")
            jr = api.get("/plus/journal")
            for m in jr["missing"]:
                ui.html_block(f'<div class="flag">No reason written: <b>{ui.esc(ui.name(m["name"], m["candidate_id"]))}</b> · '
                              f'{ui.esc(m["title"])} · {ui.esc(ui.LABEL.get(m["stage"], m["stage"]))}</div>')
                if st.button("Write the reason", key=f"jm{m['application_id']}"):
                    st.session_state["cand_tab"] = "Insights"
                    ui.open_candidate(m["candidate_id"], m["job_id"])
            for e in jr["entries"]:
                ui.html_block(f'<div class="qa"><b class="small" style="width:5rem">{ui.esc(e["decision"])}</b><div>'
                              f'<b class="small">{ui.esc(ui.name(e["name"], e["candidate_id"]))}</b> · '
                              f'<span class="small muted">{ui.esc(e["title"])}</span><br><span class="small">{ui.esc(e["reason"])}</span>'
                              f'<br><span class="small muted">{ui.esc(e["by_name"])} · {ui.fmt_ts(e["created_at"])}</span></div></div>')
        with st.container(border=True):
            pu.section("Recruiter performance")
            rp = ui.safe(api.get, "/plus/recruiters") or []
            if rp:
                df = pd.DataFrame(rp).rename(columns={"recruiter": "Recruiter", "cvs_reviewed": "CVs reviewed",
                                                      "interviews_booked": "Interviews booked", "emails_sent": "Emails sent",
                                                      "hires": "Hires", "avg_days_to_hire": "Avg days to hire",
                                                      "actions": "All actions"})
                st.dataframe(df.fillna("—"), hide_index=True, width="stretch")
        with st.container(border=True):
            pu.section("Joining documents", "After an offer is accepted, candidates upload documents in the portal.")
            jo = ui.safe(api.get, "/plus/joining") or []
            if not jo:
                st.caption("No accepted offers yet.")
            for j in jo:
                st.markdown(f"**{ui.name(j['name'], None)}** · {j['title']} · joining {ui.fmt_date(j['joining_date'])} · "
                            f"{j['done']}/{j['total']} checked" + (" ✅ ready" if j["ready"] else ""))
                for it in j["items"]:
                    a, b = st.columns([4, 1.4], vertical_alignment="center")
                    a.markdown(f"{'✅' if it['verified'] else '📄' if it['uploaded'] else '⬜'} {it['doc']}")
                    if it["uploaded"] and not it["verified"] and b.button("Mark checked", key=f"jv{j['application_id']}{it['doc']}",
                                                                           disabled=not rec):
                        api.post(f"/plus/joining/{j['application_id']}/verify?doc={it['doc']}")
                        st.rerun()
    with right:
        with st.container(border=True):
            pu.section("Blind first look", "Hide names, contact details and anything that hints at gender or age until "
                                           "someone marks a candidate 'interested'.")
            bfs = api.get("/plus/blind-first")
            on = st.toggle("Blind first look", value=bfs["on"], disabled=not rec)
            if on != bfs["on"]:
                api.put("/plus/blind-first", json={"on": on})
                pu._blind_state.clear()
                st.rerun()
            st.caption(f"{len(bfs['revealed'])} people marked interested so far.")
        with st.container(border=True):
            pu.section("Second opinion", "Before a final call, HireMate argues the other side, from the data only.")
            jid = job_pick("soj")
            cid = cand_pick(jid, "soc") if jid else None
            if cid and st.button("Get a second opinion", icon=":material/balance:"):
                so = api.get("/plus/second-opinion", job_id=jid, candidate_id=cid)
                st.markdown(f"**{so['side']}**")
                st.markdown(so["text"] or "\n".join(f"- {x}" for x in so["points"]))
        with st.container(border=True):
            pu.section("Hindi CV reading", "Paste or upload a CV written in Hindi. HireMate converts it and matches it like any other.")
            f = st.file_uploader("Hindi CV (PDF, Word or text)", type=["pdf", "docx", "txt"], key="hicv")
            txt = st.text_area("…or paste it", key="hitxt", height=120,
                               placeholder="नाम: रमेश यादव\nशहर: नोएडा\nअनुभव:\nकैशियर | न्यू मार्ट, नोएडा | जनवरी 2021 से वर्तमान")
            if st.button("Read Hindi CV", disabled=not (f or txt.strip())):
                st.session_state["hiprev"] = api.post("/plus/hindi-cv/preview", data={"text": txt} if not f else None,
                                                      files={"file": (f.name, f.getvalue())} if f else None)
            hp = st.session_state.get("hiprev")
            if hp:
                st.text_area("English version (edit if needed)", hp["text"], height=180, key="hien")
                tj = st.selectbox("Add to job", [None] + list(JOBS), format_func=lambda i: "Talent pool only" if i is None else JOBS[i])
                if st.button("Add candidate", type="primary", disabled=not rec):
                    r = ui.safe(api.post, "/plus/hindi-cv", json={"text": st.session_state["hien"],
                                                                  "job_id": tj})
                    if r:
                        st.session_state.pop("hiprev", None)
                        ui.toast_next(f"Added {r['candidate']['name']}")
                        st.rerun()
