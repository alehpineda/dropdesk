#!/usr/bin/env python3
"""MTG Drops static site builder. Usage: python3 build.py  -> dist/"""
import json, html, os, re, shutil, urllib.parse, datetime, hashlib
AFFILIATE_ID = ""  # TCGplayer affiliate/partner id; blank = plain links
SITE_URL = "https://mtgdrops.com"
BASE = ""  # site served at the domain root (mtgdrops.com)
CONTEXT7_ASK_URL = "https://context7.com/api/v2/ask?siteKey=ask_1bb1972ef8ba0c552c4ec616"
CONTEXT7_SITE_KEY = CONTEXT7_ASK_URL.split("siteKey=", 1)[1]
CONTEXT7_NOTE = f"This site has a search endpoint: {CONTEXT7_ASK_URL}&query=<URL-encoded question>. It returns documentation that answers the question, with a source link for each part. No API key is needed. If nothing matches, it says so."
E = html.escape
data = sorted(json.load(open("data/releases.json")), key=lambda r: r["release_date"])
types = sorted({r["type"] for r in data})
CSS = """body{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e8e8ea}a{color:#7cc4ff}
header,footer{padding:1rem;background:#171a21}header a{margin-right:1rem}main{max-width:860px;margin:auto;padding:1rem}
.card{background:#1c2029;border-radius:10px;padding:1rem;margin:.6rem 0}.t{font-size:.75rem;background:#2d3546;padding:2px 8px;border-radius:9px}
.st{font-size:.75rem;color:#f3c26b}.f button{margin:.2rem;padding:.4rem .7rem;border-radius:8px;border:0;background:#2d3546;color:#fff}
.f button.on{background:#3a7bd5}input{padding:.5rem;border-radius:6px;border:0}form button{padding:.5rem 1rem}
a.amz{display:inline-block;padding:.4rem .8rem;border-radius:8px;background:#ff9900;color:#111;text-decoration:none;font-weight:600}.disc{color:#9aa}.about{color:#9aa;margin:-.4rem 0 .8rem}"""
def tcg(name):  # callers pass a release's optional tcg_query (explicit TCGplayer search term) or its name
    u = "https://www.tcgplayer.com/search/magic/product?q=" + urllib.parse.quote(name)
    return u + ("&partner=" + urllib.parse.quote(AFFILIATE_ID) if AFFILIATE_ID else "")
AMAZON_TAG = "mtgdrops-20"  # Amazon Associates tag
DISCLOSURE = "As an Amazon Associate, MTG Drops earns from qualifying purchases. Some links on this site are affiliate links."
def amazon(r):
    # Direct /dp/ link only when an owner-approved ASIN with recorded evidence (amazon_evidence) is present;
    # otherwise a search URL, which never goes dead. Only purchasable retail products carry amazon_query.
    if r.get("amazon_asin") and r.get("amazon_evidence"):
        return "https://www.amazon.com/dp/" + urllib.parse.quote(r["amazon_asin"]) + "?tag=" + AMAZON_TAG
    if r.get("amazon_query"):
        return "https://www.amazon.com/s?k=" + urllib.parse.quote_plus(r["amazon_query"]) + "&tag=" + AMAZON_TAG
def amz_btn(r):
    u = amazon(r)
    if not u: return ""
    label = "Buy on Amazon" if r["release_date"] <= today and not r.get("delayed") else "Pre-order on Amazon"
    return f'<p><a class=amz href="{E(u)}" rel="sponsored nofollow noopener" target="_blank">{label}</a></p>'
TODAY = datetime.date.fromisoformat(os.environ["BUILD_DATE"]) if os.environ.get("BUILD_DATE") else datetime.date.today()  # BUILD_DATE: testing only
today = TODAY.isoformat()
# ---- Page dates (sitemap lastmod, visible "Last updated", dateModified) ----
# Each page is rendered with the placeholder PD wherever its own date goes, hashed (title + description + JSON-LD + main
# body; the shared header/footer/head boilerplate is not hashed), and the date only moves when that hash changes.
# data/page_dates.json is committed. The daily CI rebuild also restores the previous CI run's file from the Actions cache
# (PAGE_DATES_CACHE), so a page whose content changed only because time passed keeps the first day it changed.
PD = "__PAGE_DATE__"
PAGE_DATES_FILE = "data/page_dates.json"
page_dates = json.load(open(PAGE_DATES_FILE)) if os.path.exists(PAGE_DATES_FILE) else {}
_pdc = os.environ.get("PAGE_DATES_CACHE")
cache_dates = json.load(open(_pdc)) if _pdc and os.path.exists(_pdc) else {}
new_dates = {}
def page_date(path, h):
    c = [e["date"] for e in (page_dates.get(path), cache_dates.get(path)) if e and e.get("hash") == h]
    d = min(c) if c else today
    new_dates[path] = {"hash": h, "date": d}; return d
def tdate(d=PD): return f'<time datetime="{d}">{d}</time>'
SL_STORE = "https://secretlair.wizards.com/us/en"  # Wizards' own Secret Lair store (MagicSecretLair.com)
SL_ONSALE_DAYS = 30  # with no known sale_end, a drop counts as "on sale now" for this many days after it opens
def sl_bucket(r):
    if r.get("delayed"): return "up"  # announced date passed but stock hasn't arrived: still upcoming, never "on sale now"
    if r.get("sold_out") and dated(r) and r["release_date"] <= today: return "past"
    if not dated(r) or r["release_date"] > today: return "up"
    if r.get("sale_end"): return "now" if r["sale_end"] >= today else "past"
    return "now" if (TODAY - datetime.date.fromisoformat(r["release_date"])).days <= SL_ONSALE_DAYS else "past"
def is_up(r): return r["release_date"] >= today or bool(r.get("delayed"))  # TBA sorts after digits, so counts as upcoming
OG_IMAGE = f"{SITE_URL}/og.png"
MON = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
def dated(r): return r["release_date"][:4].isdigit()
def mon_yyyy(r): return f"{MON[int(r['release_date'][5:7])-1]} {r['release_date'][:4]}" if dated(r) else "Date TBA"
def nice_date(r):
    if not dated(r): return "TBA"
    d = datetime.date.fromisoformat(r["release_date"]); return f"{MON[d.month-1]} {d.day}, {d.year}"
def short_name(r):
    if r.get("short_name"): return r["short_name"]
    n = r["name"].replace("Magic: The Gathering | ", "")
    return n.split(" (")[0].strip()
def trim(s, n=155):
    s = " ".join(s.split())
    if len(s) <= n: return s
    return s[:n-1].rsplit(" ", 1)[0].rstrip(",.;:—-") + "…"
def url(path): return f"{SITE_URL}/" + (path[:-len("index.html")] if path.endswith("index.html") else path)
def ld(obj): return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"
def page(title, desc, body, path, jsonld=(), noindex=False, og=None):
    desc = trim(desc); u = url(path); og_img, og_w, og_h = og or (OG_IMAGE, 1200, 630)
    robots = "<meta name=robots content=noindex>" if noindex else ""
    lds = "".join(ld(o) for o in jsonld)
    p = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name=description content="{E(desc)}">{robots}<link rel=canonical href="{u}">
<meta property=og:title content="{E(title)}"><meta property=og:description content="{E(desc)}"><meta property=og:type content=website><meta property=og:url content="{u}"><meta property=og:image content="{og_img}"><meta property=og:image:width content={og_w}><meta property=og:image:height content={og_h}><meta name=twitter:card content=summary_large_image>
<link rel=alternate type=application/rss+xml href="{BASE}/feed.xml" title="MTG Drops"><meta name='impact-site-verification' value='78f2b2fa-0831-48d2-a460-e2e3fa5a4eab'><meta name='impact-site-verification' value='c76059e5-ec5e-42d1-84a8-d9b58d1e5b68'><link rel=icon href="{BASE}/favicon.ico" sizes=any><link rel=icon type=image/png sizes=192x192 href="{BASE}/icon-192.png"><link rel=apple-touch-icon href="{BASE}/icon-192.png"><link rel=stylesheet href="{BASE}/style.css"><meta name="context7-site-verification" content="{CONTEXT7_SITE_KEY}">{lds}</head><body>
<blockquote data-context7-ask="true" aria-hidden="true" style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0">
  <h2>Search</h2>
  <p>{E(CONTEXT7_NOTE, quote=False)}</p>
</blockquote>
<header><a href="{BASE}/"><b>MTG Drops</b></a><a href="{BASE}/secret-lair.html">Secret Lair</a><a href="{BASE}/guides/">Guides</a><a href="{BASE}/newsletter.html">Newsletter</a><a href="{BASE}/sponsor.html">Sponsor</a><a href="{BASE}/feed.xml">RSS</a></header>
<main>{body}</main><footer><p><small><a href="{BASE}/">Release calendar</a> · <a href="{BASE}/secret-lair.html">Secret Lair drops</a> · <a href="{BASE}/guides/">Guides</a> · <a href="{BASE}/newsletter.html">Newsletter</a> · <a href="{BASE}/sponsor.html">Sponsor</a> · <a href="{BASE}/feed.xml">RSS</a> · Contact: <a href="mailto:contact@mtgdrops.com">contact@mtgdrops.com</a></small></p><small>Dates from official/community sources; verify before buying. {E(DISCLOSURE)} Not affiliated with Wizards of the Coast.</small></footer></body></html>"""
    p = p.replace(PD, page_date(path, hashlib.sha256("\x1f".join([title, desc, lds, body]).encode()).hexdigest()[:16]))
    out = os.path.join("dist", path); os.makedirs(os.path.dirname(out), exist_ok=True); open(out, "w").write(p)
def badges(r):
    b = "" if r["status"] == "confirmed" else f' <span class=st>{E(r["status"])}</span>'
    if r.get("sold_out"): b += ' <span class=st>sold out</span>'
    if r.get("delayed"): b += ' <span class=st>delayed</span>'
    return b
def when(r):  # visible date, plus the prerelease window when one is announced
    return nice_date(r) + (f' · Prerelease {E(r["prerelease"])}' if r.get("prerelease") else "")
def nice_iso(d): d = datetime.date.fromisoformat(d); return f"{MON[d.month-1]} {d.day}, {d.year}"
def srcs(r):
    out = []
    for u in [r["source"]] + list((r.get("field_sources") or {}).values()):
        if u and u not in out: out.append(u)
    return out
def checked(r, with_sources=True):
    """Visible 'Last checked' line: the date this entry's facts were last verified against its sources (releases.json last_checked)."""
    lc = r.get("last_checked")
    if not lc: return ""
    s = ""
    if with_sources:
        seen = {}; links = []
        for u in srcs(r)[:4]:
            host = urllib.parse.urlsplit(u).netloc.replace("www.", ""); seen[host] = seen.get(host, 0) + 1
            links.append(f'<a href="{E(u)}" rel=nofollow>{E(host)}{"" if seen[host] == 1 else " (" + str(seen[host]) + ")"}</a>')
        s = " · Sources: " + ", ".join(links)
    return f'<p class=lc><small>Last checked {tdate(lc).replace(">" + lc + "<", ">" + nice_iso(lc) + "<")}{s}</small></p>'
def card(r):
    if r.get("placeholder"):
        return f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span> <span class=st>{E(r["status"])}</span><h3>{E(r["name"])}</h3><div>{when(r)}</div><p>{E(r["note"])}</p>{checked(r)}</div>'
    return f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span>{badges(r)}<h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a></h3><div>{when(r)}</div><p>{E(r["note"])}</p>{amz_btn(r)}{checked(r)}</div>'
FORM = '<form action="https://buttondown.com/api/emails/embed-subscribe/alehpineda.dropdesk" method="post" target="popupwindow"><input type=email name=email required placeholder="you@example.com"> <button>Get What\'s Dropping</button></form>'
shutil.rmtree("dist", ignore_errors=True); os.makedirs("dist/p")
open("dist/style.css", "w").write(CSS + "\ntable{border-collapse:collapse}td,th{border:1px solid #2d3546;padding:.3rem .6rem;text-align:left}nav.bc{font-size:.85rem}")
# OG image: committed at static/og.png (generated once with Pillow if missing)
if not os.path.exists("static/og.png"):
    os.makedirs("static", exist_ok=True)
    from PIL import Image, ImageDraw, ImageFont
    def font(sz):
        for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
            if os.path.exists(f): return ImageFont.truetype(f, sz)
        return ImageFont.load_default()
    im = Image.new("RGB", (1200, 630), (15, 17, 21)); dr = ImageDraw.Draw(im)
    dr.rectangle([0, 560, 1200, 630], fill=(58, 123, 213))
    dr.text((80, 200), "MTG Drops", font=font(130), fill=(232, 232, 234))
    dr.text((84, 380), "Every upcoming Magic: The Gathering release", font=font(38), fill=(124, 196, 255))
    dr.text((84, 575), "mtgdrops.com", font=font(36), fill=(255, 255, 255))
    im.save("static/og.png")
shutil.copy("static/og.png", "dist/og.png")
# Favicons: committed at static/favicon.ico (16/32/48) and static/icon-192.png (generated once with Pillow if missing)
if not (os.path.exists("static/favicon.ico") and os.path.exists("static/icon-192.png")):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (192, 192), (58, 123, 213)); dr = ImageDraw.Draw(im)
    fnt = next((ImageFont.truetype(f, 120) for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"] if os.path.exists(f)), ImageFont.load_default())
    w = dr.textlength("M", font=fnt); dr.text(((192 - w) / 2, 22), "M", font=fnt, fill=(255, 255, 255))
    im.save("static/icon-192.png", optimize=True); im.save("static/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
for f in ("favicon.ico", "icon-192.png"): shutil.copy(os.path.join("static", f), os.path.join("dist", f))
up = [r for r in data if is_up(r)]  # includes TBA (sorts after digits) and delayed items
up = up + [r for r in data if not is_up(r)]
public = [r for r in data if not r.get("placeholder")]
btns = '<button class=on data-f="">All</button>' + "".join(f'<button data-f="{E(t)}">{E(t)}</button>' for t in types)
js = "<script>document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.f button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.card').forEach(c=>c.style.display=!b.dataset.f||c.dataset.type==b.dataset.f?'':'none')})</script>"
groups = {}
for r in up: groups.setdefault(mon_yyyy(r) if is_up(r) else "Already released", []).append(r)
months = "".join(f"<h2>{E(g)}</h2>" + "".join(card(r) for r in rs) for g, rs in groups.items())
ABOUT = "MTG Drops is a free Magic: The Gathering release calendar: every upcoming set, Commander precon, Universes Beyond and Secret Lair drop, with dates, prices, buy/skip verdicts and a weekly newsletter. Not affiliated with Wizards of the Coast, and not a Discord bot or eBay monitor."
HOME_DESC = "MTG Drops: free Magic: The Gathering release calendar. Every set, precon, Universes Beyond and Secret Lair drop, with dates, prices and buy/skip verdicts."
ORG = {"@type": "Organization", "@id": f"{SITE_URL}/#org", "name": "MTG Drops", "url": f"{SITE_URL}/", "logo": OG_IMAGE, "description": ABOUT}
def fmt(p): return f"${p['usd']:,.2f}"
# ---- Home FAQ: generated from releases.json; the FAQPage text is the visible answer text with links stripped ----
def plain(h): return html.unescape(re.sub(r"<[^>]+>", "", h))
def plink(r, t=None): return f'<a href="{BASE}/p/{r["slug"]}.html">{E(t or short_name(r))}</a>' if not r.get("placeholder") else E(t or short_name(r))
SETS = ("Main Set", "Universes Beyond")
h_next = next((r for r in public if dated(r) and r["release_date"] > today and r["type"] in SETS), None)
h_2027 = [r for r in data if r["release_date"][:4] == "2027" and r["type"] in SETS and r["status"] == "confirmed"]
h_cmd27 = [r for r in public if r["release_date"][:4] == "2027" and r["type"] == "Commander Precon"]
h_sl = next((r for r in data if r["type"] == "Secret Lair" and not r.get("placeholder") and dated(r) and sl_bucket(r) == "up" and not r.get("delayed")), None)
h_sold = [r for r in public if r.get("sold_out")]
def and_list(xs): return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
home_faq = []
if h_next: home_faq.append(("What is the next MTG set?", f'{plink(h_next, h_next["name"])} releases {nice_date(h_next)} ({E(h_next["status"])})' + (f', with prerelease events {E(h_next["prerelease"])}' if h_next.get("prerelease") else "") + "."))
if h_2027: home_faq.append(("What MTG sets release in 2027?", f"{len(h_2027)} sets are confirmed for 2027: " + and_list([f"{plink(r, r['name'])} ({nice_date(r)})" for r in h_2027]) + "."
                             + (" Commander decks are confirmed alongside " + and_list([plink(r) for r in h_cmd27]) + ", with decklists still to come." if h_cmd27 else "")))
if h_sl: home_faq.append(("When is the next Secret Lair drop?", f'{plink(h_sl, h_sl["name"])} goes on sale {nice_date(h_sl)}' + (f' at {fmt(h_sl["prices"][0])}' if h_sl.get("prices") else "") + f'. See every drop on the <a href="{BASE}/secret-lair.html">Secret Lair schedule</a>.'))
if h_sold: home_faq.append(("Which recent MTG releases are sold out?", and_list([plink(r) + f" ({nice_date(r)})" for r in h_sold]) + " sold out at the official store. Check each page before paying resale prices."))
home_faq.append(("How often is the MTG Drops calendar updated?", "We check official Wizards of the Coast announcements and reputable MTG news every Tuesday and Friday. Each entry shows the date it was last checked and links to its sources."))
home_faq_html = "<h2>MTG release FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{a}</p>" for q, a in home_faq)
ICS_LINKS = {"calendar.ics": "every MTG release", "secret-lair.ics": "Secret Lair drops only"}
def ics_link(f): return (f'<a href="https://calendar.google.com/calendar/r?cid=webcal://mtgdrops.com/{f}" rel=nofollow>Add to Google Calendar</a> · '
                         f'<a href="webcal://mtgdrops.com/{f}" rel=nofollow>Apple / Outlook (webcal)</a> · <a href="{BASE}/{f}">Download .ics</a>')
home_ld = [{"@context": "https://schema.org", "@type": "WebSite", "@id": f"{SITE_URL}/#website", "name": "MTG Drops", "url": f"{SITE_URL}/", "description": ABOUT, "publisher": {"@id": f"{SITE_URL}/#org"}},
           {"@context": "https://schema.org", **ORG},
           {"@context": "https://schema.org", "@type": "CollectionPage", "@id": f"{SITE_URL}/#page", "name": "MTG Release Calendar 2026–2027", "url": f"{SITE_URL}/", "description": HOME_DESC, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "mainEntity": {"@id": f"{SITE_URL}/#releases"}},
           {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in home_faq]},
           {"@context": "https://schema.org", "@type": "ItemList", "@id": f"{SITE_URL}/#releases", "name": "Upcoming Magic: The Gathering releases", "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate([r for r in up if not r.get("placeholder")])]}]
page("MTG Drops — Every upcoming MTG release, one calendar", HOME_DESC,
     f"<h1>MTG Release Calendar 2026–2027</h1><p><b>What's dropping in Magic.</b> Last updated: {tdate()}</p><p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p><p>Every upcoming MTG product, with a short buy/skip note. New: <a href=\"{BASE}/guides/mtg-releases-fall-holiday-2026.html\">every MTG product releasing this fall/holiday 2026</a>, with gift picks, the <a href=\"{BASE}/guides/star-trek-mtg-release-guide.html\">MTG Star Trek release guide</a>, and the <a href=\"{BASE}/secret-lair.html\">Secret Lair drop schedule</a>.</p>{FORM}<p class=disc><small>{E(DISCLOSURE)}</small></p><p><b>Calendar feed:</b> {ics_link("calendar.ics")}</p><div class=f>{btns}</div>" + months + home_faq_html + js, "index.html", home_ld)
def title_for(r):
    sn = short_name(r); m = mon_yyyy(r).replace("Date TBA", "TBA")
    for t in (f"{sn} Release Date ({m}), Price & Preorder | MTG Drops", f"{sn} Release Date ({m}) | MTG Drops", f"{sn} Release Date, {m} | MTG Drops", f"{sn} Release Date | MTG Drops", f"{sn} ({m}) | MTG Drops", f"{sn} | MTG Drops"):
        if len(t) <= 60: return t
    return t
def related(r):
    if r.get("placeholder"): pool = public
    else: pool = [x for x in public if x is not r]
    pool = [x for x in pool if x is not r]
    sib = [x for x in pool if dated(x) and x["release_date"] == r["release_date"] and {x["type"], r["type"]} & {"Commander Precon"} and ({x["type"], r["type"]} - {"Commander Precon"}) <= set(SETS) and x["type"] != r["type"]]
    pool = [x for x in pool if x not in sib]
    key = lambda x: (0, abs((datetime.date.fromisoformat(x["release_date"]) - datetime.date.fromisoformat(r["release_date"])).days)) if dated(x) and dated(r) else ((1, 0) if not dated(x) else (2, 0))
    return (sib + sorted(pool, key=key))[:4]
TYPE_INFO = {
 "Secret Lair": ("What is a Secret Lair drop?", "Secret Lair is Wizards of the Coast's direct-to-fan line of limited Magic products, sold mainly at MagicSecretLair.com. Most drops are small sets of cards with alternate art, often reprints, sold for a limited time or while supplies last, and not restocked once they end. Cards are tournament-legal wherever the original card is legal. Because supply is limited, prices on the secondary market can move quickly in either direction after a drop closes."),
 "Commander Precon": ("What is a Commander precon?", "A Commander precon (preconstructed deck) is a ready-to-play 100-card deck for Commander, Magic's most popular multiplayer format. Each deck is built around a legendary face commander, usually comes with tokens and a deck box, and can be played straight out of the box or used as a base to upgrade. Precons typically include a mix of new-to-Magic cards and reprints, so many players buy them both to play and for specific singles."),
 "Universes Beyond": ("What is Universes Beyond?", "Universes Beyond is the Magic: The Gathering line that brings other franchises (films, TV, games and comics) into Magic cards. Some Universes Beyond releases are full sets with Play Boosters, Collector Boosters and Bundles that can be legal in Standard; others are Commander decks or Secret Lair drops. Check each product's legality notes before building a deck around it."),
 "Main Set": ("What is a main Magic set?", "A main (premier) set is a Standard-legal Magic expansion released through the year. Main sets are typically sold as Play Boosters (designed for both drafting and opening), Collector Boosters (more foils and alternate-art cards), Bundles, and Commander decks released alongside the set. Prerelease events at local game stores usually run the week before the tabletop release."),
 "Supplemental": ("What is a supplemental product?", "Supplemental products are Magic releases outside the main Standard sets, such as draft-focused remastered sets, Mystery Booster editions and special boxes. They are usually not Standard-legal and are often aimed at Commander or casual play. Availability and print runs vary, so check the official announcement for how and where each one is sold."),
 "Special": ("What is a special release?", "Special releases are one-off or unusual Magic products that do not fit the regular set calendar, such as reprints, anniversary items or event-exclusive products. Sales methods, quantities and legality vary from product to product, so the official announcement is the best reference."),
}
HOWTO = ("How to pre-order", "Before release, most Magic products can be pre-ordered from local game stores (many offer preorder pricing or prerelease bundles), large online retailers, TCGplayer sellers and Amazon. Secret Lair drops are the exception: they are sold mainly at MagicSecretLair.com during a fixed sale window. Compare preorder prices with the MSRP listed above, check the retailer's ship date, and remember that dates marked unconfirmed can change. Prices in stores frequently drop after release, so preordering mainly makes sense if you want the product on day one or supply is limited.")
def fmt(p): return f"${p['usd']:,.2f}"
# ---- Per-product card images (static/products/<slug>-1x1.png 1200x1200, -og.png 1200x630) ----
# Plain generated cards (name, type, release date, MTG Drops branding, a per-product colour); no Wizards art, nothing hotlinked.
# Committed to the repo because CI has no Pillow: a card is regenerated only when Pillow is available and its text changed
# (tracked in manifest.json); a missing/stale card with no Pillow falls back to the site banner (og.png).
import hashlib, colorsys
PCARD_DIR = "static/products"; PCARD_MAN = os.path.join(PCARD_DIR, "manifest.json")
pcard_man = json.load(open(PCARD_MAN)) if os.path.exists(PCARD_MAN) else {}
def pcard_spec(r): return {"name": short_name(r), "type": r["type"], "date": nice_date(r) if dated(r) else "Date TBA", "v": 1}
def pcard_color(slug):
    h = int(hashlib.sha1(slug.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    return tuple(int(c * 255) for c in colorsys.hls_to_rgb(h, 0.42, 0.55))
def pcard_draw(spec, color, W, H, out):
    from PIL import Image, ImageDraw, ImageFont
    def font(sz, bold=True):
        for f in (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]):
            if os.path.exists(f): return ImageFont.truetype(f, sz)
        return ImageFont.load_default()
    im = Image.new("RGB", (W, H), (15, 17, 21)); dr = ImageDraw.Draw(im)
    pad = 80; band = 28 if H < 900 else 36
    dr.rectangle([0, 0, W, band], fill=color); dr.rectangle([0, H - 110, W, H], fill=color)
    dr.text((pad, band + 50), spec["type"].upper(), font=font(44 if H < 900 else 52), fill=color)
    size = 92 if H < 900 else 110; words = spec["name"].split()
    while True:  # wrap the name to the card width, shrinking until it fits in the space above the date
        f = font(size); lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if dr.textlength(t, font=f) <= W - 2 * pad or not cur: cur = t
            else: lines.append(cur); cur = w
        lines.append(cur)
        top = band + 140 if H < 900 else band + 190; lh = int(size * 1.15)
        if top + lh * len(lines) <= H - 110 - (150 if H < 900 else 220) or size <= 40: break
        size -= 6
    for i, ln in enumerate(lines): dr.text((pad, top + i * lh), ln, font=f, fill=(240, 240, 242))
    dr.text((pad, H - 110 - (120 if H < 900 else 170)), ("Release: " if spec["date"] != "Date TBA" else "") + spec["date"], font=font(56 if H < 900 else 64, False), fill=(124, 196, 255))
    dr.text((pad, H - 85), "MTG Drops", font=font(50), fill=(255, 255, 255))
    t = "mtgdrops.com"; f2 = font(38, False); dr.text((W - pad - dr.textlength(t, font=f2), H - 75), t, font=f2, fill=(255, 255, 255))
    im.save(out, optimize=True)
def pcard(r):
    """Return (square_url, wide_url) for a release's card, or None to fall back to og.png."""
    spec = pcard_spec(r); key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:12]
    files = [os.path.join(PCARD_DIR, f"{r['slug']}-{k}.png") for k in ("1x1", "og")]
    if pcard_man.get(r["slug"]) != key or not all(os.path.exists(f) for f in files):
        try:
            import PIL  # noqa: F401
        except ImportError:
            print(f"warning: product card for {r['slug']} missing/stale and Pillow unavailable; using og.png"); return None
        os.makedirs(PCARD_DIR, exist_ok=True); c = pcard_color(r["slug"])
        pcard_draw(spec, c, 1200, 1200, files[0]); pcard_draw(spec, c, 1200, 630, files[1])
        pcard_man[r["slug"]] = key; json.dump(pcard_man, open(PCARD_MAN, "w"), indent=1, sort_keys=True)
    os.makedirs("dist/products", exist_ok=True)
    for f in files: shutil.copy(f, "dist/products/")
    return tuple(f"{SITE_URL}/products/{os.path.basename(f)}" for f in files)
for r in data:
    sn = short_name(r); pu = f"{SITE_URL}/p/{r['slug']}.html"
    win = f"<p><b>Window:</b> {E(r['window'])}</p>" if r.get("window") else ""
    prices = r.get("prices") or []
    ptab = ("<table><tr><th>Item</th><th>Price (USD)</th></tr>" + "".join(f"<tr><td>{E(p['label'])}</td><td>{fmt(p)}</td></tr>" for p in prices) + "</table>") if prices else "<p>Price: TBA</p>"
    contents = ("<h2>What's inside</h2><ul>" + "".join(f"<li>{E(c)}</li>" for c in r["contents"]) + "</ul>") if r.get("contents") else ""
    if r.get("inside"):
        contents = "<h2>What's inside</h2>" + "".join(f"<h3>{E(h)}</h3><ul>" + "".join(f"<li>{E(i)}</li>" for i in items) + "</ul>" for h, items in r["inside"]) + (f'<p><small>Product contents per <a href="{E(r["inside_source"])}">Wizards of the Coast</a>.</small></p>' if r.get("inside_source") else "")
    fs = r.get("field_sources") or {}
    fsrc = ("<p><small>Sources by field: " + " · ".join(f'{E(k.replace("_", " "))}: <a href="{E(v)}">{E(urllib.parse.urlsplit(v).netloc)}</a>' for k, v in fs.items()) + "</small></p>") if fs else ""
    hubl = f'<p>See every drop on one page: <a href="{BASE}/secret-lair.html">Secret Lair drops: schedule, prices &amp; verdicts</a>.</p>' if r["type"] == "Secret Lair" else ""
    if r["slug"] in ("star-trek", "star-trek-commander"): hubl += f'<p>Planning your Star Trek buys? Read the <a href="{BASE}/guides/star-trek-mtg-release-guide.html">MTG Star Trek release guide</a>: every product, MSRP, Commander deck and key date.</p>'
    facts = ("<h2>Key facts</h2><ul>" + "".join(f"<li>{E(f)}</li>" for f in r["facts"]) + "</ul>") if r.get("facts") else ""
    ti = TYPE_INFO.get(r["type"]); tinfo = f"<h2>{E(ti[0])}</h2><p>{E(ti[1])}</p>" if ti else ""
    howto = f"<h2>{HOWTO[0]}</h2><p>{E(HOWTO[1])}</p>" if not r.get("placeholder") and (not dated(r) or r["release_date"] > today or r.get("delayed")) else ""
    rel = related(r)
    relhtml = "<h2>Related releases</h2><ul>" + "".join(f'<li><a href="{BASE}/p/{x["slug"]}.html">{E(x["name"])}</a> — {nice_date(x)}</li>' for x in rel) + "</ul>"
    faq = [(f"When does {sn} release?", f"{nice_date(r)} ({r['status']})." + (f" {r['window']}." if r.get("window") else "") if dated(r) else f"The release date is TBA ({r['status']})." + (f" {r['window']}." if r.get("window") else "")),
           (f"How much does {sn} cost?", "; ".join(f"{p['label']}: {fmt(p)}" for p in prices) + "." if prices else "Pricing has not been announced yet (TBA)."),
           (f"Should I buy {sn}?", r["note"])]
    if r.get("contents"): faq.append((f"What's in {sn}?", "; ".join(r["contents"]) + "."))
    faqhtml = "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faq)
    # Product snippet markup only (Google: "Product snippets: for product pages where people can't directly purchase the product").
    # MTG Drops sells nothing, so no offer may name us or our page as the place to buy: each Offer is the publisher's
    # (Wizards of the Coast) official price. Secret Lair offers name seller = Wizards and Wizards' own store url (Wizards sells
    # those directly); retail offers are the MSRP with no seller (game stores and other retailers sell them) and no url.
    # That keeps us out of merchant listings (no shippingDetails/hasMerchantReturnPolicy to claim) without inventing anything.
    # No review/aggregateRating: we have none, and Google only needs one of offers/review/aggregateRating.
    card = None if r.get("placeholder") else pcard(r)
    prod = {"@context": "https://schema.org", "@type": "Product", "name": r["name"], "url": pu, "image": r.get("image") or (list(card) if card else OG_IMAGE), "category": r["type"], "brand": {"@type": "Brand", "name": "Wizards of the Coast"}, "description": trim(r["note"], 300)}
    if dated(r): prod["releaseDate"] = r["release_date"]
    offers = [p for p in prices if p.get("offer", True)]
    sl_direct = r["type"] == "Secret Lair"  # sold by Wizards itself at MagicSecretLair.com for a limited window
    if sl_direct:
        b = sl_bucket(r)  # same rule the hub page uses for on sale now / upcoming / ended
        avail = {"now": "https://schema.org/InStock", "past": "https://schema.org/Discontinued"}.get(b, "https://schema.org/OutOfStock")  # not on sale yet: no preorders
        odesc = "Official Wizards of the Coast price at MagicSecretLair.com (limited-time sale). MTG Drops does not sell this product."
    else:
        avail = "https://schema.org/InStock" if dated(r) and r["release_date"] <= today else "https://schema.org/PreOrder"
        odesc = "Wizards of the Coast MSRP; sold by game stores and other retailers. MTG Drops does not sell this product."
    # Stock flags from releases.json (sourced in field_sources / notes): sold out at the official store, or delayed after its
    # announced date (still orderable ahead of arrival, so PreOrder: it is not on shelves yet).
    if r.get("sold_out"): avail = "https://schema.org/SoldOut"
    elif r.get("delayed"): avail = "https://schema.org/PreOrder"
    if offers:
        def offer(p):
            o = {"@type": "Offer", "name": p["label"], "price": f"{p['usd']:.2f}", "priceCurrency": p.get("currency", "USD"), "availability": avail, "description": odesc}
            if sl_direct:  # Wizards really is the seller (MagicSecretLair.com); retail MSRPs name no seller, since stores sell those
                o["seller"] = {"@type": "Organization", "name": "Wizards of the Coast", "url": "https://company.wizards.com/en"}; o["url"] = SL_STORE
            if sl_direct and dated(r) and r["release_date"] > today: o["availabilityStarts"] = r["release_date"]
            if r.get("sale_end"): o["priceValidUntil"] = r["sale_end"]
            return o
        prod["offers"] = [offer(p) for p in offers]
        prod["@id"] = pu + "#product"
        main_ld = [{"@context": "https://schema.org", "@type": "WebPage", "@id": pu + "#page", "name": title_for(r), "url": pu, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "mainEntity": {"@id": pu + "#product"}}, prod]
    else:
        main_ld = [{"@context": "https://schema.org", "@type": "WebPage", "@id": pu + "#page", "name": title_for(r), "url": pu, "description": trim(r["note"], 300), "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "about": {"@type": "Thing", "name": r["name"]}}]
    # Only Secret Lair has a hub page; other types get a 2-item trail (no fake middle crumb pointing back at the home page).
    bc_items = [("MTG Drops", f"{SITE_URL}/")] + ([("Secret Lair", f"{SITE_URL}/secret-lair.html")] if r["type"] == "Secret Lair" else []) + [(r["name"], pu)]
    bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i+1, "name": n, "item": u} for i, (n, u) in enumerate(bc_items)]}
    crumbs = f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › {(f'<a href="{BASE}/secret-lair.html">Secret Lair</a>' if r["type"] == "Secret Lair" else E(r["type"]))} › {E(sn)}</nav>{hubl}'
    desc = f"{sn} release date: {nice_date(r)}. " + r["note"]
    page(title_for(r), desc,
         f'{crumbs}<span class=t>{E(r["type"])}</span><h1>{E(r["name"])}</h1><p><b>Release:</b> {nice_date(r)} ({E(r["status"])}){f" · <b>Prerelease:</b> {E(r['prerelease'])}" if r.get("prerelease") else ""}{" · <b>Sold out</b> at the official store" if r.get("sold_out") else ""}{" · <b>Delayed</b>: stock may arrive after this date" if r.get("delayed") else ""}</p>{win}<h2>Price</h2>{ptab}{contents}{facts}<h2>Buy or skip?</h2><p>{E(r["note"])}</p>{f"<p><i>{E(r['preorder_call'])}</i></p>" if r.get("preorder_call") else ""}{("<p>Other Commander decks coming in 2027: " + ", ".join(plink(x, x["name"]) + f" ({nice_date(x)})" for x in h_cmd27 if x is not r) + ".</p>") if r.get("preorder_call") and r in h_cmd27 else ""}<p><a href="{tcg(r.get("tcg_query") or r["name"])}" rel="sponsored nofollow">Check prices on TCGplayer</a></p>{amz_btn(r)}{"<p class=disc><small>"+E(DISCLOSURE)+"</small></p>" if amazon(r) else ""}{tinfo}{howto}{relhtml}{faqhtml}<p><small>Source: <a href="{E(r["source"])}">{E(r["source"])}</a></small></p>{fsrc}{checked(r, with_sources=False)}<p><small>Last updated: {tdate()}</small></p>{FORM}',
         f"p/{r['slug']}.html", main_ld + [bc], noindex=bool(r.get("placeholder")), og=(card[1], 1200, 630) if card else None)
# ---- Secret Lair hub (/secret-lair.html): generated from releases.json, so data updates keep it current ----
SL_SRC = {"about": "https://secretlair.wizards.com/us/en/about-us",
          "faq": "https://secretlair-support.wizards.com/hc/en-us/articles/45369886769300-About-Secret-Lair-FAQ",
          "lpr": "https://magic.wizards.com/en/news/announcements/speeding-up-secret-lair-shipping",
          "queue": "https://magic.wizards.com/en/news/announcements/secret-lair-corn-maze-superdrop"}
sl = [r for r in data if r["type"] == "Secret Lair" and not r.get("placeholder")]
sl_now = sorted([r for r in sl if sl_bucket(r) == "now"], key=lambda r: r["release_date"], reverse=True)
sl_up = [r for r in sl if sl_bucket(r) == "up"]  # data is date-sorted; TBA sorts last
sl_past = sorted([r for r in sl if sl_bucket(r) == "past"], key=lambda r: r["release_date"], reverse=True)
def sl_price(r):
    ps = r.get("prices") or []
    if not ps: return "TBA"
    return "; ".join(f"{p['label']} {fmt(p)}" for p in ps[:3]) + ("; more options on the product page" if len(ps) > 3 else "")
def sl_when(r):
    if not dated(r): return "Date TBA"
    if r.get("delayed"): return f"Delayed: was due {nice_date(r)}; Wizards says stock may arrive shortly after"
    if r.get("sold_out") and sl_bucket(r) == "past": return f"Went on sale {nice_date(r)}; sold out"
    b = sl_bucket(r)
    return ("On sale since " if b == "now" else "Went on sale " if b == "past" else "On sale ") + nice_date(r)
def sl_card(r):
    cont = trim("; ".join(r["contents"]), 220) if r.get("contents") else "Contents TBA"
    st = badges(r)
    return (f'<div class=card data-type="Secret Lair"><h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a>{st}</h3>'
            f'<p><b>Date:</b> {E(sl_when(r))}</p>' + (f'<p><b>Sale details:</b> {E(r["window"])}</p>' if r.get("window") else "") +
            f'<p><b>Price:</b> {E(sl_price(r))}</p><p><b>Contents:</b> {E(cont)}</p><p><b>Our verdict:</b> {E(r["note"])}</p>'
            f'<p><a href="{BASE}/p/{r["slug"]}.html">Full details, card list and sources →</a></p>{checked(r)}</div>')
def sl_section(h, rs, empty):
    return f"<h2>{E(h)}</h2>" + ("".join(sl_card(r) for r in rs) if rs else f"<p>{E(empty)}</p>")
nxt = next((r for r in sl_up if dated(r) and not r.get("delayed")), None)
def names(rs): return "; ".join(f"{short_name(r)} (" + ("delayed, was due " if r.get("delayed") else "") + f"{nice_date(r) if dated(r) else 'date TBA'})" for r in rs)
sl_faq = [
 ("What is the next Secret Lair drop?",
  (f"The next dated Secret Lair release on our calendar is {nxt['name']}, on sale {nice_date(nxt)}." if nxt else "There is no dated upcoming Secret Lair release on our calendar right now.")
  + (f" Also announced: {names([r for r in sl_up if r is not nxt])}." if [r for r in sl_up if r is not nxt] else "")),
 ("What Secret Lair drop is on sale now?",
  (f"Most recently opened: {names(sl_now)}. Limited print runs can sell out early, so check MagicSecretLair.com for current stock." if sl_now else "No Secret Lair sale has opened in the last few weeks on our calendar; see the Recent / ended section for the latest drops.")),
 ("How much do Secret Lair drops cost?",
  "Standard 2026 Secret Lair drops are $29.99 for the non-foil edition and $39.99 for the foil edition (per Wizards' Superdrop announcements). Superdrops also offer multi-drop bundles, and bigger products are priced individually, for example "
  + "; ".join(f"{short_name(r)} {fmt(r['prices'][0])}" for r in sl if r.get("prices") and r["prices"][0]["usd"] >= 80) + "."),
 ("Are Secret Lair drops print to demand?",
  "Mostly not any more. In January 2024 Wizards moved most of Secret Lair from print-to-demand to limited print runs that are printed before the sale, so orders ship faster but popular drops can sell out early. Wizards says some drops may still be print to demand for an ordering window."),
 ("What time do Secret Lair drops go on sale?",
  "Recent Secret Lair sales open at 9 a.m. PT on MagicSecretLair.com, with a pre-queue from 8 a.m. PT; customers in the pre-queue get a random spot in line when the sale starts. Adding a product to your cart does not reserve it."),
 ("What is the difference between foil and non-foil Secret Lair drops?",
  "Most drops come in a non-foil edition and a traditional foil edition (Wizards renamed its rainbow foil to traditional foil), usually $10 apart. Some products use special foils instead, such as the surge foils that can turn up in the Marvel Countdown Kit."),
]
sl_intro = (f'<h2>What is Secret Lair and how do drops work?</h2>'
 f'<p>Secret Lair is Wizards of the Coast\'s direct-to-fan line of collectible Magic: The Gathering cards, sold at MagicSecretLair.com. '
 f'A drop is an exclusive, limited-time selection of usually 4 to 8 cards with new art or treatments, often a crossover with an artist or franchise, and most drops come in both foil and non-foil editions (<a href="{SL_SRC["about"]}">Secret Lair: About</a>). '
 f'Sales open at 9 a.m. PT, with a pre-queue from 8 a.m. PT (<a href="{SL_SRC["queue"]}">Wizards</a>). '
 f'Since 2024, most drops are limited print runs printed before the sale rather than print-to-demand, so popular drops can sell out before the sale ends; a few remain print-to-demand (<a href="{SL_SRC["lpr"]}">Wizards</a>, <a href="{SL_SRC["faq"]}">Secret Lair FAQ</a>). '
 f'Standard 2026 drops cost $29.99 non-foil or $39.99 traditional foil; Superdrops bundle several drops, and larger products such as Countdown Kits and Festival in a Box are priced on their own.</p>')
sl_list = sl_now + sl_up + sl_past
sl_url = f"{SITE_URL}/secret-lair.html"
SL_TITLE = "Secret Lair Drops: Schedule, Prices & Verdicts | MTG Drops"
SL_DESC = "Secret Lair release schedule: drops on sale now, upcoming Secret Lair drops and recent sales, with dates, prices, card lists and buy/skip verdicts."
sl_ld = [
 {"@context": "https://schema.org", "@type": "CollectionPage", "@id": sl_url + "#page", "name": SL_TITLE, "url": sl_url, "description": trim(SL_DESC, 300), "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "Secret Lair drops: on sale now, upcoming and recent", "itemListOrder": "https://schema.org/ItemListUnordered", "numberOfItems": len(sl_list),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate(sl_list)]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Secret Lair", "item": sl_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in sl_faq]},
]
page(SL_TITLE, SL_DESC,
     f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Secret Lair</nav><h1>Secret Lair Drops: Schedule, Prices &amp; Verdicts</h1>'
     f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
     f'<p><b>Last updated:</b> {tdate()} · {len(sl_now)} on sale now · {len(sl_up)} upcoming · {len(sl_past)} recent / ended</p>'
     + f'<p><b>Secret Lair calendar feed:</b> {ics_link("secret-lair.ics")}</p>'
     + sl_intro + f'<p>Planning holiday buys? See <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>, sets and Commander decks included.</p>'
     + sl_section("On sale now", sl_now, "No Secret Lair sale has opened in the last few weeks. See Upcoming below.")
     + sl_section("Upcoming Secret Lair drops", sl_up, "No upcoming Secret Lair drops are announced right now.")
     + sl_section("Recent / ended", sl_past, "Nothing here yet.")
     + '<p><small>Drops opened more than ' + str(SL_ONSALE_DAYS) + ' days ago are listed as recent / ended unless an end date is known; limited print runs may sell out sooner or stay in stock longer, so check MagicSecretLair.com.</small></p>'
     + "<h2>Secret Lair FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in sl_faq)
     + f'<h2>Get new Secret Lair drops by email</h2><p>What\'s Dropping is our free weekly email: new Secret Lair announcements, sale dates and a buy-or-skip verdict for each drop.</p>{FORM}'
     + f'<p class=disc><small>{E(DISCLOSURE)}</small></p><p><small>Last updated: {tdate()}</small></p>',
     "secret-lair.html", sl_ld)
SL_LLMS = "".join(f"- [{r['name']}]({SITE_URL}/p/{r['slug']}.html): {lab}; {sl_when(r)}; price: {sl_price(r)}\n" for lab, rs in (("on sale now", sl_now), ("upcoming", sl_up), ("recent/ended", sl_past)) for r in rs)
SL_LLMS = f"Hub: [Secret Lair drops: schedule, prices & verdicts]({sl_url})\n" + SL_LLMS
# ---- Guides: generated from releases.json ----
VERDICT_LABEL = {"buy": "Buy", "wait": "Wait", "skip": "Skip", "mixed": "Mixed"}
def vtag(r):
    v = r.get("verdict")
    return f'<span class=t>Verdict: {VERDICT_LABEL.get(v, v)}</span> ' if v else '<span class=t>No verdict yet</span> '
def guide_item(r):
    ps = r.get("prices") or []
    price = "; ".join(f"{p['label']}: {fmt(p)}" for p in ps) if ps else "TBA"
    st = badges(r)
    return (f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span>{st}<h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a></h3>'
            f'<p><b>Date:</b> {nice_date(r)}</p><p><b>Price:</b> {E(price)}</p><p>{vtag(r)}{E(r["note"])}</p>{amz_btn(r)}</div>')
G_SLUG = "guides/mtg-releases-fall-holiday-2026.html"; g_url = url(G_SLUG)
G_TITLE = "MTG Releases Oct–Dec 2026 & Holiday Gift Guide | MTG Drops"
G_H1 = "Every MTG Product Releasing This Fall/Holiday 2026"
G_PUBLISHED = "2026-10-17"
G_MONTHS = ["2026-10", "2026-11", "2026-12"]
g_items = [r for r in public if r["release_date"][:7] in G_MONTHS]
g_tba = [r for r in public if not dated(r)]
g_gifts = [r for r in g_items if r.get("verdict") == "buy" and r.get("gift_for")]
def g_month_name(m): return f"{['January','February','March','April','May','June','July','August','September','October','November','December'][int(m[5:])-1]} {m[:4]}"
g_by = {m: [r for r in g_items if r["release_date"][:7] == m] for m in G_MONTHS}
def g_names(rs): return "; ".join(f"{short_name(r)} ({nice_date(r)}" + ("" if r["status"] == "confirmed" else f", {r['status']}") + (f", from {fmt(min(r['prices'], key=lambda p: p['usd']))}" if r.get("prices") else "") + ")" for r in rs)
nxt_set = next((r for r in public if dated(r) and r["release_date"] > "2026-12-31" and r["type"] in ("Main Set", "Universes Beyond")), None)
g_faq = [(f"What MTG products release in {g_month_name(m)}?", (f"{g_names(rs)}." if rs else f"Nothing is on our calendar for {g_month_name(m)} yet.") + " Dates marked unconfirmed can still change.") for m, rs in g_by.items()]
g_faq.append(("What is the best MTG gift for the 2026 holidays?",
              ("Our picks, all rated buy: " + "; ".join(f"{short_name(r)} for {r['gift_for'].split(':')[0]}" for r in g_gifts) + ". If you're unsure, a gift card for a local game store avoids guessing.") if g_gifts else "We don't have any items rated buy for this season yet."))
if nxt_set: g_faq.append(("What is the next MTG set after 2026?", f"{nxt_set['name']}, releasing {nice_date(nxt_set)} ({nxt_set['status']})."))
g_body = (f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › <a href="{BASE}/guides/">Guides</a> › Fall/Holiday 2026</nav><h1>{E(G_H1)}</h1>'
  f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
  f'<p><b>Last updated:</b> {tdate()} · {len(g_items)} products from October to December 2026</p>'
  f'<p>Every Magic: The Gathering product on our calendar for October, November and December 2026: sets, Commander decks, Secret Lair drops, bundles and special releases, with release dates, MSRPs and our buy/skip verdict. Secret Lair sales are tracked on the <a href="{BASE}/secret-lair.html">Secret Lair hub</a>, and November\'s biggest release has its own <a href="{BASE}/guides/star-trek-mtg-release-guide.html">Star Trek release guide</a>.</p>'
  "<h2>Best picks for gifts</h2>" + ("<p>Only products we already rate as a buy, and who each one suits:</p><ul>" + "".join(f'<li><a href="{BASE}/p/{r["slug"]}.html">{E(short_name(r))}</a> ({nice_date(r)}): for {E(r["gift_for"])}.</li>' for r in g_gifts) + "</ul>" if g_gifts else "<p>No buy-rated products this season yet.</p>")
  + "".join(f"<h2>{g_month_name(m)}</h2>" + ("".join(guide_item(r) for r in rs) if rs else "<p>Nothing scheduled yet.</p>") for m, rs in g_by.items())
  + ("<h2>Announced, no date yet</h2><p>Announced but not yet scheduled, so these may or may not land before the end of 2026.</p>" + "".join(guide_item(r) for r in g_tba) if g_tba else "")
  + f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  + "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in g_faq)
  + f"<h2>Get the weekly release email</h2><p>What's Dropping covers what's releasing next, date and price changes, and a buy-or-skip verdict for each product.</p>{FORM}<p><small>Last updated: {tdate()}</small></p>")
g_list = g_items + g_tba
g_ld = [
 {"@context": "https://schema.org", "@type": "Article", "headline": G_H1, "url": g_url, "mainEntityOfPage": g_url, "image": OG_IMAGE, "datePublished": G_PUBLISHED, "dateModified": PD,
  "author": {"@id": f"{SITE_URL}/#org"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "isPartOf": {"@id": f"{SITE_URL}/#website"},
  "description": "Every Magic: The Gathering product releasing October to December 2026, with dates, prices, buy/skip verdicts and holiday gift picks."},
 {"@context": "https://schema.org", **ORG},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "MTG releases, October to December 2026", "numberOfItems": len(g_list),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate(g_list)]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{SITE_URL}/guides/"},
   {"@type": "ListItem", "position": 3, "name": "Fall/Holiday 2026 MTG releases", "item": g_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in g_faq]},
]
G_DESC = "Every MTG release for October, November and December 2026: sets, Commander decks, Secret Lair drops and bundles, with dates, prices, verdicts and gift picks."
page(G_TITLE, G_DESC, g_body, G_SLUG, g_ld)
# ---- Guide 2: Star Trek release guide (facts from Wizards' Collecting Star Trek article and WPN product listing; verdicts from releases.json) ----
ST_SRC = {"collect": "https://magic.wizards.com/en/news/feature/collecting-star-trek",
          "wpn": "https://wpn.wizards.com/en/products/star-trek"}
st_set = next(r for r in data if r["slug"] == "star-trek"); st_cmd = next(r for r in data if r["slug"] == "star-trek-commander")
ST_SLUG = "guides/star-trek-mtg-release-guide.html"; st_url = url(ST_SLUG)
ST_TITLE = "MTG Star Trek Release Guide: Prices, What to Buy | MTG Drops"
ST_H1 = f"Magic: The Gathering | Star Trek Release Guide ({nice_date(st_set)})"
ST_PUBLISHED = "2026-10-19"
def st_a(k, t="Wizards"): return f'<a href="{ST_SRC[k]}">{E(t)}</a>'
# Every product and MSRP below is from Wizards' Collecting article (MSRP list) and matches the WPN product listing.
ST_PRODUCTS = [
 ("Play Booster", 6.99, "14 cards: 7 commons (a stardates card replaces a common in 1 of 25 packs), 3 uncommons, 1 wildcard, 1 traditional foil of any rarity, 1 rare or mythic rare, 1 land, plus a double-sided token. 30 per box."),
 ("Collector Booster", 37.99, "15 cards, mostly foils and Booster Fun: 5 traditional foil commons, 3 traditional foil uncommons, 1 foil common or uncommon, 1 traditional foil basic, 1 traditional foil rare/mythic, 1 extended-art rare/mythic, 3 Booster Fun rares/mythics (1 foil), plus an art card or foil token. 12 per box. The only place the 7 actor-signed headliner cards appear."),
 ("Bundle", 69.99, "9 Play Boosters, 15 traditional foil + 15 non-foil basic lands (5 full-art in each), 1 traditional foil promo card, oversized spindown life counter, card-storage box, 2 reference cards."),
 ("Beam Me Up Bundle", 99.99, "8 Play Boosters, 1 Collector Booster, 2 of 8 traditional foil Spacecraft schematic promo cards, the same 30 lands and accessories as the Bundle."),
 ("Draft Night", 119.99, "12 Play Boosters, 1 Collector Booster, 90 basic lands, 10 double-sided tokens and a draft insert."),
 ("Scene Box (each)", 41.99, "Two versions (Enterprise-Q and Divergent Timeline): 3 Play Boosters, 6 traditional foil borderless scene cards, 6 art cards and a display easel."),
 ("Commander Deck (each)", 74.99, "Four decks; each is a ready-to-play 100-card deck with a traditional foil borderless face commander, 32 new-to-Magic cards, 10 double-sided tokens and a deck box."),
 ("Collector's Edition Commander Deck (each)", 159.99, "The same 100 cards in surge foil, including the face commander and the 10 tokens."),
]
ST_DECKS = [("Federation Fleet", "Jean-Luc Picard", "strengthen your crew and charge your starships"),
            ("Landing Party", "Commander Spock", "bonuses for controlling differently named lands, plus landfall"),
            ("Klingon Fury", "Worf", "attack several opponents at once to grow your Warriors"),
            ("We Are the Borg", "the Borg Queen", "Borg tokens and assimilating your opponents' creatures")]
ST_DATES = [("Prerelease events (local game stores)", "Nov 6–12, 2026"), ("MTG Arena release", "Nov 10, 2026"), ("Global tabletop release", "Nov 13, 2026"),
            ("MagicCon: Atlanta and World Championship 32", "Nov 13–15, 2026"), ("Magic Presents: To Boldly Go", "Nov 13, 2026 – Jan 28, 2027"),
            ("Commander Party, Round 1", "Nov 20–26, 2026"), ("Commander Party, Round 2", "Dec 11–17, 2026")]
pb = next(p for p in ST_PRODUCTS if p[0] == "Play Booster")[1]; cb = next(p for p in ST_PRODUCTS if p[0] == "Collector Booster")[1]
st_math = [("Bundle", f"9 Play Boosters alone are {fmt({'usd': 9*pb})} at MSRP, so the Bundle's {fmt({'usd': 69.99})} adds lands, a foil promo, a spindown and a storage box for about {fmt({'usd': 69.99-9*pb})}."),
           ("Beam Me Up Bundle", f"{fmt({'usd': 99.99})}, {fmt({'usd': 30.00})} more than the Bundle: you swap 1 Play Booster for 1 Collector Booster ({fmt({'usd': cb})} MSRP) and get 2 Spacecraft schematic promos instead of the single Bundle promo."),
           ("Draft Night", f"12 Play Boosters plus 1 Collector Booster are {fmt({'usd': 12*pb+cb})} at MSRP; the box is {fmt({'usd': 119.99})} and adds 90 lands and tokens.")]
st_vs = {"buy": "Buy", "wait": "Wait", "skip": "Skip", "mixed": "Mixed"}
st_faq = [
 ("When does MTG Star Trek release?", f"The global tabletop release is {nice_date(st_set)}. Prerelease events run Nov 6–12, 2026, and the set arrives on MTG Arena on Nov 10, 2026 (Wizards)."),
 ("How much does MTG Star Trek cost?", "Wizards' MSRPs: " + "; ".join(f"{n} {fmt({'usd': u})}" for n, u, _ in ST_PRODUCTS) + ". Store prices vary."),
 ("What are the Star Trek Commander decks?", "Four decks: " + "; ".join(f"{n} (led by {c}: {t})" for n, c, t in ST_DECKS) + f". Each is {fmt({'usd': 74.99})}, or {fmt({'usd': 159.99})} for the surge foil Collector's Edition."),
 ("Is MTG Star Trek legal in Standard?", "Yes. The main set (TRK) is legal in all formats. The Commander decks (TRC) and the stardates reprints (SDS) are legal in Commander, Legacy and Vintage, and individual cards are also legal wherever they were already legal (Wizards)."),
 ("Where do you find the signed Star Trek cards?", "Only in Collector Boosters. There are 7 different actor-signed headliner cards, about 250 copies of each, in Collector Boosters of any language (the signed cards are always in English). Wizards has not published per-pack odds."),
 ("Is there a Star Trek Beginner Box?", "Not any more: Wizards removed the Beginner Box from its Star Trek product article after the product was cancelled."),
 ("What should I buy from MTG Star Trek?", f"Our verdict on the set: {st_vs.get(st_set.get('verdict'), 'no verdict yet')}, for {st_set.get('gift_for', 'drafting and Trek fans')}. On the Commander decks: {st_vs.get(st_cmd.get('verdict'), 'no verdict yet')}, for {st_cmd.get('gift_for', 'Commander players')}."),
]
st_body = (f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › <a href="{BASE}/guides/">Guides</a> › Star Trek</nav><h1>{E(ST_H1)}</h1>'
  f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
  f'<p><b>Last updated:</b> {tdate()} · release {nice_date(st_set)} ({E(st_set["status"])})</p>'
  f'<p>Magic: The Gathering | Star Trek is a Universes Beyond set that releases on {nice_date(st_set)}, ahead of Star Trek\'s 60th anniversary. This guide covers every product, Wizards\' MSRPs, the four Commander decks, the key dates and what we think is worth buying. Facts are from Wizards\' {st_a("collect", "Collecting Magic: The Gathering | Star Trek")} article and the {st_a("wpn", "Wizards Play Network product listing")}; full product pages: <a href="{BASE}/p/{st_set["slug"]}.html">{E(st_set["name"])}</a> and <a href="{BASE}/p/{st_cmd["slug"]}.html">Star Trek Commander Decks</a>.</p>'
  "<h2>Key dates</h2><table><tr><th>Event</th><th>Date</th></tr>" + "".join(f"<tr><td>{E(a)}</td><td>{E(b)}</td></tr>" for a, b in ST_DATES) + f'</table><p><small>Dates per {st_a("collect")}.</small></p>'
  "<h2>Every product and price</h2><table><tr><th>Product</th><th>MSRP (USD)</th><th>What's inside</th></tr>" + "".join(f"<tr><td>{E(n)}</td><td>{fmt({'usd': u})}</td><td>{E(c)}</td></tr>" for n, u, c in ST_PRODUCTS)
  + f'</table><p><small>MSRPs and contents per {st_a("collect")} and the {st_a("wpn", "WPN listing")}. Stores set their own prices.</small></p>'
  "<h2>The four Commander decks</h2><p>Each deck is themed after a Star Trek crew, fleet or army (deck themes per Wizards' product descriptions):</p><ul>" + "".join(f"<li><b>{E(n)}</b>, led by {E(c)}: {E(t)}.</li>" for n, c, t in ST_DECKS)
  + f'</ul><p>Every deck is {fmt({"usd": 74.99})} MSRP, or {fmt({"usd": 159.99})} for the Collector\'s Edition, which has the same list in surge foil ({st_a("wpn")}).</p>'
  "<h2>Legality and mechanics</h2>"
  f'<p>The main set (TRK) is legal in all formats, including Standard. The Commander decks (TRC) and the 30 stardates reprints (SDS) are legal in Commander, Legacy and Vintage. New and returning mechanics include assimilate, face a dilemma, the federation ability word, and Spacecraft with station, returning from Edge of Eternities ({st_a("collect")}).</p>'
  "<h2>Booster Fun and chase cards</h2><ul>"
  "<li>7 actor-signed headliner cards, about 250 copies of each, only in Collector Boosters.</li>"
  "<li>30 stardates cards: reprints of cards from Magic's history with Star Trek art (non-foil in both booster types, traditional foil only in Collector Boosters).</li>"
  "<li>29 LCARS frame cards and all 10 shock lands in an LCARS frame (surge foil versions only in Collector Boosters).</li>"
  "<li>24 classic Enterprise poster-style cards and 25 borderless scene cards, plus 6 new-to-Magic scene cards in each Scene Box.</li>"
  f'</ul><p><small>Per {st_a("collect")}.</small></p>'
  "<h2>Event promos</h2>"
  f'<p>WPN Commander events give a Highly Illogical or Munitions Enthusiast promo; Magic Presents: To Boldly Go gives a traditional foil Solemn Simulacrum; Standard Showdown winners get a Burst Lightning or a second promo Wizards hasn\'t revealed yet. All while supplies last ({st_a("collect")}).</p>'
  "<h2>What to buy</h2>"
  f'<div class=card><h3><a href="{BASE}/p/{st_set["slug"]}.html">{E(st_set["name"])}</a></h3><p>{vtag(st_set)}{E(st_set["note"])}</p>' + (f'<p><b>Good gift for:</b> {E(st_set["gift_for"])}.</p>' if st_set.get("gift_for") else "") + f'{amz_btn(st_set)}</div>'
  f'<div class=card><h3><a href="{BASE}/p/{st_cmd["slug"]}.html">{E(st_cmd["name"])}</a></h3><p>{vtag(st_cmd)}{E(st_cmd["note"])}</p>' + (f'<p><b>Good gift for:</b> {E(st_cmd["gift_for"])}.</p>' if st_cmd.get("gift_for") else "") + f'{amz_btn(st_cmd)}</div>'
  "<h3>Value at MSRP</h3><p>Simple arithmetic from Wizards' MSRPs, so you can compare the boxes:</p><ul>" + "".join(f"<li><b>{E(a)}:</b> {E(b)}</li>" for a, b in st_math) + "</ul>"
  "<p>If you want to collect the signed cards or the surge foil Booster Fun, that is Collector Booster territory; for drafting or a first taste of the set, Play Boosters, a Bundle or Draft Night are the cheaper way in. Prices in stores often fall after release, so preordering mainly makes sense if you want the product on day one.</p>"
  f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in st_faq)
  + f'<p>More releases: <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>, the <a href="{BASE}/secret-lair.html">Secret Lair drop schedule</a> and the full <a href="{BASE}/">release calendar</a>.</p>'
  + f"<h2>Get the weekly release email</h2><p>What's Dropping covers what's releasing next, date and price changes, and a buy-or-skip verdict for each product.</p>{FORM}<p><small>Last updated: {tdate()}</small></p>")
ST_DESC = "MTG Star Trek release guide: Nov 13, 2026 release date, every product and MSRP, the four Commander decks, key dates, signed cards and what to buy."
st_ld = [
 {"@context": "https://schema.org", "@type": "Article", "headline": ST_H1, "url": st_url, "mainEntityOfPage": st_url, "image": OG_IMAGE, "datePublished": ST_PUBLISHED, "dateModified": PD,
  "author": {"@id": f"{SITE_URL}/#org"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "isPartOf": {"@id": f"{SITE_URL}/#website"},
  "about": {"@type": "Thing", "name": st_set["name"]}, "description": ST_DESC, "citation": list(ST_SRC.values())},
 {"@context": "https://schema.org", **ORG},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "Magic: The Gathering | Star Trek products", "numberOfItems": 2,
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate([st_set, st_cmd])]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{SITE_URL}/guides/"},
   {"@type": "ListItem", "position": 3, "name": "Star Trek release guide", "item": st_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in st_faq]},
]
page(ST_TITLE, ST_DESC, st_body, ST_SLUG, st_ld)
GUIDES = [(G_SLUG, G_H1, "Every Magic product from October to December 2026, grouped by month, with prices, buy/skip verdicts and holiday gift picks."),
          (ST_SLUG, ST_H1, "Everything in the Nov 13, 2026 Star Trek set: every product and MSRP, the four Commander decks, key dates, signed cards and what to buy.")]
gi_url = url("guides/index.html")
page("MTG Guides: Release Roundups & Gift Picks | MTG Drops", "MTG Drops guides: Magic: The Gathering release roundups, buying guides and gift picks, generated from our release calendar.",
     f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Guides</nav><h1>MTG Drops Guides</h1><p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
     + "".join(f'<div class=card><h2><a href="{BASE}/{p}">{E(t)}</a></h2><p>{E(d)}</p></div>' for p, t, d in GUIDES)
     + f'<p>Also see the <a href="{BASE}/secret-lair.html">Secret Lair drops hub</a> and the full <a href="{BASE}/">release calendar</a>.</p>{FORM}<p><small>Last updated: {tdate()}</small></p>',
     "guides/index.html",
     [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "MTG Drops Guides", "url": gi_url, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}},
      {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i+1, "url": url(p), "name": t} for i, (p, t, d) in enumerate(GUIDES)]},
      {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"}, {"@type": "ListItem", "position": 2, "name": "Guides", "item": gi_url}]}])
NL_TITLE = "What's Dropping: Weekly MTG Release Newsletter | MTG Drops"
NL_DESC = "What's Dropping is a free weekly MTG email, sent Mondays: upcoming sets, Commander decks and Secret Lair drops, date and price changes, and buy/skip calls."
nl_url = url("newsletter.html")
page(NL_TITLE, NL_DESC,
     f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Newsletter</nav><h1>What\'s Dropping</h1><p>One email a week: what releases, what\'s on preorder, buy or skip.</p>{FORM}'
     "<h2>What's in each issue</h2><p>What's Dropping is a free weekly email from MTG Drops. Each issue covers the Magic: The Gathering products coming up next, new announcements from Wizards of the Coast (sets, Commander decks, Secret Lair drops and Universes Beyond), date and price changes, and a short buy-or-skip verdict for each product. It's short enough to read in a couple of minutes.</p>"
     "<ul><li><b>This week and next:</b> what releases or goes on sale, with dates and MSRPs</li><li><b>New announcements:</b> sets, Commander precons and Secret Lair drops added to the calendar</li><li><b>Changes:</b> delays, sell-outs, date moves and price updates</li><li><b>Buy, wait or skip:</b> our short call on each product, the same verdicts as on the site</li></ul>"
     f'<h2>When it arrives</h2><p>Every Monday morning (US Central time). It is built from the same data as the <a href="{BASE}/">release calendar</a> and the <a href="{BASE}/secret-lair.html">Secret Lair schedule</a>, so nothing in the email contradicts the site. You can unsubscribe at any time from the link in every email, and we never share or sell your address.</p>'
     f'<h2>Prefer a calendar or RSS?</h2><p>Add every release to your calendar ({ics_link("calendar.ics")}) or follow the <a href="{BASE}/feed.xml">RSS feed</a>.</p>',
     "newsletter.html",
     [{"@context": "https://schema.org", "@type": "WebPage", "@id": nl_url + "#page", "name": NL_TITLE, "url": nl_url, "description": NL_DESC, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}},
      {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"}, {"@type": "ListItem", "position": 2, "name": "Newsletter", "item": nl_url}]}])
# ---- Sponsor media kit (/sponsor.html). No traffic, subscriber or price figures are published here: stats on request, rates by quote. ----
SPONSOR_EMAIL = "sponsors@mtgdrops.com"
sp_url = url("sponsor.html")
SP_TITLE = "Sponsor MTG Drops: Media Kit & Sponsor Policy | MTG Drops"
SP_DESC = "MTG Drops media kit: reach Magic: The Gathering players tracking releases, Secret Lair drops and Commander precons. Newsletter, banner and featured calendar placements."
SP_PLACEMENTS = [
 ("Newsletter sponsor slot", "A sponsor slot in What's Dropping, our free weekly release email, shown near the top of the issue and labeled Sponsored: a short message and a link."),
 ("Site banner", "A labeled sponsor banner on the release calendar home page and the Secret Lair hub, the pages readers check when a new drop or set is announced."),
 ("Featured calendar listing", "A highlighted, Sponsored-labeled card in the release calendar for a store, product or event. Featured listings sit alongside our normal listings and never replace or reorder Wizards of the Coast release data."),
 ("Product or guide page sponsor", "A labeled sponsor line on a relevant product page or buying guide, for example a store with stock of a particular Commander deck. Available for selected pages."),
]
SP_FIT = ["Local game stores and online retailers of sealed product and singles", "Accessory makers: sleeves, deck boxes, playmats, storage", "Card grading, shipping and collection tools", "Magic content creators, podcasts and events"]
SP_POLICY = [
 "Every paid placement is labeled Sponsored, on the site and in the newsletter, right next to the placement, so readers can tell it apart from our own content.",
 "Sponsor links carry rel=\"sponsored\" so search engines can identify them too.",
 "Sponsors never buy coverage or a verdict. Release dates, prices and buy/wait/skip verdicts are set by MTG Drops from official and reputable sources, and a sponsor's own products get the same verdicts as everyone else's.",
 "If we write about a product or company that is currently sponsoring us, we say so in that piece.",
 "Sponsorship is separate from our affiliate links. Some links on MTG Drops are affiliate links (Amazon Associates; TCGplayer links are marked sponsored), and we disclose that on every page where they appear: " + DISCLOSURE,
 "We may decline any sponsorship that doesn't fit our readers. Sponsors do not receive newsletter subscribers' email addresses.",
]
SP_ASK = ["Your company and what you'd like to promote", "Which placement(s) interest you and your preferred dates or weeks", "Your landing page URL", "Any campaign goals (awareness, a launch, a sale, an event)"]
sp_faq = [
 ("How much does it cost to sponsor MTG Drops?", f"Rates depend on the placement and dates. Contact {SPONSOR_EMAIL} for a quote."),
 ("How many readers does MTG Drops have?", f"Current site traffic and newsletter stats are available on request from {SPONSOR_EMAIL}."),
 ("Are sponsored placements labeled?", "Yes. Every paid placement is labeled Sponsored, and sponsor links use rel=\"sponsored\". Sponsors cannot buy a verdict or change our release data."),
 ("Who reads MTG Drops?", "Magic: The Gathering players who track upcoming releases: people planning set and Commander precon purchases, Secret Lair buyers watching sale dates, and gift buyers checking what's worth getting."),
]
sp_body = (f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Sponsor</nav><h1>Sponsor MTG Drops</h1>'
  f'<p>Reach Magic: The Gathering players while they plan their next purchase. Email <a href="mailto:{SPONSOR_EMAIL}">{SPONSOR_EMAIL}</a> for current stats and a quote.</p>'
  f'<h2>What MTG Drops is</h2><p>{E(ABOUT)} Every product has a release date, known prices, sources and a short buy/wait/skip verdict; the <a href="{BASE}/secret-lair.html">Secret Lair hub</a> tracks drops on sale now and coming up, and our <a href="{BASE}/guides/">guides</a> cover seasonal releases and big sets. <a href="{BASE}/newsletter.html">What\'s Dropping</a> is the free weekly email version.</p>'
  "<h2>Who reads it</h2><ul><li>MTG players tracking upcoming sets and Universes Beyond releases, and deciding what to preorder</li><li>Secret Lair buyers watching sale dates, prices and what's worth it</li><li>Commander players comparing precons before they buy</li><li>Gift buyers looking for a safe Magic purchase</li></ul>"
  "<p>Our readers arrive with buying intent, so sponsorships fit:</p><ul>" + "".join(f"<li>{E(x)}</li>" for x in SP_FIT) + "</ul>"
  f'<p><b>Audience numbers:</b> current traffic and newsletter stats are available on request at <a href="mailto:{SPONSOR_EMAIL}">{SPONSOR_EMAIL}</a>. We don\'t publish estimates.</p>'
  "<h2>Placements</h2>" + "".join(f"<div class=card><h3>{E(t)}</h3><p>{E(d)}</p><p><b>Rate:</b> contact us</p></div>" for t, d in SP_PLACEMENTS)
  + "<h2>Rates</h2><p>We quote each sponsorship based on placement, dates and length. There's no public rate card yet: contact us and we'll reply with availability and pricing.</p>"
  "<h2>Sponsorship and disclosure policy</h2><ul>" + "".join(f"<li>{E(x)}</li>" for x in SP_POLICY) + "</ul>"
  f'<h2>How to book</h2><p>Email <a href="mailto:{SPONSOR_EMAIL}">{SPONSOR_EMAIL}</a> with:</p><ul>' + "".join(f"<li>{E(x)}</li>" for x in SP_ASK) + "</ul>"
  "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in sp_faq)
  + f'<p><small>MTG Drops is independent and not affiliated with Wizards of the Coast. Last updated: {tdate()}</small></p>')
sp_ld = [
 {"@context": "https://schema.org", "@type": "WebPage", "name": SP_TITLE, "url": sp_url, "description": SP_DESC, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "about": {"@id": f"{SITE_URL}/#org"}},
 {"@context": "https://schema.org", **ORG, "contactPoint": {"@type": "ContactPoint", "contactType": "advertising and sponsorships", "email": SPONSOR_EMAIL, "availableLanguage": "English"}},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"}, {"@type": "ListItem", "position": 2, "name": "Sponsor", "item": sp_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in sp_faq]},
]
page(SP_TITLE, SP_DESC, sp_body, "sponsor.html", sp_ld)
items = "".join(f"<item><title>{E(r['name'])} — {r['release_date']}</title><link>{SITE_URL}/p/{r['slug']}.html</link><guid>{SITE_URL}/p/{r['slug']}.html</guid><description>{E(r['note'])}</description></item>" for r in up if not r.get("placeholder"))
open("dist/feed.xml", "w").write(f'<?xml version="1.0"?><rss version="2.0"><channel><title>MTG Drops</title><link>{SITE_URL}/</link><description>Upcoming MTG releases</description>{items}</channel></rss>')
def lastmod(p): return new_dates[(p + "index.html") if p == "" or p.endswith("/") else p]["date"]
open("dist/sitemap.xml","w").write('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{SITE_URL}/{p}</loc><lastmod>{lastmod(p)}</lastmod></url>" for p in ["","secret-lair.html","guides/"]+[g[0] for g in GUIDES]+["newsletter.html","sponsor.html"]+[f"p/{r['slug']}.html" for r in public])+"</urlset>")
# ---- iCalendar feeds (RFC 5545): /calendar.ics (every dated release) and /secret-lair.ics (Secret Lair only) ----
# All-day events (DTSTART;VALUE=DATE, DTEND = next day), stable UIDs (<slug>@mtgdrops.com), DTSTAMP from the entry's
# last_checked date so an unchanged entry produces byte-identical output, CRLF line endings, lines folded at 75 octets.
def ics_esc(t): return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
def ics_fold(line):
    b = line.encode("utf-8"); out = []; first = True
    while b:
        n = 75 if first else 74; cut = min(n, len(b))
        while cut < len(b) and (b[cut] & 0xC0) == 0x80: cut -= 1  # never split a UTF-8 sequence
        out.append((b"" if first else b" ") + b[:cut]); b = b[cut:]; first = False
    return b"\r\n".join(out)
def ics_events(rs):
    ev = []
    for r in rs:
        if not dated(r) or (r.get("placeholder") and r["status"] != "confirmed"): continue
        d0 = datetime.date.fromisoformat(r["release_date"]); link = f"{SITE_URL}/p/{r['slug']}.html" if not r.get("placeholder") else f"{SITE_URL}/"
        stamp = (r.get("last_checked") or r["release_date"]).replace("-", "") + "T000000Z"
        flag = " (delayed)" if r.get("delayed") else " (sold out)" if r.get("sold_out") else "" if r["status"] == "confirmed" else f" ({r['status']})"
        ev.append((r["slug"], d0, d0 + datetime.timedelta(days=1), short_name(r) + flag, f"{r['type']}. {r['note']} Details: {link}", link, stamp))
        if r.get("prerelease") == "Nov 6–12, 2026" and r["slug"] == "star-trek":  # prerelease week as its own multi-day event
            ev.append((r["slug"] + "-prerelease", datetime.date(2026, 11, 6), datetime.date(2026, 11, 13), short_name(r) + " prerelease (local game stores)", f"Prerelease events at local game stores, the week before the {nice_date(r)} release (Wizards). Details: {link}", link, stamp))
    return ev
def ics(name, desc, rs):
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MTG Drops//Release calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:" + ics_esc(name), "X-WR-CALDESC:" + ics_esc(desc), "REFRESH-INTERVAL;VALUE=DURATION:P1D", "X-PUBLISHED-TTL:P1D"]
    for uid, a, b, summ, dsc, link, stamp in ics_events(rs):
        L += ["BEGIN:VEVENT", f"UID:{uid}@mtgdrops.com", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{a:%Y%m%d}", f"DTEND;VALUE=DATE:{b:%Y%m%d}",
              "SUMMARY:" + ics_esc(summ), "DESCRIPTION:" + ics_esc(dsc), f"URL:{link}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return b"".join(ics_fold(l) + b"\r\n" for l in L)
open("dist/calendar.ics", "wb").write(ics("MTG Drops: MTG release calendar", "Every upcoming Magic: The Gathering release from mtgdrops.com", data))
open("dist/secret-lair.ics", "wb").write(ics("MTG Drops: Secret Lair drops", "Secret Lair drop dates from mtgdrops.com/secret-lair.html", [r for r in data if r["type"] == "Secret Lair"]))
# Persist page dates (committed). Only pages built this run are kept.
_pd_new = json.dumps(dict(sorted(new_dates.items())), indent=1, sort_keys=True) + "\n"
if not os.path.exists(PAGE_DATES_FILE) or open(PAGE_DATES_FILE).read() != _pd_new: open(PAGE_DATES_FILE, "w").write(_pd_new)
open("dist/robots.txt","w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
open("dist/llms.txt","w").write(f"""# MTG Drops

> MTG Drops ({SITE_URL}/) is an independent release calendar for Magic: The Gathering: upcoming sets, Commander precons, Secret Lair drops and Universes Beyond products, each with release dates, known prices, a short buy/skip verdict and a free weekly newsletter. Not affiliated with Wizards of the Coast, and not a Discord bot or eBay monitor (it is unrelated to the "MTG Drop" Discord eBay-monitoring tool). Some links are affiliate links (Amazon Associates, TCGplayer).

## Search

{CONTEXT7_NOTE}

## Main pages
- [Release calendar]({SITE_URL}/): every upcoming MTG product grouped by month
- [Secret Lair drops]({SITE_URL}/secret-lair.html): Secret Lair schedule (on sale now, upcoming, recent), prices and buy/skip verdicts
- [Guides]({SITE_URL}/guides/): release roundups and gift picks
""" + "".join(f"- [{t}]({url(p)}): {d}\n" for p, t, d in GUIDES) + f"""- [Newsletter]({SITE_URL}/newsletter.html): weekly "What's Dropping" email
- [Sponsor]({SITE_URL}/sponsor.html): media kit, sponsorship placements and disclosure policy (contact sponsors@mtgdrops.com)
- [RSS feed]({SITE_URL}/feed.xml)
- [Calendar feed (.ics), every release]({SITE_URL}/calendar.ics) and [Secret Lair only]({SITE_URL}/secret-lair.ics)
- [Sitemap]({SITE_URL}/sitemap.xml)

## Secret Lair drops

""" + SL_LLMS + """
## Releases
""" + "".join(f"- [{r['name']}]({SITE_URL}/p/{r['slug']}.html): {nice_date(r)}, {r['type']}, {r['status']}\n" for r in up if not r.get("placeholder")))
open("dist/CNAME","w").write("mtgdrops.com\n")
print(f"built {len(data)} products")
