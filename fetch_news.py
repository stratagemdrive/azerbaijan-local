"""
fetch_news.py
Fetches Azerbaijani news headlines from RSS feeds (all English-language sources),
categorizes each story, and maintains a rolling 7-day window of up to 20
stories per category.
Output: docs/azerbaijan_news.json
No APIs, no translation libraries required — all feeds publish in English.
"""

import json
import re
import calendar
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from dateutil import parser as dateparser

# ── Configuration ─────────────────────────────────────────────────────────────

OUTPUT_PATH = Path("docs/azerbaijan_news.json")
MAX_STORIES_PER_CATEGORY = 20
MAX_AGE_DAYS = 7

FEEDS = [
    {
        "source": "AZERTAC",
        "url": "https://azertag.az/en/rss-all",
        "lang": "en",
    },
    {
        "source": "Trend News Agency",
        "url": "https://en.trend.az/feeds/index.rss",
        "lang": "en",
    },
    {
        "source": "Azernews",
        "url": "https://www.azernews.az/feed.php",
        "lang": "en",
    },
    {
        "source": "Day.az",
        "url": "https://news.day.az/rss",
        "lang": "en",
    },
    {
        "source": "JAMnews",
        "url": "https://jam-news.net/feed",
        "lang": "en",
    },
    {
        "source": "Caliber.az",
        "url": "https://caliber.az/feed",
        "lang": "en",
    },
]

CATEGORIES = ["Diplomacy", "Military", "Energy", "Economy", "Local Events"]

# ── Keyword maps ──────────────────────────────────────────────────────────────

CATEGORY_KEYWORDS = {
    "Diplomacy": [
        r"\bdiplomat\w*\b", r"\bambassador\b", r"\btreaty\b", r"\bsanction\w*\b",
        r"\bforeign (affairs|minister|policy|relations)\b",
        r"\bministry of foreign affairs\b",
        r"\bbayramov\b",  # Foreign Minister Jeyhun Bayramov
        r"\bnato\b", r"\bunited nations\b", r"\bun\b", r"\beu\b",
        r"\beuropean (union|commission|parliament|council)\b",
        r"\bembassy\b", r"\bconsulate\b", r"\bconsul\w*\b",
        r"\btrade (deal|agreement|talks|negotiation)\b",
        r"\bsummit\b", r"\bpeace (deal|talks|process|treaty|agreement)\b",
        r"\bbilateral\b", r"\bmultilateral\b",
        r"\bimf\b", r"\bwto\b", r"\bg7\b", r"\bg20\b",
        r"\bcop29\b",  # Azerbaijan hosted COP29 in 2024
        r"\bcis\b", r"\bsco\b", r"\bosce\b",
        r"\baliyev.*(visit|trip|meeting|summit|talks|received|met)\b",
        r"\bazerbaijan.*(armenia|turkey|russia|iran|usa|united states|france|eu|georgia|israel|pakistan)\b",
        r"\bpeace (process|negotiations?|framework|treaty)\b",
        r"\bnormalization\b", r"\bborder (delimitation|talks|agreement|delineation)\b",
        r"\bkarabakh.*(peace|agreement|status|settlement)\b",
        r"\bcooperation (agreement|deal|framework|protocol|memorandum)\b",
        r"\binternational (relations|law|court|community|organization)\b",
        r"\bcouncil of europe\b", r"\bminsk group\b",
        r"\btrans-caspian\b", r"\bmiddle corridor\b",
        r"\bzangezur corridor\b",
    ],
    "Military": [
        r"\bmilitary\b", r"\bdefence\b", r"\bdefense\b",
        r"\bminister of defense\b", r"\bhasanov\b",  # Defense Minister
        r"\bsoldier\w*\b", r"\btroops?\b", r"\bnavy\b", r"\barmy\b", r"\bair force\b",
        r"\bweapon\w*\b", r"\barmament\w*\b", r"\barms (deal|sale|transfer|supply)\b",
        r"\bdrone\w*\b", r"\bmissile\w*\b", r"\bartillery\b", r"\bbyraktar\b",
        r"\bwar\b", r"\bconflict\b", r"\bbattle\b", r"\bcombat\b",
        r"\bterror\w*\b", r"\bnational security\b", r"\bintelligence\b",
        r"\bexplosion\b", r"\bmunition\w*\b", r"\bshelling\b",
        r"\bceasefire\b", r"\bincident\b", r"\bprovocation\b",
        r"\bpeacekeep\w*\b", r"\bdeployment\b",
        r"\bmilitary (exercise|drill|base|aid|cooperation|parade)\b",
        r"\bsecurity (forces|operation|threat|situation)\b",
        r"\bsniper\b", r"\bmine\b", r"\blandmine\b",
        r"\bveteran\w*\b", r"\bpow\b", r"\bprisoner of war\b",
        r"\bkarabakh.*(war|conflict|occupation|offensive|liberat)\b",
        r"\b44.day war\b", r"\bseptember 2023\b",
        r"\bstate border service\b", r"\bborder (guard|incident|violation)\b",
        r"\bdefense (budget|spending|ministry|cooperation|industry)\b",
        r"\binternal troops\b", r"\bspecial forces\b",
    ],
    "Energy": [
        r"\benergy\b", r"\boil\b", r"\bnatural gas\b", r"\bpipeline\b",
        r"\blng\b", r"\brenewable\b", r"\bsolar\b",
        r"\bwind (power|energy|farm|turbine)\b",
        r"\bhydro\b", r"\bhydroelectric\w*\b",
        r"\bnuclear (plant|power|energy|reactor)\b",
        r"\belectricit\w*\b", r"\bpower (grid|plant|outage|cut|station)\b",
        r"\bblackout\b", r"\bpower (shortage|supply|generation|transmission)\b",
        r"\bcarbon\b", r"\bclimate\b", r"\bemission\w*\b", r"\bnet.zero\b",
        r"\bfuel\b", r"\bgas (price|supply|shortage|field|export)\b",
        r"\bgreen energy\b", r"\bclean energy\b", r"\benergy transition\b",
        r"\benergy (security|independence|crisis|cooperation|deal|hub)\b",
        r"\bsocar\b",  # State Oil Company of Azerbaijan
        r"\bsocar.*gas\b", r"\bsocar.*oil\b",
        r"\bshah deniz\b", r"\bace\b", r"\bscp\b", r"\bsouth caucasus pipeline\b",
        r"\btanap\b", r"\btap\b", r"\bbaku.tbilisi.ceyhan\b", r"\bbtc\b",
        r"\bsouthern gas corridor\b",
        r"\bcaspian (oil|gas|pipeline|energy)\b",
        r"\bministry of energy\b",
        r"\belectric (vehicle|car|grid)\b",
        r"\bgeothermal\b", r"\bbiomass\b",
        r"\bmining\b", r"\bmineral\w*\b", r"\bgold (mine|mining|deposit)\b",
        r"\bcopper (mine|mining)\b",
        r"\bcop29\b",  # Azerbaijan hosted global climate summit
    ],
    "Economy": [
        r"\beconom\w*\b", r"\bbudget\b", r"\bgdp\b", r"\binflation\b",
        r"\binterest rate\b", r"\bcentral bank\b", r"\brecession\b",
        r"\btrade (war|tariff|deficit|surplus|balance)\b", r"\btariff\w*\b",
        r"\bjob\w*\b", r"\bunemployment\b", r"\blabou?r\b", r"\bwage\w*\b",
        r"\bhousing (market|price|crisis)\b", r"\breal estate\b",
        r"\bexport\w*\b", r"\bimport\w*\b", r"\bcost of living\b",
        r"\bfood (price|security|inflation)\b",
        r"\btax\w*\b", r"\bfiscal\b", r"\bdeficit\b", r"\bdebt\b",
        r"\bimf\b", r"\bworld bank\b", r"\bebrd\b", r"\badb\b",
        r"\binvestment\w*\b", r"\bforeign (investment|capital|direct investment)\b",
        r"\bfdi\b", r"\bstartup\b", r"\btech (sector|industry|company)\b",
        r"\btourism\b", r"\btourist\w*\b",
        r"\bmanat\b",  # Azerbaijani currency
        r"\bcurrency\b", r"\bexchange rate\b", r"\bremittance\w*\b",
        r"\bgrowth\b", r"\bgross domestic\b",
        r"\bstatistics\b", r"\bpoverty\b", r"\bincome\b",
        r"\bfinance (minister|ministry)\b",
        r"\bmarket\w*\b", r"\bstock (market|exchange)\b",
        r"\bbank(ing)?\b", r"\bcredit\b", r"\bloan\b",
        r"\btrade (route|corridor|hub|zone)\b",
        r"\bfree (trade|economic) zone\b", r"\balat\b",
        r"\bconstruction\b", r"\binfrastructure (project|investment|development)\b",
        r"\bkarabakh.*(reconstruction|development|investment|rebuild)\b",
        r"\bliberated (territories|regions)\b",
        r"\bstate budget\b", r"\brevenue\b", r"\bprofit\b",
    ],
    "Local Events": [
        r"\bcommunity\b", r"\btown hall\b", r"\bfestival\b", r"\bparade\b",
        r"\bfire\b", r"\bflood\b", r"\baccident\b", r"\bcrash\b",
        r"\bcrime\b", r"\barrest\b", r"\bpolice\b", r"\bcourt\b",
        r"\bjudge\b", r"\bverdict\b", r"\btrial\b", r"\bsentence\b",
        r"\bmunicip\w*\b", r"\bmayor\b", r"\bcouncil\b",
        r"\bschool\b", r"\buniversity\b", r"\bcollege\b", r"\bhospital\b",
        r"\bhealth (care|system|ministry|reform)\b",
        r"\bweather\b", r"\bstorm\b", r"\bearthquake\b", r"\blandslide\b",
        r"\bwildfire\b", r"\bdrought\b", r"\bflood\w*\b",
        r"\bfundraiser\b", r"\bcharity\b", r"\bvolunteer\b",
        r"\bculture\b", r"\barts?\b", r"\bheritage\b",
        r"\bcelebration\b", r"\bholiday\b", r"\bnovruz\b",
        r"\bsport\w*\b", r"\bfootball\b", r"\bwrestling\b", r"\bjudo\b",
        r"\binfrastructure\b", r"\broad (repair|closure|construction)\b",
        r"\btransit\b", r"\bbus\b", r"\btrain\b", r"\bmetro\b",
        r"\bbaku\b", r"\bganja\b", r"\bsumgait\b", r"\bmingachevir\b",
        r"\bnakhchivan\b", r"\bsheki\b", r"\bshusha\b",
        r"\bregion\b", r"\bdistrict\b", r"\bvillage\b",
        r"\bmosque\b", r"\bchurch\b",
        r"\belection\w*\b", r"\bvote\b", r"\bparliament\b", r"\bmilli majlis\b",
        r"\bopposition\b", r"\bprotest\b", r"\bdemonstration\b",
        r"\bcorrupt\w*\b", r"\bscandal\b", r"\bpolitical prisoner\b",
        r"\bhuman rights\b", r"\bpress freedom\b", r"\bjournalist\b",
    ],
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateparser.parse(raw)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass
    return None


def score_category(text: str) -> str:
    text_lower = text.lower()
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, patterns in CATEGORY_KEYWORDS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                scores[cat] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Local Events"


def fetch_feed(source: str, url: str) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; StratagemdrivBot/1.0; "
            "+https://stratagemdrive.github.io/azerbaijan-local/)"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    stories = []
    cutoff = now_utc() - timedelta(days=MAX_AGE_DAYS)

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
    except Exception as exc:
        print(f"[WARN] Could not fetch {url}: {exc}")
        return stories

    for entry in feed.entries:
        pub_dt = parse_date(entry)
        if pub_dt is None or pub_dt < cutoff:
            continue

        title = (entry.get("title") or "").strip()
        link  = (entry.get("link")  or "").strip()
        if not title or not link:
            continue

        summary = entry.get("summary") or entry.get("description") or ""
        category = score_category(f"{title} {summary[:400]}")

        stories.append({
            "title":          title,
            "source":         source,
            "url":            link,
            "published_date": pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "category":       category,
        })

    return stories


def load_existing() -> dict[str, list[dict]]:
    if OUTPUT_PATH.exists():
        try:
            with OUTPUT_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "stories" in data:
                by_cat: dict[str, list[dict]] = {c: [] for c in CATEGORIES}
                for story in data["stories"]:
                    cat = story.get("category")
                    if cat in by_cat:
                        by_cat[cat].append(story)
                return by_cat
        except Exception as exc:
            print(f"[WARN] Could not parse existing JSON: {exc}")
    return {c: [] for c in CATEGORIES}


def merge_stories(
    existing: dict[str, list[dict]],
    fresh: list[dict],
) -> dict[str, list[dict]]:
    cutoff = now_utc() - timedelta(days=MAX_AGE_DAYS)

    for cat in CATEGORIES:
        existing[cat] = [
            s for s in existing[cat]
            if dateparser.parse(s["published_date"]).replace(tzinfo=timezone.utc) >= cutoff
        ]

    known_urls: dict[str, set[str]] = {
        cat: {s["url"] for s in existing[cat]} for cat in CATEGORIES
    }

    for story in fresh:
        cat = story["category"]
        if story["url"] in known_urls.get(cat, set()):
            continue
        existing[cat].append(story)
        known_urls[cat].add(story["url"])

    for cat in CATEGORIES:
        existing[cat].sort(key=lambda s: s["published_date"], reverse=True)
        existing[cat] = existing[cat][:MAX_STORIES_PER_CATEGORY]

    return existing


def write_output(by_cat: dict[str, list[dict]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_stories = [s for stories in by_cat.values() for s in stories]
    payload = {
        "generated_at":  now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "country":        "Azerbaijan",
        "total_stories":  len(all_stories),
        "categories":     CATEGORIES,
        "stories":        all_stories,
    }
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Wrote {len(all_stories)} stories to {OUTPUT_PATH}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"[INFO] Starting Azerbaijan news fetch at {now_utc().isoformat()}")

    seen_urls: set[str] = set()
    fresh_stories: list[dict] = []

    for feed_cfg in FEEDS:
        print(f"[INFO] Fetching {feed_cfg['source']} → {feed_cfg['url']}")
        stories = fetch_feed(feed_cfg["source"], feed_cfg["url"])
        unique = [s for s in stories if s["url"] not in seen_urls]
        seen_urls.update(s["url"] for s in unique)
        print(f"       Found {len(unique)} unique recent stories")
        fresh_stories.extend(unique)

    print(f"[INFO] Total fresh stories collected: {len(fresh_stories)}")

    existing = load_existing()
    merged   = merge_stories(existing, fresh_stories)
    write_output(merged)


if __name__ == "__main__":
    main()
