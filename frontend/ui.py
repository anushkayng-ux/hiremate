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
STAGE_COLOR = {"Applied": ("#334155", "#F1F5F9"), "Screening": ("#92400E", "#FEF3C7"),
               "Shortlisted": ("#1E40AF", "#DBEAFE"), "Interview": ("#6B21A8", "#F3E8FF"),
               "Selected": ("#FFFFFF", "#16A34A"), "Rejected": ("#B91C1C", "#FEE2E2")}

CSS = """
<style>
.hero{background:linear-gradient(135deg,#1D4ED8 0%,#2563EB 55%,#38BDF8 100%);border-radius:20px;padding:2.2rem 2rem;box-shadow:0 12px 30px rgba(37,99,235,.25)}
.hero .hp{color:#fff;background:rgba(255,255,255,.14);border-radius:12px;padding:.55rem .9rem;margin:.4rem 0;font-weight:500}
:root{--line:#E2E8F0;--fg:#0F172A;--muted:#475569;--accent:#2563EB}
.stApp{background:#F8FAFC}
[data-testid="stHeader"]{background:transparent;height:2.2rem}
.block-container{padding:1.2rem 2.4rem 5rem!important;max-width:1280px}
[data-testid="stVerticalBlock"]{gap:.7rem}
h1{font-size:1.75rem!important;font-weight:700!important;letter-spacing:-.02em;padding:0!important;margin:0!important}
h2,h3{font-weight:700!important;letter-spacing:-.01em}
h3{font-size:1.12rem!important;padding:.1rem 0!important;margin:0 0 .2rem!important}
.eyb{font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:#64748B;margin:0 0 .1rem;font-weight:700}
.muted{color:var(--muted)} .small{font-size:.86rem}
[data-testid="stMarkdownContainer"] p{color:#0F172A}
button p, button span{color:inherit!important}
/* cards = bordered containers */
/* cards: every bordered box is a white card */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:not(.st-key-askfab){background:#FFFFFF;
  border-color:#E2E8F0!important;border-radius:12px!important;padding:1.1rem 1.25rem!important;gap:.75rem}
[data-testid="stForm"]{background:#FFFFFF;border-color:#E2E8F0!important;border-radius:12px!important}
/* tags */
.pill,.tag{display:inline-block;padding:.18rem .65rem;border-radius:999px;font-size:.78rem;font-weight:600;white-space:nowrap;line-height:1.35}
.score{display:inline-block;padding:.18rem .65rem;border-radius:999px;font-weight:600;font-size:.8rem}
.s-hi{background:#DCFCE7;color:#15803D}.s-mid{background:#FEF3C7;color:#B45309}.s-lo{background:#FEE2E2;color:#B91C1C}
.has{display:inline-block;margin:.12rem .2rem .12rem 0;padding:.14rem .6rem;border-radius:999px;font-size:.78rem;font-weight:600;
  background:#F0FDF4;color:#166534}
.miss{display:inline-block;margin:.12rem .2rem .12rem 0;padding:.14rem .6rem;border-radius:999px;font-size:.78rem;font-weight:600;
  background:#FEF2F2;color:#B91C1C}
.lbl-has{color:#15803D;font-weight:600;font-size:.82rem;margin-right:.3rem}
.lbl-miss{color:#B91C1C;font-weight:600;font-size:.82rem;margin:0 .3rem 0 .6rem}
.skill{display:inline-block;margin:.12rem .2rem .12rem 0;padding:.14rem .6rem;border-radius:999px;font-size:.78rem;font-weight:600}
.sk-Proven{background:#F0FDF4;color:#166534}.sk-Listed{background:#FEF3C7;color:#78350F}.sk-Missing{background:#FEF2F2;color:#B91C1C}
.av{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;font-weight:700;flex:none}
.prow{display:flex;align-items:center;gap:.8rem}
.pname{font-size:1.02rem;font-weight:600;color:#0F172A}
.kpi{font-size:1.9rem;font-weight:700;line-height:1.1;color:#0F172A}
.kpil{font-size:.85rem;color:#475569;font-weight:500;margin-top:.2rem}
.ev{border-left:3px solid #16A34A;padding:.1rem 0 .1rem .6rem;margin:.25rem 0;color:#334155;font-size:.86rem}
mark{background:#FEF9C3;color:inherit;padding:.05rem .2rem;border-radius:4px}
.resume{white-space:pre-wrap;font-size:.86rem;line-height:1.6;background:#F8FAFC;border-radius:8px;padding:.9rem 1rem;
  max-height:620px;overflow:auto}
.src{display:inline-block;font-size:.74rem;border:1px solid var(--line);border-radius:6px;padding:.05rem .5rem;margin:.15rem .25rem 0 0;color:#334155;background:#F8FAFC}
.badge{display:inline-block;font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;color:#fff;background:#2563EB;border-radius:4px;padding:.05rem .4rem;margin-bottom:.25rem;font-weight:700}
.note{background:#EFF6FF;color:#1E3A8A;border-radius:8px;padding:.6rem .9rem;font-size:.86rem;font-weight:500}
.okbox{background:#F0FDF4;color:#166534;border-radius:8px;padding:.6rem .9rem;font-size:.9rem;font-weight:600}
.warnbox{background:#FEF2F2;color:#B91C1C;border-radius:8px;padding:.6rem .9rem;font-size:.9rem;font-weight:600}
.flag{background:#FFF7ED;color:#9A3412;border-radius:8px;padding:.45rem .75rem;font-size:.86rem;font-weight:500;margin:.2rem 0}
.flag.info{background:#F1F5F9;color:#334155}
.st-key-undobar{background:#0F172A!important;border-radius:10px!important;padding:.45rem .6rem .45rem 1rem!important}
.st-key-undobar p, .st-key-undobar span{color:#fff!important}
.st-key-undobar button{background:transparent!important;color:#93C5FD!important;border:1px solid #475569!important}
.st-key-undobar button *{color:#93C5FD!important}
.nextbar{background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;padding:.8rem 1rem}
.nextbar b{color:#1E3A8A}
.jsteps{display:flex;gap:.5rem;flex-wrap:wrap}
.jstep{flex:1;min-width:110px;background:#fff;border:1px solid #E2E8F0;border-radius:10px;padding:.55rem .75rem}
.jstep .n{font-size:1.35rem;font-weight:700;color:#0F172A;line-height:1.1}
.jstep .l{font-size:.8rem;color:#475569;font-weight:600}
.jstep.hot{border-color:#2563EB;box-shadow:0 0 0 1px #2563EB inset}
.jstep .k{font-size:.72rem;color:#64748B}
/* stepper */
.steps{display:flex;align-items:center;gap:.6rem;margin:.5rem 0 .4rem}
.step{display:flex;align-items:center;gap:.45rem;font-size:.88rem;font-weight:500;color:#64748B;white-space:nowrap}
.dot{width:26px;height:26px;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;font-size:.8rem;
  font-weight:700;border:2px solid #CBD5E1;color:#64748B;background:#fff}
.step.done{color:#15803D}.step.done .dot{background:#16A34A;border-color:#16A34A;color:#fff}
.step.now{color:#1D4ED8;font-weight:700}.step.now .dot{background:#2563EB;border-color:#2563EB;color:#fff}
.step.no{color:#B91C1C;font-weight:700}.step.no .dot{background:#DC2626;border-color:#DC2626;color:#fff}
.bar{flex:1;height:2px;background:#E2E8F0;min-width:18px}.bar.done{background:#16A34A}
/* buttons */
button[data-testid="stBaseButton-secondary"],button[data-testid="stBaseButton-secondaryFormSubmit"]{border:1px solid #CBD5E1!important;
  color:#0F172A!important;font-weight:600;background:#fff}
button[data-testid="stBaseButton-secondary"]:hover{border-color:#2563EB!important;color:#1D4ED8!important;background:#EFF6FF}
button[data-testid="stBaseButton-primary"],button[data-testid="stBaseButton-primaryFormSubmit"]{font-weight:600;color:#fff!important;
  background:#2563EB!important;border-color:#2563EB!important}
button[data-testid="stBaseButton-primary"]:hover,button[data-testid="stBaseButton-primaryFormSubmit"]:hover{background:#1D4ED8!important}
button[data-testid="stBaseButton-primary"] *,button[data-testid="stBaseButton-primaryFormSubmit"] *{color:#fff!important}
button[data-testid="stBaseButton-tertiary"]{color:#2563EB!important;font-weight:600;padding-left:0!important}
button[data-testid="stBaseButton-tertiary"] *{color:#2563EB!important}
/* segmented control = clear tabs */
[data-testid="stButtonGroup"] button{font-weight:600}
button[data-baseweb="tab"] p{font-weight:600;font-size:.95rem}
/* sidebar: white, simple */
section[data-testid="stSidebar"]{border-right:1px solid #E2E8F0}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a{padding:.55rem .7rem;border-radius:8px;margin:.1rem 0}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span{font-size:.98rem;font-weight:500;color:#334155}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"]{background:#EFF6FF}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] span{color:#1D4ED8;font-weight:600}
.help{background:#F8FAFC;border:1px solid #E2E8F0;border-radius:10px;padding:.7rem .8rem;font-size:.82rem;color:#475569}
/* Ask AI floating button */
.st-key-askfab{position:fixed!important;right:28px;bottom:24px;z-index:999990;width:auto!important}
.st-key-askfab button{padding:.7rem 1.3rem!important;font-size:1rem!important;font-weight:700;border-radius:999px!important;
  background:#2563EB!important;border:none!important;box-shadow:0 8px 24px rgba(37,99,235,.35)}
.st-key-askfab button:hover{background:#1D4ED8!important;transform:translateY(-1px)}
.st-key-askfab button *{color:#fff!important}
/* chat input */
[data-testid="stChatInput"]{border:1.5px solid #94A3B8!important;border-radius:10px}
[data-testid="stChatInputFileUploadButton"] button{background:#2563EB!important;border-radius:999px!important;
  width:auto!important;height:32px!important;padding:0 .7rem 0 .45rem!important;display:flex;align-items:center;gap:.2rem}
[data-testid="stChatInputFileUploadButton"] button svg{fill:#fff!important;color:#fff!important;width:20px;height:20px}
[data-testid="stChatInputFileUploadButton"] button::after{content:"Attach";color:#fff;font-size:.8rem;font-weight:600}
[data-testid="stChatInputSubmitButton"]{background:#2563EB!important;border-radius:8px!important}
[data-testid="stChatInputSubmitButton"] svg{fill:#fff!important;color:#fff!important}
[data-testid="stChatInputSubmitButton"]:disabled{background:#CBD5E1!important}
.emptycol{border:1.5px dashed #CBD5E1;border-radius:10px;padding:1.2rem .8rem;text-align:center;color:#64748B;font-size:.9rem;background:#fff}
div[data-testid="stDialog"] div[role="dialog"]{width:min(900px,94vw)}
[data-testid="stExpander"] details{background:#fff;border-radius:10px}
/* ---- modern + tight (overrides) ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,.stApp,button,input,textarea{font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif!important;font-size:14.5px}
.stApp{background:#F6F7FB}
[data-testid="stHeader"]{height:1.6rem}
.block-container{padding:.6rem 1.6rem 4rem!important;max-width:1400px}
[data-testid="stVerticalBlock"]{gap:.6rem}
[data-testid="stHorizontalBlock"]{gap:.7rem;margin-bottom:.1rem}
h1{font-size:1.45rem!important;letter-spacing:-.025em}
h3{font-size:1rem!important;margin:0 0 .1rem!important}
[data-testid="stMarkdownContainer"] p{margin-bottom:.1rem;line-height:1.45}
[data-testid="stMarkdownContainer"]{overflow:visible}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:not(.st-key-askfab){border-radius:14px!important;
  padding:.85rem 1rem 1.1rem!important;gap:.7rem;box-shadow:0 1px 2px rgba(15,23,42,.04),0 4px 14px rgba(15,23,42,.04)}
[data-testid="stForm"]{border-radius:14px!important;padding:.8rem!important}
.pill,.tag,.score{padding:.1rem .55rem;font-size:.74rem}
.has,.miss,.skill{padding:.08rem .5rem;font-size:.74rem;margin:.08rem .15rem .08rem 0}
.kpi{font-size:1.55rem}.kpil{font-size:.78rem;margin-top:.1rem}
.prow{gap:.6rem}.pname{font-size:.96rem}
.note,.okbox,.warnbox{padding:.45rem .7rem;font-size:.84rem;border-radius:10px}
.nextbar{padding:.55rem .8rem;border-radius:14px}
.jstep{padding:.4rem .6rem;border-radius:12px}.jstep .n{font-size:1.15rem}
.steps{margin:.2rem 0}.dot{width:22px;height:22px;font-size:.72rem}
button[data-testid^="stBaseButton"]{border-radius:10px!important;min-height:2.1rem;padding:.2rem .8rem}
button[data-testid="stBaseButton-primary"]{box-shadow:0 2px 6px rgba(37,99,235,.28)}
[data-baseweb="input"],[data-baseweb="select"]>div,[data-baseweb="textarea"]{border-radius:10px!important}
[data-testid="stWidgetLabel"] p{font-size:.8rem;font-weight:600;color:#475569;margin-bottom:.1rem}
section[data-testid="stSidebar"]{background:#fff}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a{padding:.4rem .65rem;border-radius:10px;margin:.05rem 0}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a span{font-size:.9rem}
.hero{border-radius:22px;padding:1.6rem 1.5rem}
.hero .hp{padding:.4rem .75rem;margin:.3rem 0;border-radius:10px;font-size:.92rem}
.resume{padding:.6rem .8rem;font-size:.82rem;line-height:1.5}
[data-testid="stExpander"] details{border-radius:12px}
[data-testid="stChatMessage"]{background:#fff;border:1px solid #E5E7EF;border-radius:14px;padding:.6rem .85rem;margin-bottom:.4rem}
[data-testid="stChatMessage"] ul{margin:.2rem 0 .2rem 1rem;padding:0}
[data-testid="stChatMessage"] li{margin:.12rem 0}
[data-testid="stChatMessage"] button[data-testid^="stBaseButton"]{font-size:.82rem;min-height:1.9rem;border-radius:999px!important}
[data-testid="stDataFrame"]{border-radius:10px;overflow:hidden;border:1px solid #E5E7EF}
.prow + div,.prow{line-height:1.35}
[data-testid="stMetric"]{padding:.3rem 0}
[data-testid="stMarkdownContainer"] p{padding-bottom:.12rem}
::-webkit-scrollbar{width:8px;height:8px}::-webkit-scrollbar-thumb{background:#CBD5E1;border-radius:8px}

[data-testid="stChatMessage"] h3{font-size:.95rem;font-weight:700;margin:.65rem 0 .2rem;color:#1d4ed8;letter-spacing:.01em}
[data-testid="stChatMessage"] p{margin:0 0 .45rem;line-height:1.5}
[data-testid="stChatMessage"] ul,[data-testid="stChatMessage"] ol{margin:.1rem 0 .55rem;padding-left:1.2rem}
[data-testid="stChatMessage"] li{margin:.15rem 0;line-height:1.45}
[data-testid="stChatMessage"] strong{color:#0f172a}

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
[data-testid="stElementContainer"]:has(h1) + [data-testid="stElementContainer"] p{color:#64748B;font-size:.95rem;margin:0 0 .2rem}
h2{font-size:1.2rem!important;margin:.3rem 0 .2rem!important}
h3{font-size:1.02rem!important;line-height:1.3!important;margin:0 0 .35rem!important;color:#0F172A}
/* cards */
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:not(.st-key-askfab){padding:1rem 1.15rem 1.1rem!important;gap:.65rem!important;
  border:1px solid #E6E9F2!important;border-radius:14px!important;box-shadow:0 1px 2px rgba(15,23,42,.04)}
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]{box-shadow:none;padding:.7rem .9rem!important}
[data-testid="stMarkdownContainer"] p{line-height:1.5;margin:0 0 .2rem}
.muted{color:#64748B}
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
.kpi{line-height:1.1}.kpil{color:#64748B}

/* ---- polish 2 ---- */
h1 + p, [data-testid="stMarkdownContainer"] h1 + p{color:#64748B!important;font-size:.95rem}
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


# --------------------------------------------------------------- components
def stage_pill(stage: str | None) -> str:
    if not stage:
        return '<span class="pill" style="border:1px dashed #94A3B8;color:#475569">Not added</span>'
    fg, bg = STAGE_COLOR.get(stage, ("#0F172A", "#E2E8F0"))
    return f'<span class="pill" style="color:{fg};background:{bg}">{esc(LABEL.get(stage, stage))}</span>'


def fit(s: int | None) -> tuple[str, str, str]:
    """Plain-word fit: (label, background, text colour)."""
    if s is None:
        return "Not scored", "#F1F5F9", "#475569"
    if s >= 70:
        return "Good fit", "#DCFCE7", "#15803D"
    if s >= 50:
        return "Okay fit", "#FEF3C7", "#B45309"
    return "Weak fit", "#FEE2E2", "#B91C1C"


def score_chip(s: int | None) -> str:
    label, bg, fg = fit(s)
    pct = f" · {s}%" if s is not None else ""
    return f'<span class="score" style="background:{bg};color:{fg}">{label}{pct}</span>'


def avatar(name: str, s: int | None = None, size: int = 42) -> str:
    _, bg, fg = fit(s) if s is not None else ("", "#DBEAFE", "#1D4ED8")
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
        out = '<span class="lbl-has" style="color:#64748B">Has none of the must-haves</span>'
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


# --------------------------------------------------------------- header
def header(title: str, eyebrow: str = "", sub: str = "") -> None:
    """Page header: big title, one plain line under it."""
    st.markdown(f'<h1 style="margin:0">{esc(title)}</h1>'
                + (f'<p class="muted" style="margin:.25rem 0 .5rem;font-size:.98rem">{esc(sub)}</p>' if sub else ""),
                unsafe_allow_html=True)


# --------------------------------------------------------------- components
def stage_pill(stage: str | None) -> str:
    if not stage:
        return '<span class="pill" style="border:1px dashed #94A3B8;color:#475569">Not added</span>'
    fg, bg = STAGE_COLOR.get(stage, ("#0F172A", "#E2E8F0"))
    return f'<span class="pill" style="color:{fg};background:{bg}">{esc(LABEL.get(stage, stage))}</span>'


def fit(s: int | None) -> tuple[str, str, str]:
    """Plain-word fit: (label, background, text colour)."""
    if s is None:
        return "Not scored", "#F1F5F9", "#475569"
    if s >= 70:
        return "Good fit", "#DCFCE7", "#15803D"
    if s >= 50:
        return "Okay fit", "#FEF3C7", "#B45309"
    return "Weak fit", "#FEE2E2", "#B91C1C"


def score_chip(s: int | None) -> str:
    label, bg, fg = fit(s)
    pct = f" · {s}%" if s is not None else ""
    return f'<span class="score" style="background:{bg};color:{fg}">{label}{pct}</span>'


def avatar(name: str, s: int | None = None, size: int = 42) -> str:
    _, bg, fg = fit(s) if s is not None else ("", "#DBEAFE", "#1D4ED8")
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
        out = '<span class="lbl-has" style="color:#64748B">Has none of the must-haves</span>'
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


# the one "next step" for each stage: (button label, what it does)
NEXT = {"Applied": ("Start review", "move", "Screening"), "Screening": ("Shortlist", "move", "Shortlisted"),
        "Shortlisted": ("Book interview", "tab", "Interview"), "Interview": ("Hire", "move", "Selected"),
        "Selected": ("Send offer email", "tab", "Emails")}


def next_step_button(r: dict, job_id: int, key: str, can_edit: bool = True, big: bool = False) -> None:
    """One clear button that moves the candidate forward."""
    stage = r.get("stage")
    if not stage or stage == "Rejected" or stage not in NEXT:
        return
    label, kind, target = NEXT[stage]
    if st.button(label, key=key, type="primary", width="stretch", disabled=not can_edit):
        if kind == "move":
            api.patch(f"/applications/{r['application_id']}", json={"stage": target})
            toast_next(f"{r.get('name', 'Candidate')} → {LABEL[target]}")
            st.rerun()
        else:
            st.session_state["cand_tab"] = target
            open_candidate(r["candidate_id"], job_id)


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
    return f"Candidate #{cid}" if blind() and cid else n


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
