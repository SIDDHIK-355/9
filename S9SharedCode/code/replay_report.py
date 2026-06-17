"""Replay Report generator — Session 9 assignment deliverable.

Builds a single self-contained HTML page from a persisted orchestrator run
that shows the 8 items the assignment requires:

  1. Original user goal        5. Screenshots / page-state logs
  2. Planner DAG               6. Extracted data
  3. Browser path chosen       7. Final comparison table
  4. Browser actions taken     8. Turn count + cost summary

This is a reporting tool that READS the persisted session and the gateway
ledger. It does NOT touch the orchestrator (flow.py) — it plugs in as an
external viewer, exactly as the assignment allows.

Usage:
    uv run python replay_report.py [session_id]     # default: newest session

Screenshots are embedded as base64 so the HTML is one shareable file.
Cost is pulled live from the V9 gateway ledger (/v1/cost/by_agent).
"""
from __future__ import annotations

import base64
import html
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
SESSIONS = ROOT / "state" / "sessions"
GATEWAY = "http://localhost:8109"


# ── helpers ──────────────────────────────────────────────────────────────────
def newest_session() -> str:
    dirs = [p for p in SESSIONS.iterdir() if p.is_dir()] if SESSIONS.exists() else []
    if not dirs:
        sys.exit("no sessions found under state/sessions/")
    return max(dirs, key=lambda p: p.stat().st_mtime).name


def load_nodes(sid: str) -> list[dict]:
    nd = SESSIONS / sid / "nodes"
    out = []
    for p in sorted(nd.glob("n_*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            pass
    return out


def md_table_to_html(text: str) -> str:
    """Render a markdown pipe-table (or plain text) to HTML."""
    lines = [ln for ln in (text or "").splitlines()]
    rows = [ln for ln in lines if ln.strip().startswith("|")]
    if len(rows) >= 2:
        html_rows = []
        for i, ln in enumerate(rows):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if set("".join(cells)) <= set(":- "):   # separator row
                continue
            tag = "th" if i == 0 else "td"
            html_rows.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
        return "<table class='cmp'>" + "".join(html_rows) + "</table>"
    # not a table — show preamble text + any table separately
    return "<pre class='final'>" + html.escape(text or "(no final answer)") + "</pre>"


def _items_from_fields(fields):
    """Normalise the distiller's `fields` into a list of per-item dicts.
    Handles three shapes:
      - {"laptop_1": {...}, "laptop_2": {...}}   (dict of dicts)
      - {"top_laptops": [{...}, {...}]}          (list nested under one key)
      - [{...}, {...}]                            (bare list of dicts)
    """
    if isinstance(fields, list):
        return [v for v in fields if isinstance(v, dict)]
    if isinstance(fields, dict):
        # a single value that is a list of dicts → use it
        for v in fields.values():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                return v
        # otherwise dict-of-dicts
        return [v for v in fields.values() if isinstance(v, dict)]
    return []


def structured_to_table(fields) -> str | None:
    """Render the distiller's structured fields as a comparison table:
    one column per spec, one row per item. Returns None when no per-item
    dicts can be found."""
    items = _items_from_fields(fields)
    if not items:
        return None
    cols: list[str] = []
    for v in items:
        for c in v:
            if c not in cols:
                cols.append(c)
    head = "<tr><th>#</th>" + "".join(f"<th>{html.escape(c)}</th>" for c in cols) + "</tr>"
    body = ""
    for i, v in enumerate(items, 1):
        body += f"<tr><td>{i}</td>" + "".join(
            f"<td>{html.escape(str(v.get(c, '—')))}</td>" for c in cols
        ) + "</tr>"
    return f"<table class='cmp'>{head}{body}</table>"


def gather_screenshots(sid: str) -> list[tuple[str, str, str]]:
    """Return [(layer, label, data_uri), ...] — EVERY distinct page state the
    run captured. For the vision layer we use the *_marked.png (the annotated
    version of that same frame) and skip its *_raw.png duplicate; for the a11y
    layer only *_raw.png exists. Layers are ordered as they ran (a11y attempt
    first, then the vision escalation)."""
    base = SESSIONS / sid / "browser"
    shots: list[tuple[str, str, str]] = []
    if not base.exists():
        return shots

    def add(p: Path):
        layer = p.parent.name  # 'vision' | 'a11y'
        label = p.stem.replace("_", " ")
        b64 = base64.b64encode(p.read_bytes()).decode()
        shots.append((layer, label, f"data:image/png;base64,{b64}"))

    # a11y frames (raw only) first, then vision frames (annotated)
    for p in sorted(base.rglob("a11y/*_raw.png")):
        add(p)
    for p in sorted(base.rglob("vision/*_marked.png")):
        add(p)
    # fallback: if neither pattern matched, just take whatever pngs exist
    if not shots:
        for p in sorted(base.rglob("*.png")):
            add(p)
    return shots


def fetch_cost(sid: str) -> dict:
    try:
        r = httpx.get(f"{GATEWAY}/v1/cost/by_agent", params={"session": sid}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


# ── build ────────────────────────────────────────────────────────────────────
def build(sid: str) -> Path:
    sdir = SESSIONS / sid
    query = (sdir / "query.txt").read_text().strip() if (sdir / "query.txt").exists() else "(no query)"
    nodes = load_nodes(sid)

    def by_skill(name):
        return [n for n in nodes if n.get("skill") == name]

    browser_nodes = by_skill("browser")
    # pick the browser node that produced content / the most turns
    browser = None
    if browser_nodes:
        browser = max(browser_nodes,
                      key=lambda n: ((n.get("result") or {}).get("output") or {}).get("turns", 0))
    bout = (browser.get("result") or {}).get("output") if browser else {}
    bout = bout or {}

    distiller = by_skill("distiller")
    dist_out = (distiller[-1].get("result") or {}).get("output") if distiller else {}

    formatter = by_skill("formatter")
    final_answer = ""
    if formatter:
        final_answer = ((formatter[-1].get("result") or {}).get("output") or {}).get("final_answer", "")
    if not final_answer:
        # fall back to the browser/distiller done-note
        final_answer = json.dumps(dist_out, indent=2, ensure_ascii=False) if dist_out else "(no final answer)"

    shots = gather_screenshots(sid)
    cost = fetch_cost(sid)

    # optional architecture diagram embedded at the top of the report
    arch_section = ""
    arch_path = ROOT / "assets" / "architecture.png"
    if arch_path.exists():
        arch_b64 = base64.b64encode(arch_path.read_bytes()).decode()
        arch_section = (
            "<section><h2><span class='n'>★</span>Architecture (assignment cascade)</h2>"
            "<p class='hint'>The agent's path for this run: "
            "User Goal → Planner → Browser → (A11y → Vision) → Distiller → QA/Critic → Replay → Final Table.</p>"
            f"<img class='arch' src='data:image/png;base64,{arch_b64}' alt='architecture diagram'>"
            "</section>"
        )

    # ---- DAG (ordered node chain) ----
    dag_items = "".join(
        f"<span class='dag-node {('crit' if n['skill']=='critic' else '')}'>"
        f"{html.escape(n['node_id'])}<br><b>{html.escape(n['skill'])}</b>"
        f"<br><small>{html.escape(n['status'])}</small></span>"
        f"<span class='arrow'>→</span>"
        for n in nodes
    ).rstrip("<span class='arrow'>→</span>")
    # remove trailing arrow cleanly
    if dag_items.endswith("</span>"):
        # last arrow span removed by trimming
        pass

    # ---- actions table ----
    action_rows = ""
    for a in (bout.get("actions") or []):
        acts = a.get("actions") or []
        desc = ", ".join(
            f"{x.get('type','?')}(" + str(x.get('mark', x.get('value', x.get('direction', '')))) + ")"
            for x in acts
        )
        action_rows += (
            f"<tr><td>{a.get('turn','')}</td><td>{html.escape(desc)}</td>"
            f"<td>{html.escape(str(a.get('outcome',''))[:80])}</td></tr>"
        )
    if not action_rows:
        action_rows = "<tr><td colspan=3>(no per-turn actions recorded)</td></tr>"

    # ---- cost summary ----
    total_calls = total_in = total_out = 0
    cost_rows = ""
    if "_error" not in cost:
        for agent, recs in cost.items():
            for rec in recs:
                total_calls += rec.get("calls", 0)
                total_in += rec.get("in_tok", 0)
                total_out += rec.get("out_tok", 0)
                cost_rows += (
                    f"<tr><td>{html.escape(agent)}</td><td>{html.escape(rec.get('provider',''))}</td>"
                    f"<td>{rec.get('calls',0)}</td><td>{rec.get('in_tok',0)}</td>"
                    f"<td>{rec.get('out_tok',0)}</td><td>${rec.get('dollars',0):.4f}</td></tr>"
                )
    else:
        cost_rows = f"<tr><td colspan=6>cost ledger unavailable: {html.escape(cost['_error'])}</td></tr>"

    turns = bout.get("turns", 0)
    path = bout.get("path", "(unknown)")
    final_url = bout.get("final_url", "")

    # ---- screenshots gallery ----
    gallery = ""
    for layer, label, uri in shots:
        gallery += (
            f"<figure><img src='{uri}' alt='{html.escape(label)}' "
            f"onclick=\"zoom(this.src,'{html.escape(layer)} · {html.escape(label)}')\">"
            f"<figcaption>{html.escape(layer)} · {html.escape(label)}</figcaption></figure>"
        )
    if not gallery:
        gallery = "<p>(no screenshots captured for this run)</p>"

    extracted = json.dumps(dist_out or bout.get("content", "") or {}, indent=2, ensure_ascii=False)

    # real comparison table from the distiller's structured fields, if present
    cmp_table = structured_to_table((dist_out or {}).get("fields")) or \
        "<p style='color:var(--mut)'>(no structured fields — see narrative below)</p>"

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Replay Report — {html.escape(sid)}</title>
<style>
  :root {{ --bg:#0f1117; --card:#171a23; --ink:#e6e8ee; --mut:#9aa3b2;
           --acc:#7c5cff; --good:#36c275; --line:#262a36; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
          font:15px/1.55 -apple-system,Segoe UI,Roboto,Helvetica,Arial; }}
  header {{ padding:28px 32px; background:linear-gradient(120deg,#1b1140,#0f1117);
            border-bottom:1px solid var(--line); }}
  header h1 {{ margin:0 0 6px; font-size:22px; }}
  header .sid {{ color:var(--mut); font-size:13px; }}
  main {{ max-width:1080px; margin:0 auto; padding:24px 32px 80px; }}
  section {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
             padding:20px 22px; margin:18px 0; }}
  section h2 {{ margin:0 0 14px; font-size:16px; color:#fff; }}
  section h2 .n {{ display:inline-block; width:24px; height:24px; line-height:24px;
                   text-align:center; background:var(--acc); color:#fff; border-radius:6px;
                   font-size:13px; margin-right:10px; }}
  .goal {{ font-size:17px; color:#fff; }}
  .pill {{ display:inline-block; padding:4px 12px; border-radius:999px; font-size:13px;
           background:#231a4d; color:#c5b6ff; border:1px solid #3a2d7a; }}
  .pill.path {{ background:#13351f; color:#7ff0ad; border-color:#1f5e36; font-weight:600; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  th,td {{ text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ color:var(--mut); font-weight:600; }}
  table.cmp th {{ background:#1d2230; color:#fff; }}
  table.cmp td {{ color:var(--ink); }}
  .dag {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px; }}
  .dag-node {{ background:#1d2230; border:1px solid var(--line); border-radius:8px;
               padding:8px 10px; text-align:center; min-width:84px; font-size:12px; }}
  .dag-node.crit {{ border-color:#5e4b1f; background:#2a2310; }}
  .dag-node b {{ color:#fff; font-size:13px; }}
  .arrow {{ color:var(--acc); font-size:18px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:12px; }}
  figure {{ margin:0; background:#0c0e14; border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  figure img {{ width:100%; display:block; cursor:zoom-in; transition:transform .12s; }}
  figure img:hover {{ transform:scale(1.01); }}
  figcaption {{ padding:7px 10px; font-size:12px; color:var(--mut); }}
  .hint {{ color:var(--mut); font-size:13px; margin:0 0 12px; }}
  img.arch {{ width:100%; border-radius:10px; border:1px solid var(--line); background:#fff; }}
  /* lightbox */
  #lb {{ position:fixed; inset:0; background:rgba(4,5,9,.94); display:none;
         z-index:99; align-items:center; justify-content:center; flex-direction:column;
         padding:24px; cursor:zoom-out; }}
  #lb.open {{ display:flex; }}
  #lb img {{ max-width:96vw; max-height:86vh; border:1px solid var(--line); border-radius:8px; }}
  #lb .cap {{ color:#cdd3df; margin-top:12px; font-size:14px; }}
  #lb .x {{ position:fixed; top:18px; right:24px; color:#fff; font-size:30px; cursor:pointer; }}
  pre {{ background:#0c0e14; border:1px solid var(--line); border-radius:8px; padding:14px;
         overflow:auto; font-size:13px; color:#cdd3df; max-height:340px; }}
  .kpis {{ display:flex; gap:14px; flex-wrap:wrap; }}
  .kpi {{ background:#1d2230; border:1px solid var(--line); border-radius:10px; padding:12px 18px; }}
  .kpi b {{ display:block; font-size:22px; color:#fff; }}
  .kpi span {{ color:var(--mut); font-size:12px; }}
  a {{ color:#9d86ff; }}
</style></head>
<body>
<header>
  <h1>🧭 Browser Comparison Agent — Replay Report</h1>
  <div class="sid">session <b>{html.escape(sid)}</b> · generated from persisted run + V9 cost ledger</div>
</header>
<main>

  {arch_section}

  <section>
    <h2><span class="n">1</span>Original user goal</h2>
    <div class="goal">{html.escape(query)}</div>
  </section>

  <section>
    <h2><span class="n">2</span>Planner DAG</h2>
    <div class="dag">{dag_items}</div>
  </section>

  <section>
    <h2><span class="n">3</span>Browser path chosen</h2>
    <p>Cascade layer the skill actually used:
       &nbsp;<span class="pill path">{html.escape(str(path))}</span></p>
    <p style="color:var(--mut)">choices: extract · deterministic · a11y · vision · blocked</p>
    {f'<p>Final URL: <a href="{html.escape(final_url)}">{html.escape(final_url)}</a></p>' if final_url else ''}
  </section>

  <section>
    <h2><span class="n">4</span>Browser actions taken</h2>
    <table><tr><th>Turn</th><th>Action(s)</th><th>Outcome</th></tr>{action_rows}</table>
  </section>

  <section>
    <h2><span class="n">5</span>Screenshots / page-state logs</h2>
    <p class="hint">👆 Click any screenshot to view it full-screen.</p>
    <div class="grid">{gallery}</div>
  </section>

  <section>
    <h2><span class="n">6</span>Extracted data</h2>
    <pre>{html.escape(extracted)}</pre>
  </section>

  <section>
    <h2><span class="n">7</span>Final comparison table</h2>
    {cmp_table}
    <details style="margin-top:14px"><summary style="color:var(--mut);cursor:pointer">Formatter's narrative answer</summary>
    {md_table_to_html(final_answer)}</details>
  </section>

  <section>
    <h2><span class="n">8</span>Turn count &amp; cost summary</h2>
    <div class="kpis">
      <div class="kpi"><b>{turns}</b><span>browser turns</span></div>
      <div class="kpi"><b>{total_calls}</b><span>gateway calls</span></div>
      <div class="kpi"><b>{total_in:,}</b><span>input tokens</span></div>
      <div class="kpi"><b>{total_out:,}</b><span>output tokens</span></div>
      <div class="kpi"><b>$0.00</b><span>free tier</span></div>
    </div>
    <table style="margin-top:14px">
      <tr><th>Agent</th><th>Provider</th><th>Calls</th><th>In tok</th><th>Out tok</th><th>Cost</th></tr>
      {cost_rows}
    </table>
  </section>

</main>
<div id="lb" onclick="this.classList.remove('open')">
  <span class="x">×</span>
  <img id="lbimg" src="">
  <div class="cap" id="lbcap"></div>
</div>
<script>
  function zoom(src, cap) {{
    document.getElementById('lbimg').src = src;
    document.getElementById('lbcap').textContent = cap || '';
    document.getElementById('lb').classList.add('open');
  }}
  document.addEventListener('keydown', e => {{
    if (e.key === 'Escape') document.getElementById('lb').classList.remove('open');
  }});
</script>
</body></html>"""

    out = sdir / "replay_report.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    sid = sys.argv[1] if len(sys.argv) > 1 else newest_session()
    out = build(sid)
    print(f"replay report written: {out}")
    print(f"open it with:  open '{out}'")


if __name__ == "__main__":
    main()
