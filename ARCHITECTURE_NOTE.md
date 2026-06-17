# Architecture Note — Browser Comparison Agent + Replay Viewer

**Task chosen:** *Compare the top 3 laptops under ₹80,000 on Flipkart* (model name, price, processor, RAM, screen size).

**Stack:** `llm_gatewayV9` (multi-provider LLM gateway) + `Session9Code` (growing-graph orchestrator + Browser skill). No third-party agent frameworks (no LangChain / LlamaIndex / CrewAI / AutoGen), as the assignment requires.

---

## 1. High-level flow

```
User Goal → Planner → Browser skill → [cascade] → Distiller → QA/Critic → Formatter → Final Table
                                          │
                              Extract / Deterministic / A11y / Vision / Gateway-Blocked
```

The orchestrator (`flow.py`) runs the agent as a **NetworkX DiGraph that grows at runtime**. The Planner emits a seed plan; nodes run in parallel when their inputs are ready; the graph extends through dynamic successors, static successors, Critic auto-insertion, and Planner re-invocation on failure. **The orchestrator was not modified** — all new behaviour plugs in through the skill catalogue (`agent_config.yaml`) and the Browser skill.

## 2. The Browser skill — a cheapest-first cascade

The Browser skill (`browser/skill.py`) is the heart of the assignment. Given a base `url` + a `goal`, it tries the cheapest layer first and escalates only when a layer returns empty/insufficient output:

| Layer | Method | Cost | When it runs |
|-------|--------|------|--------------|
| **Extract** | `trafilatura` over plain HTTP | free, no browser | static pages; skipped when the goal is interactive |
| **Deterministic** | Playwright + caller CSS selectors | cheap | only if `metadata.selectors` is supplied |
| **A11y** | Playwright + accessibility-tree text → `/v1/chat` | low (text-only) | dynamic pages, no screenshot needed |
| **Vision (Set-of-Marks)** | Screenshot + numbered boxes → `/v1/vision` | highest | when the a11y tree is insufficient |
| **Gateway-Blocked** | CAPTCHA / login / Cloudflare detection | — | returns `error_code="gateway_blocked"`; Planner recovers via a different source |

Each turn the driver enumerates interactive elements, asks Gemini for the next action(s) (`click / type / key / scroll / done`), executes them with Playwright, and re-observes. Per-turn artifacts (raw screenshot, marked screenshot, element legend) are persisted to disk.

## 3. Why a normal `web_search` + `fetch_url` can't do this

Flipkart's listing is JavaScript-rendered and the useful data only appears **after** searching, filtering by price, and sorting. Static fetch returns page chrome, not the filtered/sorted product cards. The Browser skill drives those widgets directly.

## 4. What our run actually did

- **Path chosen:** `vision` (Set-of-Marks) — the agent looked at numbered screenshots and clicked.
- **5 visible browser actions** (≥3 required): clicked the search box → typed "laptops" + Enter → clicked a filter → scrolled → settled on the top 3 (`done`). Final URL ended with `&sort=popularity`, proving a real on-site sort — not snippet scraping.
- **Distiller** turned the page text into structured fields; **Critic** (QA) checked it and passed; **Formatter** produced the final table.
- **Result:** HP 15 (₹46,700 / Ryzen 3 / 8 GB), HP 15 (₹41,838 / Core 3 / 8 GB), ASUS Vivobook 15 (₹58,990 / Ryzen 5 / 16 GB) — all 15.6", all under ₹80,000.
- **Cost:** $0.00 (free tier), captured from the V9 ledger.

## 5. The gateway (`llm_gatewayV9`)

A FastAPI multi-provider router on port 8109. Every skill call is tagged with its agent name, routed to a provider (Gemini for vision/text; Groq added for the Critic so it doesn't compete with Gemini's 15-requests/minute free limit), and logged into a SQLite cost ledger queried at `/v1/cost/by_agent`.

## 6. Replay Viewer

`replay_report.py` is an **external reporting tool** (does not touch the orchestrator). It reads the persisted session + the gateway cost ledger and emits one self-contained `replay_report.html` containing the 8 required items: original goal, Planner DAG, browser path chosen, browser actions, embedded screenshots, extracted data, final comparison table, and turn-count + cost summary.

## 7. Design choices worth noting

- **Cheapest-correct-path cascade** keeps cost near zero — Vision (the expensive layer) only fires when the text layers fail.
- **Provider separation** (Critic on Groq, browser on Gemini) removes the free-tier rate-limit failures that otherwise hit the last node in a run.
- **Honest failure handling** — a blocked gateway is a first-class `error_code`, not a crash; the Planner recovers by re-routing.
- **Best-effort Critic** — passes honest partial data, fails only fabricated/empty data, preventing pointless recovery loops.
- **Watch mode** — a `S9_BROWSER_HEADFUL=1` env toggle (added only in the Browser skill) opens a real Chrome window for live demos, without changing default headless behaviour.
