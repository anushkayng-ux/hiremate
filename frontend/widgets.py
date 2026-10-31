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
    target = st.selectbox("Add to", list(opts), index=list(opts).index(pre))
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
                        added += bool(ui.safe(api.post, "/applications", json={"job_id": opts[target], "candidate_id": f}))
                        continue
                    res = ui.safe(api.post, "/candidates/upload", files=[("files", (f.name, f.getvalue()))],
                                  data={"allow_duplicate": str(dup).lower(), **({"job_id": opts[target]} if opts[target] else {})})
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
            tag = {"must": "#B91C1C", "bonus": "#1D4ED8", "penalty": "#D97706"}[r["kind"]]
            x.markdown(f'<span class="pill" style="background:#F1F5F9;color:{tag}">{KIND_LABEL[r["kind"]]}</span> '
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
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;color:#0F172A;max-width:820px;margin:32px auto;padding:0 20px}}
h1{{margin:0;font-size:24px}}.sub{{color:#475569;margin:4px 0 20px}}.c{{border:1px solid #E2E8F0;border-radius:12px;padding:14px 18px;margin:12px 0;break-inside:avoid}}
.h{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}.n{{font-weight:700;font-size:17px}}
.t{{background:#DCFCE7;color:#15803D;border-radius:99px;padding:2px 10px;font-size:13px;font-weight:600}}
.s{{background:#DBEAFE;color:#1E40AF;border-radius:99px;padding:2px 10px;font-size:13px;font-weight:600}}
.m{{color:#475569;font-size:14px;margin-top:4px}}p{{font-size:14px;margin:8px 0}}ul{{margin:4px 0 0 18px;font-size:13px;color:#334155}}
.f{{color:#64748B;font-size:12px;margin-top:24px}}</style></head><body>
<h1>Shortlist: {e(job['title'])}</h1><div class="sub">{e(job['location'])} · {job['min_years']:g}+ years · prepared {date.today():%d %b %Y} with HireMate</div>
{''.join(cards)}<div class="f">Synthetic demo data. Scores help you decide; the hiring team makes every decision.</div></body></html>"""
