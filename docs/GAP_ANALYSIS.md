# HireMate: Competitor Gap Analysis

**Date:** 1 November 2026 · **Compared with:** Greenhouse, Lever, Ashby, Workable, Zoho Recruit, Naukri RMS,
Darwinbox, Manatal, Paradox (Olivia), BambooHR, SmartRecruiters, iCIMS.

## 1. Assignment requirements: status

| # | Requirement | Status | Where |
|---|---|---|---|
| R1 | Upload and analyse CVs and JDs | ✅ Done | Jobs → New job · Job → Add CVs · Candidate portal sign-up · Documents |
| R2 | Match and rank, show skills and gaps | ✅ Done | Job page (ranked list, price-tag score, Has ✓ / Missing ✗), Board, Candidate → Why this match |
| R3 | Summaries + role-specific interview questions | ✅ Done | Candidate → Overview (Quick summary) · Candidate → Interview |
| R4 | Draft recruitment emails (invite, assessment, …) | ✅ Done (+ offer letters, WhatsApp) | Candidate → Emails · Candidate → Offer |
| R5 | Answer recruitment questions from the data | ✅ Done (now also sees offers, sources, screening answers) | Ask AI on every page |
| Tech | Python, AI/ML/NLP/LLM, simple UI, sample data, setup steps, grounded answers | ✅ Done | FastAPI + Streamlit, scikit-learn, BM25/embeddings, Gemini/Claude/Ollama, README |

Still open from the tracker: **T49 demo rehearsal**. The app is live on Render; the README still describes Hugging Face Spaces as an option.

## 2. What almost every recruiting tool has

| Common feature | Who has it | HireMate before | HireMate now |
|---|---|---|---|
| CV parsing + AI matching | All | ✅ | ✅ |
| Pipeline / kanban board | Greenhouse, Lever, Workable, Zoho | List only | ✅ **Board** view per job |
| Screening / knockout questions on apply | Workable, Zoho, Paradox, Naukri RMS | ❌ | ✅ Per-job questions, answered in the portal; flags only, never auto-reject |
| Interview scheduling + calendar invites | All | Slots, no calendar file | ✅ `.ics` for recruiter and candidate (1-hour reminder) |
| Offer letters + accept/decline | Greenhouse (DocuSign), BambooHR, Pinpoint, Darwinbox | Selection email only | ✅ Offer letter (Word), send to portal, Accept / Decline, acceptance rate |
| SMS / WhatsApp messaging | Paradox, iCIMS, Indian ATS tools | ❌ | ✅ WhatsApp version of any sent email + click-to-chat link |
| Source-of-hire tracking + referrals | Greenhouse, Lever, SmartRecruiters | ❌ | ✅ Source on every application, referrer name, "Where good candidates come from" report |
| Time-to-hire / time-in-stage | Ashby, Greenhouse, SmartRecruiters | Waiting-too-long alerts only | ✅ Time to hire, time to interview, days per stage, days each job is open |
| Export to Excel | All | Printable shortlist only | ✅ Ranked list as CSV (opens in Excel, keeps ₹ and Hindi names) |
| Privacy / data retention | Enterprise ATS; required in India by the **DPDP Act 2023** | ❌ | ✅ Consent at sign-up, candidate "Delete my data", admin retention clean-up |
| Career site / candidate portal | Workable, Manatal, Pinpoint | ✅ | ✅ (+ "How did you hear about us") |
| Structured scorecards | Greenhouse, Lever | ✅ | ✅ |
| Bias checks / blind review | Textio, Greenhouse | ✅ | ✅ |

## 3. Where HireMate is already ahead of most tools

- **Proof-based skills:** a skill counts fully only if a CV sentence proves it, and that sentence is highlighted.
- **Explainable score:** computed in code, with the breakdown shown. The AI only explains and writes.
- **Hindi emails**, **Ask AI** with sources on every page, **plain-English screening rules**, **Undo** after every move.
- **Two-sided loop:** the candidate portal is connected to the recruiter inbox with Reply with AI.

## 4. Still not built (future work)

| Gap | Why it matters | Effort |
|---|---|---|
| Multi-posting to Naukri / LinkedIn / Indeed / Apna | Biggest source of CVs for store roles | Needs partner APIs |
| WhatsApp Business API (send from the app, chatbot screening) | High-volume store hiring runs on WhatsApp | Needs Meta Business account |
| Walk-in drive / bulk hiring day (token numbers, on-the-spot rounds) | Typical for festive-season retail hiring | Medium |
| Two-way calendar sync (Google / Outlook) | Avoids double-booking interviewers | Medium |
| e-Sign on offers, background verification, onboarding hand-off to HRMS | Closes the loop after "Accepted" | Needs vendors |
| Online skill tests (MCQ / billing speed test) with auto-scoring | Objective signal for cashier roles | Medium |
| Candidate NPS survey after rejection / hiring | Employer brand | Small |
| Adverse-impact (fairness) statistics | Needs real, consented demographic data | Out of scope for synthetic data |

## 5. Sources

- Lever, "13 Best Recruiting Software Platforms for 2026": https://www.lever.co/insights/best-recruiting-software
- Zimyo, "Best AI Recruiting Tools for Indian Businesses (2026)": https://www.zimyo.com/insights/best-ai-recruiting-tools-for-indian-businesses-2026-features-pricing-comparisons-2/
- Darwinbox, "Best Recruitment Software in India": https://darwinbox.com/blog/best-recruitment-software-in-india
- Zoho Recruit vs Naukri RMS (2026): https://itforsme.in/compare/zoho-recruit-vs-naukri-rms
