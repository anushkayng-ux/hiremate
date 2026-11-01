# HireMate Plus: 40 Features Beyond the 5 Core Requirements

All Plus code lives in its own folders, so the 5 core features stay untouched:

- `backend/app/plus/`: logic and API (`insights.py`, `talent.py`, `hr_tools.py`, `portal_tools.py`, `router.py`)
- `frontend/plus/`: screens (`hub.py` = the **Plus** page, `plus_ui.py` = shared pieces, `portal_steps.py`, `portal_cv.py`)
- `tests/test_plus.py`: 15 tests

**Same safety rules as the core:** every number is worked out in code from HireMate's own data and can be explained. The AI only
rewrites wording (when a key is set). Nothing in Plus rejects, moves or messages a candidate on its own. Candidates never see scores.

## Where to find each feature

| # | Feature | Where (HR) | What it does |
|---|---|---|---|
| **Smarter matching** ||||
| 1 | Best fit elsewhere | Plus → Today · Candidate → Insights | A person weak for their job but 10+ points stronger for another open job. One click adds them. |
| 2 | Success profile | Candidate → Insights | Traits shared by your good hires (or top applicants) and how many this person has. |
| 3 | Hire and train | Candidate → Insights | Missing must-have skills with weeks to learn each. "Trainable" if 4 weeks or less. |
| 4 | Ask the CV | Candidate → Insights | Answers questions with the exact CV lines quoted, or says "Not in the CV". |
| 5 | CV integrity check | Candidate → Insights | Overlapping jobs, years that don't add up, sudden title jumps, figures over 100%, copied CV text. |
| **Spotting problems early** ||||
| 6 | Dropout risk | Plus → Today · Candidate → Insights | Risk 0–95 with reasons (waiting, no reply, unconfirmed interview, commute, salary, notice) and what to do. Writes a check-in message. |
| 7 | Commute check | Candidate → Insights | Estimated travel time across Delhi-NCR (about 30 areas) from home to the store. |
| 8 | Salary fit meter | Candidate → Insights · Plus → Messages (pay band) | Expected salary (from the screening question) vs the job's pay band. |
| 9 | Offer at risk | Plus → Today | Finds hesitation in candidate replies ("another offer", "I'll think about it") and quotes it. |
| **For candidates (portal)** ||||
| 10 | CV coach | Portal → Improve my CV | Tips per job with example lines. Never shows scores. |
| 11 | No CV? Answer 6 questions | Sign-in page (3rd tab) · Portal → Improve my CV | Writes a clean CV from simple answers, then signs up or replaces the CV. |
| 12 | AI chat screening | Portal → My next steps · Candidate → Insights | 5 questions in a chat, scored 1–5 each with a reason that HR sees. |
| 13 | Pick your own interview slot | Portal → My next steps | Shortlisted candidates book a free slot; it's confirmed and the invite is drafted. |
| 14 | Honest status timing | Portal → My next steps | "Usually 3 days at this step. You're on day 2." Uses real stage times. |
| 15 | Joining day checklist | Portal → My next steps · Plus → Decisions & team · Candidate → Insights | Upload ID, PAN, bank details after accepting; HR marks each checked. |
| **HR's day** ||||
| 16 | 9 AM briefing | Home · Plus → Today | Interviews, replies, risks, long waits, better fits and drafts in 5 lines. |
| 17 | Bring back runners-up | Plus → Talent pool | For a job: strong people from other jobs or the pool. Adds them and drafts invites. |
| 18 | Job post writer | Plus → Messages | Naukri, LinkedIn, Apna (Hinglish) and WhatsApp versions, ready to copy. |
| 19 | Interview notes → scorecard | Plus → Interviews | Rough notes become 1–5 ratings per must-have, each with the line it's based on. Saves as feedback. |
| 20 | Cashier billing test | Portal → My next steps · Candidate → Insights | 8 timed sums (bill totals, change, discounts), marked automatically. |
| 21 | Question bank that learns | Plus → Interviews | 👍/👎 on questions; the most useful rise to the top for that role. |
| 22 | Hindi CV reading | Plus → Decisions & team | Devanagari CVs converted (names and places transliterated) and matched like English ones. |
| 23 | Recruiter performance | Plus → Decisions & team | Per recruiter: CVs reviewed, interviews booked, emails sent, hires, days to hire. |
| **Matching (new)** ||||
| 24 | Why this score? | Candidate → Insights | Plain reasons + the single change that would raise the score most (re-scored in code). |
| 25 | JD reality check | Plus → Talent pool | % of the pool who prove each must-have. Flags rare asks. |
| 26 | Hidden-gem finder | Plus → Today | Lower score but results in numbers, promotions, awards or long stays. |
| 27 | Career-path view | Candidate → Insights | Timeline chart: growth, job-hopping, gap or stable. |
| **Interviews (new)** ||||
| 28 | Live interview helper | Plus → Interviews | Tick questions, write notes; suggests the next question for skills not covered yet. |
| 29 | Panel agreement check | Candidate → Insights | Flags when two interviewers' ratings differ by 2+ points on a skill. |
| 30 | Role-play scenarios | Plus → Interviews | Store situations per skill, with a good answer and red flags. |
| **Communication (new)** ||||
| 31 | Tone switch | Plus → Messages | Any draft to Formal, Warm, Short, Hindi or Hinglish. |
| 32 | Answer candidate questions from policy | Plus → Messages | Replies drafted only from your policy documents, with the source named. |
| 33 | Bulk update, personal touch | Plus → Messages | One update to a whole stage; each message names that person's strength. |
| **Decisions and fairness (new)** ||||
| 34 | Decision journal | Candidate → Insights · Plus → Decisions & team | One line on why for every decision. Lists decisions with no reason written. |
| 35 | Blind first look | Plus → Decisions & team | Names hidden everywhere until someone presses "I'm interested". |
| 36 | Second opinion | Candidate → Insights · Plus → Decisions & team | Argues the other side from the data: reasons to slow down or to reconsider. |
| **Talent pool (new)** ||||
| 37 | Talent pool health | Plus → Talent pool | Per job: in pipeline, ready and close in the pool. Healthy, thin or empty. |
| 38 | Re-engage silver list | Plus → Talent pool | This month's 5 past candidates worth contacting again, with a message. |
| 39 | Skill demand board | Plus → Talent pool | Skills jobs need vs % of the pool who prove them (chart). |
| 40 | Duplicate and merge | Plus → Talent pool | Same phone, near-same email, or same name and city. Merge keeps the history. |

## Demo data added for Plus

- Expected salaries in screening answers, and a hesitant reply from Priya ("another offer").
- **Deepak Singh**, a warehouse lead who applied for Cashier: shows *Best fit elsewhere*.
- A second interviewer for Anjali who disagrees on Customer service: shows *Panel agreement*.
- A duplicate profile of Imran (same phone, different email): shows *Duplicate and merge*.
- Rohit marked "not selected" for Cashier with no reason yet: shows the *Decision journal* reminder.
- Starter questions in the question bank, and an "Interview day guide" policy (parking, certificates).

## 3-minute Plus demo

1. **Home**: read the briefing card → **Open Plus**.
2. **Today**: Priya might drop out ("another offer") → Deepak is a better fit for Warehouse → **Add**.
3. Open Imran → **Insights**: why the score is 43%, the biggest single fix, 68-minute commute, CV integrity flag.
4. **Interviews**: paste notes → **Make scorecard** → role-play scenario.
5. **Messages**: answer Arjun's parking question from policy → change a draft's tone to Hinglish → job posts.
6. Sign in as **sana.khan@example.com**: My next steps → chat screening → billing test.
