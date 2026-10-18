# PS5 Games Tracker

A nightly, self-updating list of PS5 games released in 2025–2026 that scored 70+ with critics, with
Canadian digital and disc prices, price-drop alerts for your wishlist, and discount statistics.
Runs on the Mac mini at 8 pm, publishes to GitHub Pages, alerts through ntfy.

Built on the "scheduled AI-assisted data pipeline" blueprint: **the AI proposes, code decides.**

## First-time setup (on the Mac)

1. **GitHub**: create an empty public repo named `ps5_games_tracker`. In *Settings → Pages*, set
   *Source* to **GitHub Actions**.
2. **Push the code** (from the unzipped folder):
   ```bash
   cd ps5_games_tracker
   git init -b main && git add . && git commit -m "Initial import"
   git remote add origin https://github.com/YOUR_USER/ps5_games_tracker.git
   git push -u origin main
   ```
   The token in your Keychain needs the **workflow** permission (it pushes `.github/workflows/`).
3. **Settings**: `cp config.example.env config.env`, then set the two ntfy topic names (long and random)
   and your dashboard URL. Subscribe to both topics in the ntfy iPhone app.
4. **Source test - do this before anything else**:
   ```bash
   python3 scripts/source_test.py
   ```
   It checks PlayStation Store, Metacritic, OpenCritic, Deku Deals, EB Games and Walmart from your own
   connection (~3 minutes). If anything isn't PASS, send back `.run/source_test_report.md` and a zip
   of `.run/samples/` - the page readers are adjusted from those samples.
5. **One-time catch-up** (about 1–2 hours, requests are spaced out on purpose):
   ```bash
   python3 scripts/enrich.py --limit 400      # Deku Deals + PlayStation Store links
   python3 scripts/recheck.py --backlog 400   # confirm every score on Metacritic
   python3 scripts/prices.py --all-disc       # first digital + disc prices
   python3 scripts/build_stats.py && python3 scripts/validate.py
   git add data && git commit -m "First full check" && git push
   ```
6. **Schedule it**: `bash scripts/install_mac.sh --run-now`, then `tail -f logs/$(date +%F).log`.
   Confirm three things: a commit appears, the Actions run is green, the page shows the new time.
7. **Review** `tools/rebuild_report.md`: what the rebuild dropped, corrected, and 5 games that need
   your decision (possible DLC / VR-only / free-to-play).

## How a night runs (`scripts/run_daily.sh`, 8 pm Toronto time)

| Step | Script | What it does | AI? |
|---|---|---|---|
| 1 | `git pull` | picks up wishlist changes made from the dashboard | – |
| 2 | `recheck.py` | reads Metacritic PS5 scores (OpenCritic fallback) for waiting games, unlocked scores and ~40 unverified games; moves games between statuses | no |
| 3 | `enrich.py` | finds missing Deku Deals / PlayStation Store links from the game title | no |
| 4 | `prices.py` | digital prices for every game; disc prices for wishlist games + a rotating third of the rest; opens/closes sales | no |
| 5 | `discover.py` | Metacritic's 70+ list for the year → games we don't track yet | no |
| 6 | `run_agent.sh` | Claude Code (headless, your subscription) classifies new games, finds release-day games and missing links; Sundays: 14-day catch-up, Walmart/EB flyers, sale dates. Writes only `proposals/<date>.json` | **yes** |
| 7 | `coverage_check.py` | quiet note to your phone if the agent did too little | no |
| 8 | `apply_proposals.py` | accepts/rejects each proposal item against the rules | no |
| 9 | `recheck.py --new-only`, `prices.py --only …` | checks today's new games | no |
| 10 | `build_stats.py`, `validate.py` | statistics; integrity gate (failure = nothing published + problem alert) | no |
| 11 | `git push` → GitHub Actions | validates again, stamps the time, publishes the dashboard | no |
| 12 | `notify.py` | new games + wishlist price drops (one alert per sale; >3 become one summary) | no |

## Rules (enforced in code - `scripts/common.py`, `rules.py`, `apply_proposals.py`, `validate.py`)

- **Scope**: PS5 version released in 2025 or 2026. Full games only: no DLC/expansions that need the base
  game, sports games (real sports, leagues, licensed motorsport), PS VR2-only or free-to-play games.
- **On the list**: Metacritic PS5 score 70+, or another critic aggregate (OpenCritic) when Metacritic has
  none. Games you add by hand carry an `inclusion_reason` and show "By Request".
- **Lifecycle**: found on release day → *Waiting for Scores* → listed the first night it has 70+ →
  score keeps updating for 30 days after release, then locks. Once on, always on. No 70+ within
  30 days → dropped from the waiting list (kept in the data as `expired`).
- **Prices**: digital = PlayStation Store Canada non-member price (PS Plus-only discounts ignored).
  Disc = new copies at Best Buy, Video Games Plus, PNP Games (via Deku Deals), EB Games and Walmart.
  Disc discounts are measured against the most common launch price across those stores.
- **Alerts** (wishlist only): 25%+ off, or below the lowest price ever recorded for that format
  (permanent price cuts included). One alert per sale; several disc stores the same night → one
  alert naming the cheapest.
- **Statistics**: every listed game; sports games excluded.

### Deliberate exception: Walmart
Walmart.ca's robots.txt disallows automated access (this goes against blueprint rule 7). At the owner's
request the tracker still reads Walmart product pages, **politely only**: one request per game per check,
random 6–14 s pauses, a normal browser identity, cached results. There is no fingerprint spoofing,
proxy rotation or CAPTCHA solving. If Walmart answers with a bot check, it is marked blocked for 7 days
and Sunday's agent run collects Walmart prices from published flyers instead.

## Wishlist
- On the dashboard, tap ☆: GitHub opens a pre-filled issue ("wishlist: add PS5-0042") → tap **Submit**.
  The `wishlist.yml` workflow (owner's issues only) updates `data/wishlist.json`, closes the issue and
  republishes within ~2 minutes.
- Or on the Mac: `python3 scripts/wishlist.py add "Clair Obscur"` / `remove PS5-0042` / `list`.

## Data files (`data/`, the source of truth; git history is the audit trail)
| File | Contents |
|---|---|
| `games.json` | every game ever considered, with status (`listed`, `pending_score`, `expired`, `excluded`, `review`) |
| `prices.jsonl` | append-only: one line per observed price change |
| `sales.json` | open sales + sales closed in the last 60 days |
| `checks.jsonl` | append-only: every external check (source, URL, result) |
| `events.json` | sale calendar (researched, agent-proposed, and expected dates) |
| `seed_observations.json` | sale prices researched before tracking began, each with its source |
| `stats.json` | derived numbers for the Statistics tab |
| `wishlist.json`, `meta.json` | wishlist IDs; run times and source status |

## Development
- Tests (no network needed): `python3 -m unittest discover -s tests`
- Dashboard source: `tools/dashboard.css` + `tools/dashboard.js` → `python3 tools/build_index.py`
  (add `--preview` for a standalone file with the data embedded, in `.run/preview.html`).
- `tools/seed_catalog.py`, `tools/seed_history.py`: the one-time rebuild from 2026-10-17 (kept for audit).

## Known limits
- None of these sites has an official API. The page readers try structured data first and page text
  last, and were tested against sample pages, not the live sites - hence step 4.
- Deku Deals' dated price-history charts may not be readable; if they are, history before tracking can
  be back-filled later. Until then, pre-tracking statistics rely on published sale lists.
- Sale history before 2026-10-17 covers major published sales only.
