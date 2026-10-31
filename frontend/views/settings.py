import streamlit as st

import api
import ui
import widgets

ui.header("Settings", sub="AI model, screening rules, documents and reports.")
_a, _b, _ = st.columns([1, 1, 2])
if _a.button("Documents & policies", icon=":material/menu_book:", width="stretch"):
    ui.go("knowledge")
if _b.button("Reports", icon=":material/insights:", width="stretch"):
    ui.go("analytics")
s = ui.safe(api.get, "/settings")
if not s:
    st.stop()
u = st.session_state.user
rec = u["role"] in ("Admin", "Recruiter")

# ------------------------------------------------------------ AI model (free by default, paid optional)
ai = api.get("/settings/ai")
admin = u["role"] == "Admin"
with st.container(border=True):
    top_l, top_r = st.columns([3, 1.2], vertical_alignment="center")
    top_l.markdown("**AI model**")
    ok = s["llm"]["connected"]
    top_r.markdown(f'<span class="pill" style="background:{"#DCFCE7" if ok else "#FEF3C7"};color:'
                   f'{"#1D4ED8" if ok else "#92400E"}">{"AI on" if ok else "Using templates"}</span>',
                   unsafe_allow_html=True)
    st.caption(f"Now: {s['llm']['provider']}. Scores never use AI. AI only writes summaries, questions, emails, JDs "
               "and answers. Without a key everything still works with templates.")
    plan = st.segmented_control("Plan", ["Free", "Paid"], default="Paid" if ai["plan"] == "paid" else "Free",
                                disabled=not admin, key="aiplan") or "Free"
    opts = {k: v for k, v in ai["providers"].items() if v["plan"] == plan.lower()}
    cur = ai["provider"] if ai["provider"] in opts else next(iter(opts))
    prov = st.radio("Model", list(opts), index=list(opts).index(cur), format_func=lambda k: opts[k]["label"],
                    horizontal=True, disabled=not admin)
    need = opts[prov]["key"]
    gkey = akey = ourl = None
    a, b = st.columns(2)
    if need == "gemini":
        gkey = a.text_input("Google AI Studio key", type="password", disabled=not admin,
                            placeholder=f"Saved: {ai['gemini_key']}" if ai["gemini_key"] else "Paste your key")
        a.caption("Free key: aistudio.google.com/apikey" if plan == "Free" else "Use a key with billing turned on.")
    elif need == "anthropic":
        akey = a.text_input("Anthropic key", type="password", disabled=not admin,
                            placeholder=f"Saved: {ai['anthropic_key']}" if ai["anthropic_key"] else "sk-ant-…")
        a.caption("Get one at console.anthropic.com. Paid per use.")
    elif prov == "ollama":
        ourl = a.text_input("Ollama address", ai["ollama_url"], disabled=not admin)
        a.caption("Install Ollama, then: ollama pull qwen2.5:7b-instruct")
    model = b.text_input("Model name", ai["model"] if prov == ai["provider"] else opts[prov]["default_model"],
                         disabled=not admin or prov == "template")
    if plan == "Paid":
        st.info("Paid models charge your own account each time the AI writes something. Free is enough for the demo.")
    if admin:
        x, y, z, _ = st.columns([1, 1.2, 1.3, 3])
        if x.button("Save", type="primary", width="stretch"):
            r = ui.safe(api.put, "/settings/ai", json={"provider": prov, "model": model, "gemini_key": gkey,
                                                       "anthropic_key": akey, "ollama_url": ourl})
            if r:
                st.session_state.ai_test = api.post("/settings/ai/test")
                st.rerun()
        if y.button("Test connection", width="stretch"):
            st.session_state.ai_test = api.post("/settings/ai/test")
        if z.button("Remove saved keys", width="stretch"):
            ui.safe(api.put, "/settings/ai", json={"provider": "gemini_free", "clear_keys": True})
            st.session_state.pop("ai_test", None)
            st.session_state.pop("aiplan", None)
            ui.toast_next("Keys removed. Back on the free plan.")
            st.rerun()
        t = st.session_state.get("ai_test")
        if t:
            (st.success if t["ok"] else st.warning)(t["message"])
        st.caption("Keys are saved on the server only. This page never shows them again, only the last 4 characters.")
    else:
        st.caption("Only an Admin can change the AI model.")


left, right = st.columns([1.2, 1], gap="large")
with left:
    with st.container(border=True):
        st.markdown("**Match score weights**")
        st.caption("Match = Skills + Text match + Experience. Changes re-rank every job.")
        w = s["weights"]
        with st.form("w"):
            sk = st.slider("Skills (must-haves count double)", 0, 100, w["skills"])
            tx = st.slider("Text match (meaning of the CV vs the JD)", 0, 100, w["text"])
            ex = st.slider("Experience (years vs years asked)", 0, 100, w["exp"])
            tot = sk + tx + ex or 1
            st.caption(f"Share: skills {round(sk / tot * 100)}% · text {round(tx / tot * 100)}% · "
                       f"experience {round(ex / tot * 100)}%")
            if st.form_submit_button("Save weights", type="primary", disabled=not rec):
                if ui.safe(api.put, "/settings/weights", json={"skills": sk, "text": tx, "exp": ex}):
                    ui.toast_next("Saved. All jobs re-ranked.")
                    st.rerun()
    with st.container(border=True):
        st.markdown("**Screening rules for all jobs**")
        st.caption("Rules here apply to every job. Add job-only rules on the job page → Criteria. "
                   "You can also tell Ask AI: \"Add rule for all jobs: must be Class 12 or above\".")
        widgets.criteria_editor(None, "gcrit", rec)
    with st.container(border=True):
        st.markdown("**Guidelines for the AI**")
        st.caption("Plain-English instructions the AI follows in summaries, questions, emails and answers. "
                   "Example: Always mention the store address in interview emails.")
        g = api.get("/settings/guidelines")["text"]
        with st.form("guide"):
            gt = st.text_area("Guidelines", g, height=110, label_visibility="collapsed",
                              placeholder="- Keep emails under 120 words\n- Ask every candidate about weekend availability")
            if st.form_submit_button("Save guidelines", disabled=not rec):
                api.put("/settings/guidelines", json={"text": gt})
                ui.toast_next("Guidelines saved")
                st.rerun()
    with st.container(border=True):
        st.markdown("**Fair review**")
        b = st.toggle("Blind review: hide names while screening", value=s["blind"], disabled=not rec)
        if b != s["blind"]:
            api.put("/settings/blind", on=str(b).lower())
            st.session_state.blind = b
            st.rerun()
        st.caption("Rules that are always on: AI never rejects on its own · every email needs a recruiter's approval · "
                   "employment gaps are never scored · JDs are checked for biased words.")

with right:
    with st.container(border=True):
        st.markdown("**Search**")
        ui.html_block(f'<span class="small">Embeddings: {ui.esc(s["embedder"])}<br>'
                      f'Vector store: {ui.esc(s["vector_store"])}</span>')
    with st.container(border=True):
        st.markdown("**Team & roles**")
        for x in api.get("/settings/users"):
            st.markdown(f"{x['name']} · <span class='muted small'>{x['email']} · {x['role']}</span>", unsafe_allow_html=True)
        if u["role"] == "Admin":
            with st.expander("Add a teammate"):
                with st.form("nu", clear_on_submit=True):
                    n = st.text_input("Name")
                    e = st.text_input("Email")
                    r = st.selectbox("Role", ["Recruiter", "Interviewer", "Admin"])
                    p = st.text_input("Temporary password", type="password")
                    if st.form_submit_button("Add"):
                        if ui.safe(api.post, "/settings/users", json={"name": n, "email": e, "role": r, "password": p}):
                            ui.toast_next(f"Added {n}")
                            st.rerun()
    with st.container(border=True):
        st.markdown("**Knowledge store**")
        if st.button("Open knowledge store"):
            ui.go("knowledge")
    if u["role"] == "Admin":
        with st.container(border=True):
            st.markdown("**Demo data**")
            if st.button("Reset to the sample data"):
                st.session_state.confirm_reset = True
            if st.session_state.get("confirm_reset"):
                st.warning("This deletes everything you added and reloads the 3 jobs and 7 CVs.")
                if st.button("Yes, reset", type="primary"):
                    api.post("/settings/reset-demo")
                    st.session_state.pop("confirm_reset")
                    ui.toast_next("Demo data reloaded")
                    st.rerun()

with st.expander("How matching works"):
    st.markdown("""
- **Skills**: each must-have counts double. A skill counts fully only if a real sentence in the CV proves it
  (**Proven**). If it only appears in the skills list, it counts half (**Listed**).
- **Text match**: how close the CV's meaning is to the JD (embeddings, or TF-IDF when offline).
- **Experience**: years from the CV's dates vs the years the job asks for.
- Scores are worked out in code, not by the AI. The AI only explains and writes.
- ML helpers: Naive Bayes (job family), Logistic Regression (shortlist chance), KNN (similar people),
  K-Means + PCA (talent groups). These are hints only.
""")
st.markdown("**Recent activity**")
for l in api.get("/settings/activity", limit=15):
    ui.html_block(f'<p class="small muted" style="margin:.1rem 0">{ui.fmt_ts(l["created_at"])} · '
                  f'<b style="color:#0F172A">{ui.esc(l["action"])}</b> {ui.esc(l["detail"] or "")} · {ui.esc(l["by_name"])}</p>')
