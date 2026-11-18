# Thermal Materials Academic Radar

A daily research radar for phonon and thermal transport, Boltzmann transport,
machine-learned interatomic potentials, interfacial heat transfer, electronics
thermal management and cooling, and the conferences and special issues that
publish them.

**Site:** https://benz666.github.io/thermal-materials-academic-radar/

Three pages, each a year → month → week timeline of gallery cards. Opening a
card shows a short **What / Why / How / Impact** summary and the original link.

| Page | Sources |
|---|---|
| Papers & Preprints | arXiv (6 categories + targeted queries), Crossref (32 journals), OpenAlex search, new works by 35 watched authors |
| Industry & Tools | Company / trade-press RSS, GitHub releases of 21 codes, fast-rising GitHub repositories |
| Conferences & Calls | 21 US conferences (daily page-change watch), Nature-family calls for papers, WikiCFP, weekly web search for other publishers |

## How it runs

1. **GitHub Actions, daily 11:00 UTC, no LLM** — fetch, deduplicate, score
   against `config/topics.yaml`, cap per day, write rule-based summaries,
   archive to `data/archive/<page>/<YYYY-MM>.json`, build `public/`, deploy to Pages.
2. **Claude step in the same Action (Claude Code, Sonnet 5.5)** — when the
   `CLAUDE_CODE_OAUTH_TOKEN` secret is set, reads `data/llm_queue.json`, writes
   summaries and weekly special-issue / conference checks to `data/llm_out/`
   (see `CLAUDE_ROUTINE.md`), which are merged before deploying. Without the
   secret the site deploys with rule-based summaries.

## Configure

- `config/topics.yaml` — themes, keywords, context gates, project mapping
- `config/sources.yaml` — feeds, journals, searches, repos, call pages
- `config/conferences.yaml` — conference watch list and verified dates
- `config/authors.yaml` — watched authors (`python -m radar.authors` resolves OpenAlex ids)
- `config/profile.md` — public research profile used for "Impact on me"

## Run locally

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m radar.run           # fetch + build
.venv/bin/python -m radar.run --build   # rebuild only
python -m http.server -d public 8000    # preview at http://localhost:8000
```

Summaries marked *rules* are extracted automatically from abstracts; always
check the original source.
