"""Quietly flag a weak agent run (never blocks the pipeline)."""
import datetime as dt

from common import PROPOSALS, RUN, load_json, today

MIN_SEARCHES = 3


def main():
    prop = load_json(PROPOSALS / f"{today()}.json")
    cand = load_json(RUN / "candidates.json", {}) or {}
    problems = []
    if prop is None:
        problems.append("no proposal file was written")
    else:
        if len(prop.get("searches", [])) < MIN_SEARCHES:
            problems.append(f"only {len(prop.get('searches', []))} searches (minimum {MIN_SEARCHES})")
        proposed = {x.get("title", "").lower() for x in prop.get("new_games", [])}
        missed = [c["title"] for c in cand.get("scored_new", []) if c["title"].lower() not in proposed]
        if missed:
            problems.append(f"{len(missed)} Metacritic candidates not classified: {', '.join(missed[:5])}")
        if dt.date.fromisoformat(today()).weekday() == 6 and not prop.get("flyer_prices"):
            problems.append("Sunday run found no Walmart/EB Games flyer prices")
    print("coverage: " + ("; ".join(problems) if problems else "ok"))
    (RUN / "coverage.txt").write_text("; ".join(problems))


if __name__ == "__main__":
    main()
