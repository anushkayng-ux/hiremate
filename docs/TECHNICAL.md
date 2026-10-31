# HireMate — Technical note

## 1. Architecture

- **Layered + ports and adapters.**
  - `frontend/` (Streamlit) only draws screens and calls the API. It holds no keys and no database.
  - `routers/` turn HTTP into service calls. Pydantic validates every input.
  - `services/` hold the use cases (recruit, interviews, emails, knowledge, assistant, analytics).
  - `core/` is pure logic (parsing, skills, scoring, ML). Easy to test.
  - `adapters/` are swappable: `LLMProvider` (Gemini / Claude / Ollama), `Embedder` (bge / hashing),
    `VectorStore` (ChromaDB / in-memory).
- **Storage rule:** each JD, CV and policy is stored twice.
  - SQLite = source of truth (records, stages, emails, logs).
  - ChromaDB = search index (chunks + embeddings). It can be rebuilt from SQLite at any time (done on startup
    if the embedder changed).

## 2. Data model

`users` · `jobs` · `job_skills (must|nice)` · `candidates` · `candidate_skills (Proven|Listed + proof sentence)` ·
`applications (job × candidate, stage)` · `match_results` · `interviews` · `interview_feedback` ·
`emails (Draft|Approved, approved_by)` · `notes` · `knowledge_docs` · `activity_logs` · `settings` ·
`assistant_sessions` · `generated_files`

## 3. Parsing

- PDF → pdfplumber; Word → python-docx (paragraphs + tables); TXT as is. Scanned PDFs give a clear error.
- **JD:** title (first line), `Location:`, `Must have:`, `Nice to have:`, `Qualification:`, years (`N+ years`).
  If there is no "Must have" line, skills are found from the whole text.
- **CV:** name, email, phone, city, summary, education level, roles with date ranges
  (`Apr 2021 – Present`), total years from the dates, skills.
- **Skill proof:** a skill is **Proven** only if a real CV sentence mentions it (the sentence is stored).
  If it only appears in the skills list it is **Listed**. This stops keyword stuffing.

## 4. Matching (computed in code)

```
Match = (w_s · Skills + w_t · Text + w_e · Experience) / (w_s + w_t + w_e)     default 50 / 30 / 20
Skills     = Σ weight × credit / Σ weight     must-have weight 2, nice 1; Proven 1.0, Listed 0.5, Missing 0
Text       = cosine(JD, CV)   bge-base-en-v1.5 (rescaled) or TF-IDF over all JDs+CVs when offline
Experience = min(100, CV years / years asked × 100)
```
- Every result returns the breakdown, per-skill status with proof, missing must-haves and "what would raise the
  score". Weights are editable in Settings and re-rank every job.
- Employment gaps are never part of the score.

## 5. Model choice

| Area | Picked | Why | Also considered |
|---|---|---|---|
| Skill extraction | Rules + synonym dictionary (+ LLM backup for writing) | Exact, explainable, works offline | spaCy NER (heavier, needs labelled data) |
| Keyword search | BM25 | Strong on exact terms like "WMS", "POS" | TF-IDF |
| Semantic match | bge-base-en-v1.5 | Top small open embedding model, runs on CPU | MiniLM (weaker), OpenAI embeddings (paid) |
| Offline fallback | Hashing TF + TF-IDF | No download, always available | — |
| Retrieval | BM25 + vectors, reciprocal-rank fusion | Hybrid beats either alone | Vectors only |
| Job family | Multinomial Naive Bayes | Tiny data, fast, probabilistic | Decision tree (overfits), SVM |
| Shortlist chance | Logistic Regression (L2) | Calibrated probability, readable weights | Random forest (black box on tiny data) |
| Similar people | KNN (cosine) | No training, natural fit | — |
| Talent groups | K-Means + PCA | Simple, visual | DBSCAN (unstable on few points) |
| Writing | Gemini Flash (free) / Claude / Qwen 2.5 7B (Ollama) | Free tier, quality option, offline option | GPT-4o (paid) |

ML outputs are shown as **hints**. Recruiters decide.

## 6. Asha (assistant)

1. **Intent router (rules)** handles actions and database questions, so it works with no LLM:
   create job (from attached JD or written JD), add candidates (from attached CVs, with duplicate check),
   rank for a job or for an attached JD, move stage, schedule (parses "Tuesday at 3pm"), draft + approve email,
   notes, feedback, compare, summarize, questions, knowledge list/add/delete.
2. **Confirmations:** create, add, reject, approve and delete wait for a "yes" (pending action in the session).
3. **RAG** for everything else: BM25 + vector search → top chunks → LLM answers with citations [1].
   If nothing matches, it says "not in the data".
4. **Next-step suggestions** after each answer. Session state is stored in SQLite.
5. Writes a JD from a short description and returns a downloadable **.docx** (python-docx).

## 7. Grounding and safety

- LLM prompts include only database facts / retrieved text, temperature 0.2, JSON outputs validated
  (fallback to templates if invalid).
- No auto-reject. Email approval logged with name and time. Every change goes to `activity_logs`.
- JD check flags age, gender, appearance and hype words.
- Blind review hides names in lists.
- Keys only on the server: env / HF Secrets, or saved by an Admin on Settings → AI model (stored in the server DB,
  shown masked, never sent back to the browser). Free plan is the default; paid is opt-in. JWT auth on every endpoint; Interviewers can't change stages.
- Synthetic data only.

## 8. Limits

- Data is tiny and synthetic, so ML numbers are a method demo, not evidence.
- Skill dictionary is retail-focused; new skills from JDs are added as plain phrases.
- No real email sending, calendar sync or candidate portal (out of scope).
- Free hosting sleeps and resets storage.
