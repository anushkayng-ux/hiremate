---
title: HireMate
emoji: 🌿
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# HireMate

AI recruiter assistant for an **HR & recruitment team**, with an in-app assistant called **Ask AI**.
Built as an assignment prototype. **All data is synthetic** — no real candidates.

## What it does (the 5 requirements)

| # | Requirement | Where in the app | How (AI / ML) |
|---|---|---|---|
| R1 | Upload and analyse CVs and JDs | Jobs → New job (upload JD) · Job → Add CVs · Candidate portal → apply with CV · Settings → Documents | PDF/Word/text parsing, skill extraction with proof sentences, JD quality + bias check |
| R2 | Match and rank, with skills and gaps | Job page (best match first, Has ✓ / Missing ✗), Quick review, Candidate → Why this match | Skills + BM25/embeddings text match + experience; your own rules; ML shortlist chance |
| R3 | Candidate summaries + role-specific interview questions | Candidate → Overview (Quick summary) · Candidate → Interview (Questions to ask, Practical task) | LLM, grounded in the CV, the job and your rules |
| R4 | Draft recruitment emails (invitation, assessment, …) | Candidate → Emails (Write draft → Send) · auto-drafts on Book / Hire / Not selected · Reply with AI | LLM drafts, recruiter presses **Send**; goes to the candidate portal (and real email if SMTP is set) |
| R5 | Answer recruitment questions from the data | **Ask AI** button on every page · Documents → Ask | LLM over a snapshot of all jobs, candidates, interviews, emails, replies + RAG over policies, with sources |

**Two portals, one loop**

1. Recruiter adds a job and CVs (or candidates apply themselves in the candidate portal).
2. HireMate ranks them. **Quick review**: Shortlist / Maybe later / Not selected, one person at a time.
3. **Book interview**: 3 free time slots, one click. AI drafts the invite. Recruiter presses **Send**.
4. Candidate sees it in **Messages**, confirms or asks for another time, or replies.
5. The reply lands in the recruiter's **Home → Replies from candidates**. **Reply with AI** drafts the answer.
6. After the interview: rate each must-have skill for that one job, then Hire (AI drafts the selection email) or Not selected (AI drafts a kind email).

Also: things to check on each CV (gaps, short jobs, missing contact, duplicates), waiting-too-long alerts, Undo,
share shortlist (printable page), compare 2–3 people, Hindi emails, blind review, reports, team roles, activity log.

## New in this version (from the competitor gap review, see `docs/GAP_ANALYSIS.md`)

| Feature | Where |
|---|---|
| **Pipeline board** (one column per stage, move with →) | Job → Board |
| **Screening questions** per job (yes/no, number, short answer). Candidates answer in the portal. A "must" question that doesn't match **flags** the person; nobody is auto-rejected | Job → Screening questions · Candidate → Overview · portal → My applications |
| **Offer letters**: numbers from a form, AI may reword but never changes a figure, Word download, Send → candidate **Accepts / Declines** in the portal | Candidate → Offer · portal → My applications |
| **WhatsApp**: short version of any sent email + click-to-chat link | Candidate → Emails → Also send on WhatsApp |
| **Calendar invite (.ics)** with a 1-hour reminder | Candidate → Interview · portal → My applications |
| **Source of hire + referrals** (Naukri, LinkedIn, Apna, Walk-in, Referral …) | Add CVs dialog · Candidate → Source · Reports |
| **Speed reports**: time to hire, time to interview, days in each stage, offer acceptance | Reports → Speed and sources |
| **Export ranked list** to Excel (CSV) | Job → Candidates |
| **Privacy (DPDP Act 2023)**: consent at sign-up, candidate "Delete my data", admin retention clean-up, admin erase | Sign-up · portal → My profile · Settings → Privacy |
| **New look**: aubergine "store aisle" menu, shelf-tag yellow highlight, match scores shown as price tags | Everywhere |

## HireMate Plus: 40 extra features (separate folder)

Everything beyond the 5 core requirements lives in **`backend/app/plus/`** and **`frontend/plus/`**, with a **Plus** item in
the menu, an **Insights** tab on every candidate, a briefing card on Home, and **My next steps** + **Improve my CV** in the
candidate portal. Highlights: dropout risk, best fit elsewhere, commute and salary fit, hidden gems, why-this-score with the
biggest single fix, CV integrity check, career-path chart, AI chat screening, cashier billing test, self-booked interviews,
joining checklist, notes → scorecard, panel agreement, question bank that learns, Hindi CVs, tone switch, policy answers,
decision journal, blind first look, second opinion, talent-pool health and duplicate merge.

Full list, where each one is, and a 3-minute demo: **`docs/PLUS_FEATURES.md`**.

## Tech stack

- **Frontend:** Streamlit (multipage, "store aisle" theme: Bricolage Grotesque + Figtree). Two portals: recruiter and candidate.
- **Backend:** FastAPI + Uvicorn + Pydantic
- **Data:** SQLite (source of truth) + ChromaDB (search index). Every JD/CV is stored in both.
- **Parsing:** pdfplumber, python-docx
- **NLP:** skill dictionary + synonyms, BM25, TF-IDF, bge-base-en-v1.5 embeddings (optional)
- **ML (scikit-learn):** Naive Bayes, Logistic Regression, KNN, K-Means + PCA
- **LLM:** free plan by default (Gemini Flash free key, or Qwen 2.5 on Ollama). Paid plan optional (Claude, Gemini Pro). Templates if no key. Switch in Settings.
- **Auth:** bcrypt + JWT. Staff roles (Admin, Recruiter, Interviewer) and candidate accounts use separate tokens: a candidate can never open a recruiter page.

## Turn on AI (free, 2 minutes)

1. Open https://aistudio.google.com/apikey and sign in with any Google account.
2. Click **Create API key** and copy it.
3. In HireMate: **Settings → AI model → Free → Gemini Flash**, paste the key, **Save**, then **Test connection**.

Without a key everything still works, but summaries, questions, emails and answers use simple templates.
The key stays on the server (never shown again, never in the browser or in Git).

## Candidate portal

On the sign-in page choose **Candidate**. Every sample candidate can sign in with their email
(e.g. `arjun.mehta@example.com`) and password `candidate123`. New people can sign up with their CV.
Candidates see only their own applications (never scores), the emails you **sent** (never drafts), their interview, and open jobs.

## Real email (optional)

Emails always arrive in the candidate portal. To also send a real email, add to `.env`:
`SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`. Synthetic `@example.com` addresses are never mailed.

## Run it locally

**Easiest:** Windows → double-click `run.bat`. Mac → double-click `run_mac.command`.
It installs everything on the first run (3–5 minutes) and opens http://localhost:8501.

**Manual steps:**

1. Install Python 3.11+.
2. Install packages:
   ```bash
   pip install -r requirements.txt
   ```
3. (Optional) turn on AI writing: sign in as Admin → **Settings → AI model**.
   - **Free (default):** paste a free Google AI Studio key (Gemini Flash), or use Qwen on Ollama offline.
   - **Paid (optional):** pick Claude or Gemini Pro and paste your key.
   - Click **Test connection**. Keys are saved on the server only and never shown again.
   - You can also set `GEMINI_API_KEY` in `.env` instead.
4. Start both parts:
   ```bash
   ./start.sh                # opens on http://localhost:7860
   ```
   Or in two terminals:
   ```bash
   uvicorn backend.app.main:app --port 8000
   cd frontend && streamlit run app.py
   ```
5. Sign in: `admin@hiremate.demo` / `recruit123` (Admin).
   Others: `recruiter@hiremate.demo`, `interviewer@hiremate.demo` (same password).

- The database seeds itself on first start (3 jobs, 7 CVs, 8 policy docs).
- API docs: http://localhost:8000/docs
- Without any AI key, every feature still works with templates. A key makes the writing better.
- Better matching (optional): `pip install -r requirements-embeddings.txt` → uses bge-base-en-v1.5.
- Offline AI (optional): install Ollama, `ollama pull qwen2.5:7b-instruct`, set `LLM_PROVIDER=ollama`.

## Run the tests

```bash
pytest -q
```
40 tests. Covers login, parsing, ranking, JD/CV upload, duplicates, pipeline, interviews, feedback, emails + approval,
knowledge CRUD + RAG, the full Ask AI flow, analytics, settings, role checks, screening questions, offers,
WhatsApp, calendar, sources, CSV export, consent and data erasure.

## Deploy on Render (current live demo)

1. New → **Web Service** → connect the GitHub repo → Runtime **Docker** (uses the `Dockerfile`).
2. Environment: add `JWT_SECRET` and (optional) `GEMINI_API_KEY`. Render sets `PORT`; `start.sh` uses it.
3. Free instances sleep when idle: open the link a minute before a demo. Storage resets on redeploy, so the demo data reloads.

## Put it online free (Render)

1. Push this folder to a GitHub repo.
2. On render.com: **New → Blueprint**, pick the repo. `render.yaml` creates one free Docker web service.
3. When asked, paste your free Gemini key into `GEMINI_API_KEY` (`JWT_SECRET` is generated for you).
4. Wait for the build (about 5 minutes), then open the `onrender.com` link.

Notes:
- Keys stay on the server, never in the browser or on GitHub.
- Free services sleep after 15 minutes idle; the first visit takes about a minute to wake. Open it before a demo.
- Free storage resets on each restart or deploy, so the demo data reloads. Fine for a prototype; use the PC version for data you keep.
- The same Dockerfile also runs on Hugging Face Spaces (Docker) or any Docker host.

## Talk to Ask AI (examples)

- Attach a JD → "Who matches this?" → "Yes, create the job"
- Attach CVs → "Add to Store Manager"
- "Write a JD for a visual merchandiser in Noida with 2+ years" → download .docx → "ok, create the job"
- "Shortlist Kavya for Store Manager" · "Schedule an interview for Kavya on Tuesday at 3pm"
- "Draft an invitation for Kavya" → "send"
- "Which candidates are awaiting interviews?" · "Compare Priya and Rohit"
- "Can a candidate reschedule twice?" (answers from policy docs, with sources)
- "Add a policy: Notice period is 30 days for store staff" · "Delete the hiring time FAQ"

## Safety rules (always on)

- Scores are computed in code. The AI only explains and writes.
- AI never rejects anyone. Rejections need a recruiter's "yes".
- AI only drafts. Every email stays a draft until a recruiter presses Send. Sending is logged.
- Ask AI asks before creating, deleting or sending anything.
- Answers cite sources, or say "not in the data".
- Employment gaps are never scored. JDs are checked for biased words. Blind review mode hides names.

## Project layout

```
backend/app/
  main.py            FastAPI app, startup (seed + index)
  config.py, db.py   settings, SQLite schema + helpers
  security.py        bcrypt + JWT, roles
  core/              parsing, skills, matching, ML, NLP, JD check   (pure logic)
  adapters/          llm (Gemini/Claude/Ollama), embedder (bge/hashing), vectorstore (Chroma/memory)
  plus/              HireMate Plus: 40 extra features (insights, talent, hr_tools, portal_tools, router)
  services/          recruit, assist (AI writing), interviews, knowledge (RAG), analytics, assistant (Ask AI), files,
                     extras (screening questions, offers, WhatsApp, calendar, sources, CSV, privacy)
  routers/           HTTP endpoints
  seed.py, sample_data.py   synthetic demo data
frontend/
  app.py             login + navigation
  views/             one file per page
  api.py, ui.py, widgets.py
tests/test_api.py, tests/test_extras.py, tests/test_plus.py
docs/TECHNICAL.md    architecture, models, matching, limits
```
