# Instructions for the daily Claude routine

The GitHub Action fetches and scores items every day without any LLM. This
routine adds written summaries and does the weekly web checks that need
judgement. It only ever writes new files under `data/llm_out/` (and, weekly,
`data/proposals/`) and pushes them; the Action merges them into the site.

## Every day

1. `git pull` on `main`.
2. Read `config/profile.md` (who the reader is) and `data/llm_queue.json`.
3. For each queued item (at most 40, highest relevance first), write an
   English summary from the given title, abstract and page excerpt only:
   - `what`  — what was done or announced (1–2 sentences)
   - `why`   — the motivation or problem (1–2 sentences)
   - `how`   — method, data, tools or format (1–2 sentences)
   - `impact` — concrete relevance to the reader's projects in
     `config/profile.md` (name the project; say "Low relevance" when it is low)
   Use only facts in the provided text. If something is not stated, write
   "Not stated in the abstract." Never invent numbers, names or results.
   For conference / special-issue items: what = scope, why = motivation of
   the call, how = submission format and deadlines, impact = which project
   would fit and whether it is worth submitting.
4. Write `data/llm_out/YYYY-MM-DD.json` (today's date, UTC):
   ```json
   {"summaries": {"<item id>": {"what": "…", "why": "…", "how": "…", "impact": "…"}},
    "new_items": []}
   ```
5. Commit only that file: `git add data/llm_out && git commit -m "Claude summaries YYYY-MM-DD" && git push`.

## Mondays (weekly)

6. Search the web for **open special issues / calls for papers** in journals
   that block automated reading: Elsevier (IJHMT, Int. J. Thermal Sciences,
   Materials Today Physics, Computational Materials Science, Applied Thermal
   Engineering), AIP (JAP, APL, JCP special topics), ASME (J. Heat Mass
   Transfer, J. Electronic Packaging), APS, ACS, IOP (JPCM, MLST), IEEE
   (TCPMT, TED). Topics: phonon / thermal transport, interfaces, MLIPs,
   electronics thermal management and cooling, thermal simulation, AI agents
   for materials simulation. **Exclude MDPI and Frontiers.**
   Add each open call you verified on the publisher's page to `new_items`:
   `{"kind": "special-issue", "title", "url", "venue", "deadline": "YYYY-MM-DD",
     "abstract": "<scope text>", "summary": {what, why, how, impact}}`.
7. Check the conferences marked `fetch: false` in `config/conferences.yaml`
   (sites that block robots) for new dates or deadlines; add a
   `{"kind": "conference", …}` item for real changes. Only US-held events.
8. Read `data/topic_suggestions.json`. Write `data/proposals/topics-YYYY-MM-DD.md`
   listing at most 10 keywords worth adding to `config/topics.yaml` (theme +
   reason). **Do not edit `config/` yourself** — the owner approves changes.
9. Commit and push as in step 5 (include `data/proposals/`).
