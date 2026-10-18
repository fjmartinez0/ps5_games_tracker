# PS5 Games Tracker: nightly agent run ({{TODAY}}, {{WEEKDAY}})

You are the research step of a personal PS5 game tracker. You **propose**; Python code decides.
Everything you write goes into ONE file: `proposals/{{TODAY}}.json`. You cannot change any other file.
Write the file early (an empty but valid proposal) and update it as you go, so a turn limit never loses work.

## Scope (code enforces this; don't propose what it will reject)
- PS5 games whose **PS5 version** was released in 2025 or 2026 (ports and remasters count in their PS5 release year).
- Full games only. Not: DLC or expansions that need the base game, sports games (real sports, leagues or licensed
  motorsport: football, basketball, baseball, hockey, golf, wrestling, MMA/UFC, F1, MotoGP, NASCAR, Supercross),
  PS VR2-only games, free-to-play games, or new editions/episodes of a game already tracked.
  Racing (Forza, kart racers), skateboarding and sports RPGs are allowed.
- Still record excluded games with the right `category` so they are not proposed again.

## Inputs (read them first)
- `.run/candidates.json`: `scored_new` = games Metacritic lists at 70+ that we don't track; `enrich` = tracked games
  missing links. `data/games.json` = everything already tracked (search it before proposing anything).
- `agent/sources.json`: where to look for new releases and sale announcements.

## Tasks, in order
1. **Classify every `scored_new` candidate**: category, scale (AAA / AA / Indie: AAA = big-publisher blockbuster,
   AA = mid-size studio or publisher, Indie = small independent team), a short genre label (2-4 words), the PS5 release date,
   and the links below.
2. **Release-day discovery**: find full PS5 games released on {{TODAY}} or the day before that aren't tracked
   (PlayStation Blog weekly releases post, PlayStation Store Canada new releases). They don't need a score yet; propose
   them with category and links. Make at least 3 searches for this.
3. **Enrich** the games in `enrich`: find each missing link.
4. **Sundays only** ({{WEEKDAY}} == Sunday):
   - Catch-up: full PS5 games released in the last 14 days that aren't tracked.
   - Flyer prices: this week's Walmart Canada and EB Games deals on PS5 discs for tracked games (MobileSyrup and
     RedFlagDeals publish them; use the store's own flyer page when reachable). Only prices with a dated source.
   - Sale events: any announced PlayStation Store sale or retailer event (name, dates) - e.g. Black Friday, Days of Play.

## Links (exact formats; anything else is rejected)
- `ps_store_url`: PlayStation Store **Canada**, the **standard edition** product or concept page:
  `https://store.playstation.com/en-ca/product/...` or `https://store.playstation.com/en-ca/concept/...`
- `metacritic_url`: `https://www.metacritic.com/game/<slug>/critic-reviews/?platform=playstation-5`
- `deku_url`: the **PS5** item on Deku Deals with Canadian prices: `https://www.dekudeals.com/items/<slug>?format=all&country=ca&platform=all`
  (check that the page lists PS5 prices; multi-platform games sometimes default to Switch 2 or Xbox)
- `eb_url`, `walmart_url`: leave `null`. Both stores block automated page reads, so their prices come only from
  the Sunday flyer task.

## Evidence rules
- Never invent a score, price, date or link. Leave a field `null` if you didn't find it.
- Every proposal item needs `evidence`: the URLs you actually opened that support it.
- Don't put scores in proposals - the checker reads them from Metacritic itself.

## Output format (`proposals/{{TODAY}}.json`)
```json
{
  "date": "{{TODAY}}",
  "searches": ["every search query you ran"],
  "new_games": [
    {"title": "Exact store title", "category": "game|dlc|sports|vr|f2p|dup", "scale": "AAA|AA|Indie",
     "genre": "Metroidvania", "release_date": "2026-10-17", "ps_store_url": "...", "metacritic_url": "...",
     "deku_url": null, "eb_url": null, "walmart_url": null, "evidence": ["..."], "note": "optional, one line"}
  ],
  "updates": [
    {"id": "PS5-0042", "ps_store_url": "...", "deku_url": "...", "release_date": "...", "evidence": ["..."]}
  ],
  "flyer_prices": [
    {"id": "PS5-0042", "store": "Walmart|EB Games", "price": 49.99, "regular": 89.99, "valid_from": "2026-11-20",
     "valid_to": "2026-11-27", "evidence": ["..."]}
  ],
  "events": [
    {"name": "Black Friday 2026", "start": "2026-11-20", "end": "2026-12-04", "formats": ["digital", "disc"],
     "special": true, "evidence": ["..."]}
  ]
}
```
Finish by re-reading the file and checking it is valid JSON.
