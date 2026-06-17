# Browser Comparison Agent + Replay Viewer — Session 9 Assignment

A browser-capable AI agent that completes a **real comparison task on the web** — it
searches, filters, and sorts a live, JavaScript-rendered shopping site, extracts the
results, and produces a **replay report** of the whole run.

**Chosen task:** *Compare the top 3 laptops under ₹80,000 on Flipkart* (model name,
price, processor, RAM, screen size).

---

## 1. The problem

A normal `web_search` + `fetch_url` can only read **static** pages. It fails on modern
sites where the useful data only appears **after** you interact — search, filter by
price, sort, open product cards, switch tabs. Flipkart's laptop listing is exactly
this kind of page: JavaScript-rendered, with filter/sort widgets, where the right
laptops only surface after driving the page.

This project demonstrates work `fetch_url` **cannot** do: a real agent that drives a
live browser and produces a verifiable, replayable result.

## 2. What the agent does (architecture)

```
User Goal → Planner → Browser skill → [cheapest correct path] → Distiller → QA/Critic → Replay Viewer → Final Table
                                            │
                          Extract / Deterministic / A11y / Vision / Gateway-Blocked
```

- **Planner** decomposes the goal into a small graph of skills (the DAG).
- **Browser skill** opens a real headless Chrome and tries the **cheapest layer first**,
  escalating only when needed:

  | Layer | Method | When |
  |-------|--------|------|
  | Extract | `trafilatura` over plain HTTP | static pages |
  | Deterministic | Playwright + CSS selectors | only if selectors supplied |
  | A11y | accessibility-tree text → `/v1/chat` | dynamic pages, no screenshot |
  | **Vision (Set-of-Marks)** | screenshot + numbered boxes → `/v1/vision` | when a11y is insufficient |
  | Gateway-Blocked | CAPTCHA / login detection | returns `gateway_blocked`, Planner recovers |

- **Distiller** turns the raw page text into structured fields.
- **QA / Critic** validates the data (best-effort: passes honest partial data, fails
  fabricated/empty data).
- **Formatter** writes the final comparison table.
- **Replay Viewer** (`replay_report.py`) gathers everything into one HTML page.

> **The orchestrator (`flow.py`) is NOT modified.** All new behaviour plugs in through
> the skill catalogue (`agent_config.yaml`, prompt files) and the Browser skill — as the
> assignment requires. No third-party agent frameworks (no LangChain / LlamaIndex /
> CrewAI / AutoGen).

## 3. What our verified run did (`s8-f6948e73`)

| Step | Node | Result |
|------|------|--------|
| 1 | Planner | built the DAG |
| 2 | **Browser** | path = **vision**, 5 actions: click search → type "laptops" + Enter → click filter → scroll → done. Final URL ended `&sort=popularity` (real sort) |
| 3 | Distiller | extracted 3 laptops with all 5 fields |
| 4 | Formatter | final comparison table |
| 5 | **Critic** | **PASS** — all requested fields present |

**5 visible browser actions** (≥3 required), real search + filter + sort, **not** snippet
scraping. Cost: **$0.00** (free tier).

### Final comparison table

| # | Model | Price | Processor | RAM | Screen |
|---|-------|-------|-----------|-----|--------|
| 1 | HP 15 (MSO'24, Ryzen 3 7320U) | ₹46,700 | AMD Ryzen 3 Quad Core | 8 GB | 15.6" |
| 2 | HP 15 (i3 14th Gen, Core 3 100U) | ₹41,838 | Intel Core 3 | 8 GB | 15.6" |
| 3 | ASUS Vivobook 15 (2026) | ₹58,990 | AMD Ryzen 5 Hexa Core | 16 GB | 15.6" |

## 4. Repository layout

```
.
├── llm_gatewayV9/            # FastAPI multi-provider LLM gateway (port 8109)
├── S9SharedCode/
│   ├── code/
│   │   ├── flow.py           # orchestrator (UNMODIFIED)
│   │   ├── skills.py         # skill registry + dispatch
│   │   ├── agent_config.yaml # skill catalogue
│   │   ├── prompts/          # per-skill prompts (planner, critic, …)
│   │   ├── browser/          # the Browser skill + layered drivers
│   │   ├── replay_report.py  # ← Replay Viewer (HTML generator)
│   │   └── state/sessions/   # persisted runs (graphs, nodes, screenshots)
│   └── run_demo.sh           # demo runner
├── SUBMISSION_BACKUP/        # the graded run + report + screenshots
│   ├── s8-f6948e73_clean_run/replay_report.html
│   └── SCREENSHOTS/          # step1…step5 (search → filter → sort → result)
├── ARCHITECTURE_NOTE.md      # short architecture note
└── README.md                 # this file
```

## 5. Setup & run

**Prerequisites:** Python 3.12, `uv`, a free Gemini key (and optional free Groq key).

```bash
# 1. keys — create /<repo>/.env
GEMINI_API_KEY=...          # required (Google AI Studio, free)
GROQ_API_KEY=...            # optional — runs the Critic so it doesn't hit Gemini's 15/min cap

# 2. start the gateway (keep this terminal open)
cd llm_gatewayV9
uv run python main.py        # → http://localhost:8109

# 3. install the browser engine (one-time)
cd ../S9SharedCode/code
uv run playwright install chromium

# 4. run the agent
uv run python flow.py "Open the Flipkart homepage at https://www.flipkart.com, use the search box to search for laptops, filter by price under 80000, sort the list, and give the top 3 laptops with model name, price, processor, RAM, and screen size."

# 5. build the replay report (newest run, or pass a session id)
uv run python replay_report.py
open state/sessions/<session_id>/replay_report.html
```

**Watch it live:** prefix the run with `S9_BROWSER_HEADFUL=1 S9_BROWSER_SLOWMO_MS=1500`
to open a real Chrome window and watch the search / filter / sort happen.

## 6. The Replay Report (the deliverable)

`replay_report.py` reads a persisted session + the gateway cost ledger and emits a single
self-contained `replay_report.html` with the 8 required items:

1. Original user goal  2. Planner DAG  3. Browser path chosen  4. Browser actions
5. Screenshots (click to zoom)  6. Extracted data  7. Final comparison table
8. Turn count + cost summary

## 7. Submission artifacts

- 🎥 **YouTube demo:** _<add link>_
- 💻 **GitHub repo:** _<add link>_
- 📑 **Replay trace/report:** `SUBMISSION_BACKUP/s8-f6948e73_clean_run/replay_report.html`
- 🖼️ **Screenshots:** `SUBMISSION_BACKUP/SCREENSHOTS/`
- 📊 **Final comparison output:** see §3 above
- 📝 **Architecture note:** `ARCHITECTURE_NOTE.md`

## 8. Notable engineering decisions

- **Cheapest-correct-path cascade** keeps cost ~$0 — Vision (expensive) only fires when
  the text layers fail.
- **Provider separation** — the Critic runs on Groq so it doesn't exhaust Gemini's free
  15-requests/minute limit (which previously caused `503`s on the last node).
- **Best-effort Critic** — passes honest partial data, fails only fabricated/empty data,
  preventing pointless recovery loops the strict version caused.
- **Watch mode** — a `S9_BROWSER_HEADFUL` env toggle added only in the Browser skill,
  default stays headless.
