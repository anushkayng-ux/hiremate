# HireMate — Scope Document

**Project:** AI-powered recruiter assistant ("HireMate") with an in-app assistant called **Ask AI**
**Prepared for:** HR & Recruitment team
**Prepared by:** Project team
**Date:** 31 October 2026
**Status:** Clickable mockup done · Python build next

---

## 1. Goal

- Help recruiters do routine hiring work faster: read CVs and JDs, rank candidates, prepare interviews, draft emails, answer questions.
- Every score is explainable. Every AI draft is approved by a human. AI never rejects anyone.
- Recruiter-only tool. **No candidate login or portal.**

## 2. The 5 assignment requirements

| # | Requirement | Where it lives |
|---|---|---|
| R1 | Upload and analyse CVs and JDs | Add candidates, Create job, Knowledge, Ask AI (attach files) |
| R2 | Match and rank candidates, show skills and gaps | Job pipeline, Ranked list, Screening & Matching, candidate Profile |
| R3 | Candidate summaries and interview questions | Profile (AI summary), Interview tab |
| R4 | Draft recruitment emails | Emails tab, Ask AI |
| R5 | Answer recruitment questions from the data | Ask AI (database + documents) |

## 3. Users and roles

| Role | Can do |
|---|---|
| Admin | Everything, including settings and team |
| Recruiter | Jobs, candidates, matching, interviews, emails, knowledge |
| Interviewer | Own interviews: questions, scorecard, feedback |

## 4. In scope

### A. Dashboard
- Open roles, applications, to screen, interviews ahead.
- **Needs you:** next actions (screen, schedule, add feedback, decide).
- **Coming up:** next interviews. **Roles:** top match per job.

### B. Jobs
- Create job by uploading a JD, writing one with AI, or pasting text.
- AI reads must-have skills, nice-to-have skills, minimum years, qualification, location.
- Recruiter reviews and **edits requirements**; candidates re-rank instantly.
- **JD check:** flags vague, biased (age, gender, appearance) or missing items.
- Each job: **Pipeline board** (drag between stages), **Ranked list**, **Requirements**.
- **Suggested from talent pool:** people already in the database who fit.

### C. Candidates
- Upload many CVs at once (PDF, DOCX, TXT) or paste text.
- Auto-extract name, location, experience years, roles with dates, education, skills.
- **Duplicate check** (same name or email) → Skip or Add anyway.
- Search and filter by skill, city, job, stage, experience, education.
- Stages: **Applied → Screening → Shortlisted → Interview → Selected / Rejected.**

### D. Matching
- Match score = **Skills + Text match + Experience** (weights set in Settings).
- A skill counts fully only if a CV sentence proves it ("Proven"), half if only listed.
- Shows matched skills with proof, missing must-haves, experience vs. required years, "what would raise the score".
- **Review list:** filter by must-have, filter by years, bulk move / compare / reject + draft emails.
- **Compare** 2–3 candidates side by side.
- AI never auto-rejects. Recruiter decides.

### E. Candidate profile
- Resume on the left with proof lines highlighted, AI analysis on the right.
- AI summary (strengths, experience, gaps, fit) with sources.
- Relevant experience, similar candidates, notes, full activity history.

### F. Interview assistant
- Schedule: date, time, mode, interviewer.
- Questions: Technical, HR, Verification (checks CV claims), Gap-probing, each with follow-up and "good answer".
- Assessment / assignment generator with instructions.
- Scorecard (1–5 per must-have), written feedback, **AI feedback summary**, overall readiness.

### G. Email generator
- Types: interview invitation, reminder, follow-up, assessment instructions, selection, rejection.
- Uses candidate, job, interview slot and HR policy. English or Hindi.
- Recruiter edits and **approves** every email; approval is logged.

### H. Ask AI (AI assistant)
- Opens from the header on every page (Ctrl + J). Accepts attached JD / CV / policy files.
- Can: create jobs, add candidates, rank "who matches this JD", move stages, schedule interviews, draft and approve emails, add feedback and notes, compare, summarize, answer policy questions.
- Writes a JD from a short description → **downloadable .docx** → "ok, create the job".
- Manages the knowledge store: list, add, delete (asks to confirm first).
- Shows **next-step suggestions** after every answer.
- Answers come from the **database** (structured) or **documents** (RAG), with a badge and sources. Says "not in data" when it doesn't know.

### I. Knowledge store
- One place for all JDs, CVs, policies and FAQs.
- Upload (auto-sorted), create, edit, view, download .docx, delete.

### J. Analytics
- Applications by job, pipeline funnel, average match by job, most-missing must-haves, shortlist rate, interviews done, selected.

### K. Settings
- Score weights with live preview, blind review, AI model, team & roles, knowledge link, reset demo data.

## 5. Out of scope (future work)

- Candidate portal or job board posting.
- Real email sending, calendar sync, self-scheduling links.
- Video / voice AI interviews, background checks, e-sign offers.
- SSO, encryption at rest, data-retention automation.
- Adverse-impact (fairness) statistics on real data.

## 6. Tech stack (our choice)

| Layer | Choice |
|---|---|
| Frontend | Streamlit (multipage) |
| Backend API | FastAPI + Uvicorn, Pydantic |
| Database | SQLite (records) + local file storage |
| Vector store | ChromaDB |
| CV / JD parsing | pdfplumber, python-docx |
| NLP | spaCy small + skill synonym list, BM25 (rank_bm25), TF-IDF baseline |
| Embeddings | bge-base-en-v1.5 (local) |
| Reranker | bge-reranker-base (optional) |
| Classic ML | scikit-learn: Logistic Regression, KNN, K-Means + PCA, Naive Bayes |
| LLM | Gemini Flash (free) · Qwen 2.5 7B via Ollama (offline) · Claude (optional key) |
| Auth | bcrypt + JWT, recruiter-only |
| Hosting | Hugging Face Spaces (Docker), keys in Secrets |

## 7. Architecture

- **Layered + ports and adapters.** Streamlit only shows screens and calls the API.
- **FastAPI routers:** auth, jobs, candidates, applications, match, interviews, emails, knowledge, assistant, analytics, settings.
- **Services:** ingest, match, interview, email, assistant (intent router + RAG), analytics.
- **Ports:** LLMProvider, Embedder, VectorStore, DocStore, UserStore. Each has swappable adapters.
- **Storage rule:** every JD/CV is stored twice — original + metadata in SQLite (source of truth), chunks + embeddings in ChromaDB (search index).

## 8. Data model

`users` · `jobs` · `job_skills` · `candidates` · `candidate_skills` (status + proof sentence) · `applications` (candidate × job, stage, score) · `match_results` · `interviews` · `interview_feedback` · `emails` (draft, approved_by) · `notes` · `knowledge_docs` · `activity_logs`

## 9. AI and ML approach

- **Scores are computed in code.** The LLM only explains and writes.
- Extraction: rules + synonyms first, LLM as backup. A skill is "Proven" only if its sentence exists in the CV.
- Matching: skills (must-have ×2) + embedding similarity + experience fit.
- ML: Logistic Regression (shortlist chance), KNN (similar people), K-Means + PCA (talent groups), Naive Bayes (job family).
- Assistant: intent router for actions + SQL-style queries, RAG over documents for policy questions.
- Grounding: answers cite sources; low confidence → "not in data"; temperature low; JSON outputs validated.

## 10. Safety and fairness

- No auto-reject. Human approval for every email and stage change.
- Blind review mode. JD bias check. Employment gaps never used in scoring.
- Emails say they were drafted with AI and checked by a recruiter.
- **Synthetic data only.** API keys only on the server.

## 11. Sample data

- 3 jobs: Store Manager (Noida), Cashier / Customer Service Associate (Ghaziabad), Warehouse Supervisor (Gurugram).
- 7 CVs with different fits and quality, interview records, feedback, 8 HR policy / FAQ documents.

## 12. Deliverables

- Clickable mockup (done).
- Source code: FastAPI backend + Streamlit frontend.
- SQLite schema + seed script with synthetic data.
- `.env.example`, `requirements.txt`, `Dockerfile`.
- README with setup steps.
- Short technical doc: architecture, model choice, matching method, limits.
- 5-minute demo script.

## 13. Build plan

| Week | Focus |
|---|---|
| 1 | Data model, seed data, parsing (CV/JD), skills + proof, FastAPI skeleton, login |
| 2 | Matching + scoring, jobs, candidates, pipeline, ranked list, compare |
| 3 | Profile, interviews, emails, knowledge store, Ask AI (actions + RAG) |
| 4 | Analytics, settings, evaluation, deploy to Hugging Face, README, demo rehearsal |

## 14. Acceptance criteria

- A recruiter can complete the full flow: create job → upload CVs → see ranked list with proof → shortlist → schedule → questions → feedback → select → email approved → dashboard updates.
- Ask AI can do every action above from chat, including creating a job from an attached JD and adding a candidate from an attached CV.
- Every score shows its breakdown; every AI answer shows its source or says "not in data".
- No button, form or chat action is a placeholder.

## 15. Risks and limits

| Risk | Plan |
|---|---|
| Messy or scanned PDFs | Clear error, paste-text fallback |
| LLM quota or downtime | Template fallback, offline Qwen option |
| Small synthetic data makes ML weak | Present ML as method demo; rules + embeddings carry ranking |
| Free hosting sleeps | Open the link before the demo |

## 16. Demo script (5 minutes)

1. Sign in → Dashboard "Needs you".
2. Ask Ask AI: attach a JD → "Who matches this?" → "Ok, create the job".
3. Attach a CV → "Add to <job>".
4. Open top candidate → resume with highlights → AI summary.
5. Shortlist → schedule interview → questions → feedback → select.
6. Draft selection email → approve.
7. Ask AI: "Which candidates are awaiting interviews?" and a policy question.
8. Analytics → Settings (weights) → How matching works.
