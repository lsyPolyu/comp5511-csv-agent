# Presentation and demo script (5-7 minutes + Q&A)

Slides: the "Feedback-Driven Tool Use for CSV Analysis Agents" deck (10 slides, speaker notes on each).

## Before the session (day before and 15 minutes before)

1. Laptop charged, on the venue Wi-Fi; DeepSeek balance above CNY 5.
2. `cd F:\JavaAiNew\agent_project\COMP5511` and start the UI:
   `.\.venv\Scripts\python.exe -m streamlit run app.py` -> browser at http://localhost:8501
3. Run question 1 below once (warms up the API and checks the key).
4. Have `data\raw\train.csv` ready in File Explorer, and the backup screen recording open in a player.

## Timing

| Time | Slide | What to say (short) |
| --- | --- | --- |
| 0:00 | 1 Cover | Project, research question. |
| 0:30 | 2 Problem | Models pick plausible but wrong arguments; failures or silent wrong answers. |
| 1:15 | 3 Approach | Three tools, Python computes everything, three ways to handle a failed call. |
| 2:00 | 4 Feedback | Same F08 error: raw message vs structured feedback, 1/3 vs 3/3. |
| 2:45 | 5 Demo | Live demo, about 2 minutes (below). |
| 4:45 | 6 Setup | 2 datasets, 40 tasks, 10 faults, 450 runs, independent references. |
| 5:15 | 7 Results | 100% natural for all; fault recovery 10 / 93 / 100%. |
| 5:45 | 8 Cost | Proposed 26% fewer tokens, 25% less time; free when nothing fails. |
| 6:15 | 9 Cases | F08 needs the numeric column list; F04 silent fault. |
| 6:45 | 10 Takeaways | Three takeaways, limits, thank you. |

## Live demo (about 2 minutes)

1. Upload `train.csv`; open the "Data" expander for one second (891 rows, 12 columns).
2. Mode `proposed`. Ask: **What was the survival rate for each passenger class? Draw a bar chart.**
   Expected: class 1 0.63, class 2 0.47, class 3 0.24; table, bar chart, action log with
   `aggregate_data` then `plot_result`, T = 2, R = 0.
3. Point at the action log: "These are the exact arguments the model chose; Python computed the numbers."
4. Repair path: click "Use the 8-row sample", tick "Offline scripted demo", mode `proposed`, Run.
   Say clearly: "This one is a scripted replay, labelled offline, to show a repair deterministically."
   Show: first call uses `gender` (red), feedback lists `Sex`, the corrected call succeeds, R = 1.
5. Optional if time: switch the same offline demo to `baseline` -> stops with `tool_error`.

Backup: if the network or API fails, play the screen recording of steps 1-4 and continue.

## Likely questions and answer points

1. **Why not just use LangChain or another agent framework?**
   The research is about what happens after a failed call; a framework hides retries and messages.
   Writing the loop makes every counter (T, R, requests) explicit and logged.
2. **Natural tasks are all 100%. Does your method help at all?**
   With good column names and notes, this model rarely makes argument errors, so natural tasks cannot
   separate the modes; I report that. Under controlled faults, proposed recovers 100% vs 93% for raw
   retry, and with 26% fewer tokens and 25% less time. It costs nothing when the call is right.
3. **Isn't fault injection artificial?**
   Yes; it is a controlled test so every mode faces the identical error at the same point. The faults
   copy real error types (wrong name, wrong case, wrong type, missing category). Limitation acknowledged;
   next step is weaker models with more organic errors.
4. **How do you know an answer is correct?**
   Independent Pandas reference script that imports none of the agent code; tolerance 1e-6; tables,
   chart type and axes, and the named winner are checked. An oracle run reproduced all 50 references.
5. **Is the difference between raw_retry and proposed significant?**
   For success, no: 2 runs, McNemar p = 0.5. The consistent difference is efficiency (one repair round
   every time). Against baseline both retry modes are highly significant (p < 1e-7).
6. **What can the validator not catch?**
   Calls that are valid but answer the wrong question, for example averaging the wrong numeric column.
   That needs semantic checks or user confirmation.
