"""Shared UI helpers: styling, navigation, small components."""
from __future__ import annotations

import html
from datetime import date, datetime

import streamlit as st

import api

PAGES: dict = {}
STAGES = ["Applied", "Screening", "Shortlisted", "Interview", "Selected", "Rejected"]
FLOW = STAGES[:5]
# plain words on screen; the database keeps its own stage names
LABEL = {"Applied": "New", "Screening": "Reviewing", "Shortlisted": "Shortlisted", "Interview": "Interview",
         "Selected": "Hired", "Rejected": "Not selected"}
STAGE_COLOR = {"Applied": ("#3D3954", "#EEEDF3"), "Screening": ("#7A4D00", "#FFF1BF"),
               "Shortlisted": ("#2B2350", "#E7E3F6"), "Interview": ("#0B6149", "#DDF1E8"),
               "Selected": ("#FFFFFF", "#0E7A5C"), "Rejected": ("#B42318", "#FDE6E3")}

CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,650;12..96,700&family=Figtree:wght@400;500;600;700&display=swap");
/* HireMate — "store aisle" theme.
   ink #1E1B33 · canvas #F2F3F6 · aisle (sidebar) #2B2350 · till green #0E7A5C (actions) · shelf-tag yellow #FFD23F (one highlight)
   Headings: Bricolage Grotesque. Body: Figtree. The bold move: match scores are price tags. */
:root{--ink:#1E1B33;--muted:#5A566E;--line:#E3E2EA;--canvas:#F2F3F6;--aisle:#2B2350;--aisle2:#3A3166;
  --go:#0E7A5C;--go2:#0B6149;--tag:#FFD23F;--card:#FFFFFF}
.stApp{background:var(--canvas)}
.hero{background:var(--aisle);border-radius:20px;padding:2rem 1.9rem}
.hero .hp{color:#fff;background:rgba(255,255,255,.08);border-left:4px solid var(--tag);border-radius:10px;padding:.5rem .85rem;margin:.4rem 0;font-weight:500}
[data-testid="stHeader"]{background:transparent;height:2.2rem}
.block-container{padding:1.4rem 2.6rem 6rem!important;max-width:1300px}
[data-testid="stVerticalBlock"]{gap:.75rem}
h1,h2,h3,.kpi,.pname,.bhead{font-family:"Bricolage Grotesque",Figtree,sans-serif!important}
h1{font-size:2.05rem!important;font-weight:700!important;letter-spacing:-.025em;line-height:1.1!important;padding:0!important;margin:0!important;color:var(--ink)}
h2,h3{font-weight:650!important;letter-spacing:-.015em;color:var(--ink)}
h3{font-size:1.15rem!important;padding:.1rem 0!important;margin:0 0 .25rem!important}
.eyb{font-size:.78rem;color:var(--muted);margin:0 0 .1rem;font-weight:600}
.muted{color:var(--muted)} .small{font-size:.86rem}
[data-testid="stMarkdownContainer"] p{color:var(--ink)}
button p, button span{color:inherit!important}
/* panels: flat white, hairline border, no shadow */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:not(.st-key-askfab){background:var(--card);
  border-color:var(--line)!important;border-radius:14px!important;padding:1.15rem 1.3rem!important;gap:.75rem}
[data-testid="stForm"]{background:var(--card);border-color:var(--line)!important;border-radius:14px!important}
/* chips */
.pill,.tag{display:inline-block;padding:.16rem .6rem;border-radius:6px;font-size:.78rem;font-weight:600;white-space:nowrap;line-height:1.4}
.has,.miss,.skill{display:inline-block;margin:.12rem .2rem .12rem 0;padding:.13rem .55rem;border-radius:6px;font-size:.78rem;font-weight:600}
.has{background:#DDF1E8;color:#0A5A43}.miss{background:#FDE6E3;color:#B42318}
.lbl-has{color:var(--go);font-weight:650;font-size:.82rem;margin-right:.3rem}
.lbl-miss{color:#B42318;font-weight:650;font-size:.82rem;margin:0 .3rem 0 .6rem}
.sk-Proven{background:#DDF1E8;color:#0A5A43}.sk-Listed{background:#FFF1BF;color:#6B4400}.sk-Missing{background:#FDE6E3;color:#B42318}
/* THE price tag: match score */
.score{position:relative;display:inline-flex;align-items:center;gap:.35rem;padding:.2rem .7rem .2rem 1.05rem;font-weight:700;
  font-size:.8rem;line-height:1.35;border-radius:0 6px 6px 0;
  clip-path:polygon(10px 0,100% 0,100% 100%,10px 100%,0 50%);font-variant-numeric:tabular-nums}
.score::before{content:"";position:absolute;left:7px;top:50%;width:5px;height:5px;margin-top:-2.5px;border-radius:50%;
  background:var(--canvas)}
.av{display:inline-flex;align-items:center;justify-content:center;border-radius:12px;font-weight:700;flex:none;
  font-family:"Bricolage Grotesque",sans-serif}
.prow{display:flex;align-items:center;gap:.85rem}
.pname{font-size:1.05rem;font-weight:650;color:var(--ink)}
.kpi{font-size:2.2rem;font-weight:700;line-height:1;color:var(--ink);letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.kpil{font-size:.86rem;color:var(--muted);font-weight:500;margin-top:.35rem}
.ev{border-left:3px solid var(--go);padding:.1rem 0 .1rem .6rem;margin:.25rem 0;color:#3D3954;font-size:.86rem}
mark{background:#FFE98A;color:inherit;padding:.05rem .2rem;border-radius:3px}
.resume{white-space:pre-wrap;font-size:.87rem;line-height:1.65;background:#F7F7FA;border:1px solid var(--line);border-radius:10px;
  padding:1rem 1.1rem;max-height:620px;overflow:auto}
.src{display:inline-block;font-size:.74rem;border:1px solid var(--line);border-radius:6px;padding:.05rem .5rem;margin:.15rem .25rem 0 0;color:#3D3954;background:#F7F7FA}
.badge{display:inline-block;font-size:.72rem;color:var(--aisle);background:var(--tag);border-radius:5px;padding:.05rem .45rem;margin-bottom:.25rem;font-weight:700}
.note{background:#E7E3F6;color:var(--aisle);border-radius:10px;padding:.65rem .95rem;font-size:.88rem;font-weight:500}
.okbox{background:#DDF1E8;color:#0A5A43;border-radius:10px;padding:.65rem .95rem;font-size:.9rem;font-weight:600}
.warnbox{background:#FDE6E3;color:#B42318;border-radius:10px;padding:.65rem .95rem;font-size:.9rem;font-weight:600}
.flag{background:#FFF4D6;color:#7A4D00;border-radius:10px;padding:.5rem .8rem;font-size:.87rem;font-weight:500;margin:.2rem 0}
.flag.info{background:#EEEDF3;color:#3D3954}
.qa{display:flex;gap:.6rem;align-items:flex-start;padding:.4rem 0;border-bottom:1px solid var(--line)}
.qa:last-child{border-bottom:0}
.st-key-undobar{background:var(--aisle)!important;border-radius:12px!important;padding:.45rem .6rem .45rem 1rem!important}
.st-key-undobar p, .st-key-undobar span{color:#fff!important}
.st-key-undobar button{background:transparent!important;color:var(--tag)!important;border:1px solid #5B528F!important}
.st-key-undobar button *{color:var(--tag)!important}
.nextbar{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--tag);border-radius:12px;padding:.85rem 1.1rem}
.nextbar b{color:var(--ink)}
.jsteps{display:flex;gap:.5rem;flex-wrap:wrap}
.jstep{flex:1;min-width:110px;background:#fff;border:1px solid var(--line);border-radius:10px;padding:.55rem .75rem}
.jstep .n{font-size:1.35rem;font-weight:700;color:var(--ink);line-height:1.1}
.jstep .l{font-size:.8rem;color:var(--muted);font-weight:600}
.jstep.hot{border-color:var(--go);box-shadow:0 0 0 1px var(--go) inset}
.jstep .k{font-size:.72rem;color:#6B6880}
/* stepper */
.steps{display:flex;align-items:center;gap:.6rem;margin:.55rem 0 .4rem;flex-wrap:wrap}
.step{display:flex;align-items:center;gap:.45rem;font-size:.88rem;font-weight:500;color:#6B6880;white-space:nowrap}
.dot{width:26px;height:26px;border-radius:8px;display:inline-flex;align-items:center;justify-content:center;font-size:.8rem;
  font-weight:700;border:2px solid #D4D2DE;color:#6B6880;background:#fff}
.step.done{color:var(--go)}.step.done .dot{background:var(--go);border-color:var(--go);color:#fff}
.step.now{color:var(--aisle);font-weight:700}.step.now .dot{background:var(--tag);border-color:var(--tag);color:var(--aisle)}
.step.no{color:#B42318;font-weight:700}.step.no .dot{background:#B42318;border-color:#B42318;color:#fff}
.bar{flex:1;height:2px;background:var(--line);min-width:18px}.bar.done{background:var(--go)}
/* pipeline board */
.bhead{display:flex;justify-content:space-between;align-items:baseline;padding:.2rem .2rem .45rem;border-bottom:3px solid var(--aisle);
  margin-bottom:.35rem;font-weight:650;color:var(--ink)}
.bhead b{font-size:1.1rem}
.bempty{border:1.5px dashed #D4D2DE;border-radius:10px;padding:.8rem;text-align:center;color:#9A97AB;font-size:.82rem}
[class*="st-key-bcard"]{padding:.7rem .8rem!important;gap:.35rem!important}
/* buttons */
button[data-testid="stBaseButton-secondary"],button[data-testid="stBaseButton-secondaryFormSubmit"]{border:1px solid #D4D2DE!important;
  color:var(--ink)!important;font-weight:600;background:#fff}
button[data-testid="stBaseButton-secondary"]:hover{border-color:var(--go)!important;color:var(--go2)!important;background:#F2FAF6}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{font-weight:650;color:#fff!important;
  background:var(--go)!important;border-color:var(--go)!important}
button[data-testid="stBaseButton-primary"]:hover,button[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:var(--go2)!important}
button[data-testid="stBaseButton-primary"] *,button[data-testid="stBaseButton-primaryFormSubmit"] *{color:#fff!important}
button[data-testid="stBaseButton-tertiary"]{color:var(--go)!important;font-weight:650;padding-left:0!important}
button[data-testid="stBaseButton-tertiary"] *{color:var(--go)!important}
button:focus-visible,a:focus-visible{outline:3px solid var(--tag)!important;outline-offset:2px}
[data-testid="stButtonGroup"] button{font-weight:600}
[data-testid="stButtonGroup"] button[aria-checked="true"],[data-testid="stButtonGroup"] button[kind="segmented_controlActive"]{
  background:var(--aisle)!important;color:#fff!important;border-color:var(--aisle)!important}
button[data-baseweb="tab"] p{font-weight:600;font-size:.95rem}
/* sidebar = the aisle */
section[data-testid="stSidebar"]{background:var(--aisle)!important;border-right:0}
section[data-testid="stSidebar"] *{color:#E9E6F5}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a{padding:.6rem .8rem;border-radius:10px;margin:.12rem 0}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span{font-size:.98rem;font-weight:500;color:#D6D1EE!important}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover{background:var(--aisle2)}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"]{background:var(--tag)}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] *{color:var(--aisle)!important;font-weight:700}
section[data-testid="stSidebar"] button{background:transparent!important;border:1px solid #5B528F!important}
section[data-testid="stSidebar"] button *{color:#E9E6F5!important}
section[data-testid="stSidebar"] hr{border-color:#4A4178}
.help{background:var(--aisle2);border-radius:12px;padding:.75rem .85rem;font-size:.83rem;color:#D6D1EE}
.help b{color:#fff!important}
/* Ask AI: the one floating thing, in shelf-tag yellow */
.st-key-askfab{position:fixed!important;right:28px;bottom:24px;z-index:999990;width:auto!important}
.st-key-askfab button{padding:.75rem 1.35rem!important;font-size:1rem!important;font-weight:700;border-radius:14px!important;
  background:var(--tag)!important;border:2px solid var(--aisle)!important;box-shadow:4px 4px 0 var(--aisle)}
.st-key-askfab button:hover{transform:translate(-1px,-1px);box-shadow:5px 5px 0 var(--aisle)}
.st-key-askfab button *{color:var(--aisle)!important}
/* chat input */
[data-testid="stChatInput"]{border:1.5px solid #9A97AB!important;border-radius:12px}
[data-testid="stChatInputFileUploadButton"] button{background:var(--aisle)!important;border-radius:8px!important;
  width:auto!important;height:32px!important;padding:0 .7rem 0 .45rem!important;display:flex;align-items:center;gap:.2rem}
[data-testid="stChatInputFileUploadButton"] button svg{fill:#fff!important;color:#fff!important;width:20px;height:20px}
[data-testid="stChatInputFileUploadButton"] button::after{content:"Attach";color:#fff;font-size:.8rem;font-weight:600}
[data-testid="stChatInputSubmitButton"]{background:var(--go)!important;border-radius:8px!important}
[data-testid="stChatInputSubmitButton"] svg{fill:#fff!important;color:#fff!important}
[data-testid="stChatInputSubmitButton"]:disabled{background:#D4D2DE!important}
.emptycol{border:1.5px dashed #D4D2DE;border-radius:12px;padding:1.2rem .8rem;text-align:center;color:#6B6880;font-size:.9rem;background:#fff}
div[data-testid="stDialog"] div[role="dialog"]{width:min(900px,94vw)}
[data-testid="stExpander"] details{background:#fff;border-radius:12px}
/* sign-in screen */
.signin-hero{background:var(--aisle);border-radius:18px;padding:1.6rem 1.7rem;color:#fff;margin-bottom:.4rem}
.signin-hero h1{color:#fff!important;font-size:2.4rem!important}
.signin-hero p{color:#D6D1EE!important;margin:.5rem 0 0}
.signin-hero .tagrow{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:1rem}
@media (max-width:640px){.block-container{padding:1rem 1rem 6rem!important}h1{font-size:1.6rem!important}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
[data-testid="stChatMessage"]{background:#fff;border:1px solid var(--line);border-radius:14px;padding:.6rem .85rem;margin-bottom:.4rem}
[data-testid="stChatMessage"] ul{margin:.2rem 0 .2rem 1rem;padding:0}
[data-testid="stChatMessage"] li{margin:.12rem 0}
[data-testid="stChatMessage"] button[data-testid^="stBaseButton"]{font-size:.82rem;min-height:1.9rem;border-radius:999px!important}
[data-testid="stDataFrame"]{border-radius:10px;overflow:hidden;border:1px solid var(--line)}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#D4D2DE;border-radius:8px}
[data-testid="stDataFrame"]{border-radius:10px;overflow:hidden;border:1px solid #E3E2EA}
.prow + div,.prow{line-height:1.35}
[data-testid="stMetric"]{padding:.3rem 0}
[data-testid="stMarkdownContainer"] p{padding-bottom:.12rem}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#D4D2DE;border-radius:8px}

[data-testid="stChatMessage"] h3{font-size:.95rem;font-weight:700;margin:.65rem 0 .2rem;color:#0B6149;letter-spacing:.01em}
[data-testid="stChatMessage"] p{margin:0 0 .45rem;line-height:1.5}
[data-testid="stChatMessage"] ul,[data-testid="stChatMessage"] ol{margin:.1rem 0 .55rem;padding-left:1.2rem}
[data-testid="stChatMessage"] li{margin:.15rem 0;line-height:1.45}
[data-testid="stChatMessage"] strong{color:#1E1B33}

/* ---- steady layout: side-by-side boxes end at the same line ---- */
[data-testid="stHorizontalBlock"]{align-items:stretch}
[data-testid="stColumn"]{display:flex!important;flex-direction:column}
[data-testid="stColumn"] > [data-testid="stVerticalBlock"]{flex:1 1 auto}
[data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:last-child{flex:1 1 auto}
[data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"]:last-child > [data-testid="stVerticalBlock"]{flex:1 1 auto}
.block-container{max-width:1320px!important}

/* ---- polish: one spacing system (tight but calm) ---- */
.block-container{padding:1rem 2rem 6.5rem!important}
[data-testid="stMain"] [data-testid="stVerticalBlock"]{gap:.8rem}
[data-testid="stHorizontalBlock"]{gap:1rem!important}
h1{font-size:1.6rem!important;line-height:1.2!important;margin:0 0 .1rem!important}
[data-testid="stElementContainer"]:has(h1) + [data-testid="stElementContainer"] p{color:#6B6880;font-size:.95rem;margin:0 0 .2rem}
h2{font-size:1.2rem!important;margin:.3rem 0 .2rem!important}
h3{font-size:1.02rem!important;line-height:1.3!important;margin:0 0 .35rem!important;color:#1E1B33}
/* cards */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:not(.st-key-askfab){padding:1rem 1.15rem 1.1rem!important;gap:.65rem!important;
  border:1px solid #E3E2EA!important;border-radius:14px!important;box-shadow:0 1px 2px rgba(15,23,42,.04)}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]{box-shadow:none;padding:.7rem .9rem!important}
[data-testid="stMarkdownContainer"] p{line-height:1.5;margin:0 0 .2rem}
.muted{color:#6B6880}
/* rows inside cards: avatar + text + button line up */
.prow{align-items:center;gap:.75rem}
.pname{font-weight:600}
[data-testid="stHorizontalBlock"]{align-items:stretch}
/* buttons and inputs: one height */
button[data-testid^="stBaseButton"]{min-height:2.3rem;font-weight:500}
[data-baseweb="input"] input,[data-baseweb="select"]>div{min-height:2.3rem}
[data-testid="stTabs"] [role="tablist"]{gap:.25rem;margin-bottom:.4rem}
[data-testid="stExpander"] summary{padding:.55rem .8rem}
/* sidebar */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a{padding:.5rem .75rem;margin:.1rem .4rem}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.6rem}
/* pills, tags and chips */
.pill,.tag,.score{line-height:1.5;vertical-align:middle}
.kpi{line-height:1.1}.kpil{color:#6B6880}

/* ---- polish 2 ---- */
h1 + p, [data-testid="stMarkdownContainer"] h1 + p{color:#6B6880!important;font-size:.95rem}
[data-testid="stElementContainer"]:has(+ [data-testid="stLayoutWrapper"]){margin-bottom:.3rem}
[data-testid="stPopover"] button, [data-testid="stPopoverButton"]{min-height:2.3rem!important;height:2.3rem}
[data-testid="stLayoutWrapper"] [data-testid="stHorizontalBlock"]{margin-bottom:.25rem}
.kpi-box,[data-testid="stLayoutWrapper"]:has(.kpil) > [data-testid="stVerticalBlock"]{padding:.8rem 1.1rem!important;gap:.15rem!important}
.kpi{margin-bottom:.1rem}
[data-testid="stMain"] [data-testid="stHorizontalBlock"] [data-testid="stVerticalBlock"]{gap:.7rem}
.prow + .prow{margin-top:.4rem}
.block-container{max-width:1360px!important}

.kpil{margin-top:.2rem;padding-bottom:.35rem;line-height:1.3}
.kpi{padding-top:.15rem}

.ainote{background:linear-gradient(90deg,#E6F4EE,#F7F7FA);border:1px solid #E6F4EE;border-radius:12px;padding:.65rem .9rem;
  font-size:.92rem;line-height:1.5;color:#1E293B;margin:.1rem 0 .2rem}
.aibadge{font-size:.72rem;font-weight:700;color:#2B2350;background:#fff;border:1px solid #E7E3F6;border-radius:999px;padding:.05rem .5rem;margin-right:.4rem;white-space:nowrap}
</style>
"""


def setup() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


# --------------------------------------------------------------- navigation
def go(page: str, **state) -> None:
    for k, v in state.items():
        st.session_state[k] = v
    if page not in PAGES:  # this role has no access to that page
        st.session_state["_toast"] = "Your role cannot open that page."
        page = "dashboard"
    st.switch_page(PAGES[page])


def open_candidate(cid: int, job_id: int | None = None) -> None:
    go("candidate", cand_id=cid, cand_job=job_id)


def open_job(job_id: int) -> None:
    go("job", job_id=job_id)


# --------------------------------------------------------------- header
def header(title: str, eyebrow: str = "", sub: str = "") -> None:
    """Page header: big title, one plain line under it."""
    st.markdown(f'<h1 style="margin:0">{esc(title)}</h1>'
                + (f'<p class="muted" style="margin:.25rem 0 .5rem;font-size:.98rem">{esc(sub)}</p>' if sub else ""),
                unsafe_allow_html=True)

def ai_note(page: str, job_id: int | None = None) -> None:
    """A short note written by the AI at the top of a page. Kept for 10 minutes per page."""
    import time
    key = f"_brief_{page}_{job_id}"
    hit = st.session_state.get(key)
    if not hit or time.time() - hit[0] > 600:
        try:
            with st.spinner("AI is writing a note…"):
                r = api.get("/ai/brief", page=page, job_id=job_id)
            hit = (time.time(), r.get("text", ""))
        except api.ApiError:
            hit = (time.time() - 540, "")   # try again in a minute
        st.session_state[key] = hit
    if hit[1]:
        st.markdown(f'<div class="ainote"><span class="aibadge">✦ AI note</span> {esc(hit[1])}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------- components
def stage_pill(stage: str | None) -> str:
    if not stage:
        return '<span class="pill" style="border:1px dashed #9A97AB;color:#5A566E">Not added</span>'
    fg, bg = STAGE_COLOR.get(stage, ("#1E1B33", "#E3E2EA"))
    return f'<span class="pill" style="color:{fg};background:{bg}">{esc(LABEL.get(stage, stage))}</span>'


def fit(s: int | None) -> tuple[str, str, str]:
    """Plain-word fit: (label, background, text colour)."""
    if s is None:
        return "Not scored", "#EEEDF3", "#5A566E"
    if s >= 70:
        return "Good fit", "#0E7A5C", "#FFFFFF"
    if s >= 50:
        return "Okay fit", "#FFD23F", "#2B2350"
    return "Weak fit", "#FDE6E3", "#B42318"


def score_chip(s: int | None) -> str:
    label, bg, fg = fit(s)
    pct = f" · {s}%" if s is not None else ""
    return f'<span class="score" style="background:{bg};color:{fg}">{label}{pct}</span>'


def avatar(name: str, s: int | None = None, size: int = 42) -> str:
    _, bg, fg = fit(s) if s is not None else ("", "#E7E3F6", "#2B2350")
    ini = "".join(w[0] for w in str(name).split()[:2]).upper() or "?"
    return (f'<span class="av" style="width:{size}px;height:{size}px;background:{bg};color:{fg};'
            f'font-size:{int(size * .36)}px">{esc(ini)}</span>')


def has_missing(rows: list[dict], must_only: bool = True) -> str:
    """'Has ✓ …  Missing ✗ …' in plain words."""
    rs = [r for r in rows if r.get("must")] if must_only and any(r.get("must") for r in rows) else rows
    has = [r["skill"] for r in rs if r["status"] != "Missing"]
    miss = [r["skill"] for r in rs if r["status"] == "Missing"]
    out = '<span class="lbl-has">Has</span>' + "".join(f'<span class="has">✓ {esc(x)}</span>' for x in has)
    if not has:
        out = '<span class="lbl-has" style="color:#6B6880">Has none of the must-haves</span>'
    if miss:
        out += '<span class="lbl-miss">Missing</span>' + "".join(f'<span class="miss">✗ {esc(x)}</span>' for x in miss)
    else:
        out += '<span class="lbl-has" style="margin-left:.6rem">Nothing missing</span>'
    return out


def stepper(stage: str | None) -> str:
    if not stage:
        return ""
    cur = FLOW.index(stage) if stage in FLOW else -1
    parts = []
    for i, s in enumerate(FLOW):
        if stage == "Rejected":
            cls = ""
        else:
            cls = "done" if i < cur or (i == cur and s == "Selected") else "now" if i == cur else ""
        mark = "✓" if cls == "done" else str(i + 1)
        parts.append(f'<span class="step {cls}"><span class="dot">{mark}</span>{LABEL[s]}</span>')
        if i < len(FLOW) - 1:
            parts.append(f'<span class="bar {"done" if cls == "done" else ""}"></span>')
    if stage == "Rejected":
        parts.append('<span class="bar"></span><span class="step no"><span class="dot">✗</span>Not selected</span>')
    return '<div class="steps">' + "".join(parts) + "</div>"


# the one "next step" for each stage: (button label, what it does, target)
NEXT = {"Applied": ("Review", "review", None), "Screening": ("Shortlist", "move", "Shortlisted"),
        "Shortlisted": ("Book interview", "tab", "Interview"), "Interview": ("Hire", "move", "Selected"),
        "Selected": ("Send offer email", "tab", "Emails")}
EMAIL_NOTE = {"Rejected": "A polite 'not selected' email is drafted.", "Selected": "A selection email is drafted."}


def move(app_id: int, stage: str, name: str = "Candidate", cid: int | None = None) -> dict | None:
    """Move a candidate. Drafts the right email (never sends) and remembers how to undo."""
    r = safe(api.post, f"/smart/move/{app_id}", json={"stage": stage})
    if r:
        st.session_state["_undo"] = {"app_id": app_id, "old": r["old_stage"], "email_id": r["email_id"], "cid": cid,
                                     "text": f"{name} moved to {LABEL[stage]}." + (
                                         f" {EMAIL_NOTE[stage]} Read it and press Send on Home."
                                         if r["email_id"] else "")}
    return r


def show_undo() -> None:
    """A small bar after every move: what happened + Undo. Disappears on the next click."""
    u = st.session_state.pop("_undo", None)
    if not u:
        return
    with st.container(key="undobar"):
        a, b = st.columns([6, 1], vertical_alignment="center")
        a.markdown(f'<span style="font-weight:600">✓ {esc(u["text"])}</span>', unsafe_allow_html=True)
        if b.button("Undo", key="undo_btn", width="stretch"):
            api.post(f"/smart/undo/{u['app_id']}", json={"old_stage": u["old"], "email_id": u["email_id"]})
            for k in [k for k in st.session_state if str(k).startswith("rvdone")]:
                st.session_state[k].pop(u.get("cid"), None)  # Quick review shows that person again
            toast_next("Undone")
            st.rerun()


def next_step_button(r: dict, job_id: int, key: str, can_edit: bool = True) -> None:
    """One clear button that moves the candidate forward."""
    stage = r.get("stage")
    if not stage or stage == "Rejected" or stage not in NEXT:
        return
    label, kind, target = NEXT[stage]
    if st.button(label, key=key, type="primary", width="stretch", disabled=not can_edit):
        if kind == "move":
            move(r["application_id"], target, r.get("name", "Candidate"), r.get("candidate_id"))
            st.rerun()
        elif kind == "review":
            go("review", job_id=job_id, rv_start=r["candidate_id"])
        else:
            st.session_state["cand_tab"] = target
            open_candidate(r["candidate_id"], job_id)


def flags_html(flags: list[dict]) -> str:
    if not flags:
        return '<div class="okbox">Nothing unusual found in the CV.</div>'
    return "".join(f'<div class="{"flag" if f["level"] == "warn" else "flag info"}">'
                   f'{"⚠" if f["level"] == "warn" else "ℹ"} {esc(f["text"])}</div>' for f in flags)


def skill_chips(rows: list[dict]) -> str:
    return "".join(f'<span class="skill sk-{r["status"]}" title="{esc(r.get("evidence", ""))}">'
                   f'{"★ " if r.get("must") else ""}{esc(r["skill"])}</span>' for r in rows)


def html_block(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def blind() -> bool:
    if "blind" not in st.session_state:
        try:
            st.session_state.blind = bool(api.get("/settings")["blind"])
        except api.ApiError:
            st.session_state.blind = False
    return st.session_state.blind


def name(n: str, cid: int | None = None) -> str:
    if blind() and cid:
        return f"Candidate #{cid}"
    try:  # HireMate Plus: blind first look (hidden until someone marks the person 'interested')
        from plus import plus_ui
        if plus_ui.hidden(cid):
            return f"Candidate #{cid}"
    except Exception:  # noqa: BLE001
        pass
    return n


def fmt_date(d: str | None) -> str:
    if not d:
        return "—"
    try:
        x = date.fromisoformat(d[:10])
    except ValueError:
        return d
    today = date.today()
    if x == today:
        return "Today"
    if (x - today).days == 1:
        return "Tomorrow"
    return f"{x:%a} {x.day} {x:%b}"


def fmt_time(t: str | None) -> str:
    try:
        d = datetime.strptime(t, "%H:%M")
        return f"{d.hour % 12 or 12}:{d:%M %p}"
    except (TypeError, ValueError):
        return t or ""


def fmt_ts(ts: str | None) -> str:
    try:
        d = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        return f"{d.day} {d:%b}, {d.hour % 12 or 12}:{d:%M %p}"
    except (TypeError, ValueError):
        return ts or ""


def safe(fn, *a, **kw):
    """Run an API call, show a friendly error instead of a traceback."""
    try:
        return fn(*a, **kw)
    except api.ApiError as e:
        st.error(e.detail)
        return None


def toast_next(msg: str) -> None:
    st.session_state["_toast"] = msg


def show_toast() -> None:
    m = st.session_state.pop("_toast", None)
    if m:
        st.toast(m, icon="✅")


def highlight(text: str, phrases: list[str]) -> str:
    out = esc(text)
    for p in sorted({p for p in phrases if p and len(p) > 12}, key=len, reverse=True):
        ep = esc(p)
        if ep in out:
            out = out.replace(ep, f"<mark>{ep}</mark>", 1)
    return out
