#!/usr/bin/env python3
"""MTG Drops static site builder. Usage: python3 build.py  -> dist/"""
import json, html, os, shutil, urllib.parse, datetime
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
def tcg(name):
    u = "https://www.tcgplayer.com/search/magic/product?q=" + urllib.parse.quote(name)
    return u + ("&partner=" + urllib.parse.quote(AFFILIATE_ID) if AFFILIATE_ID else "")
AMAZON_TAG = "mtgdrops-20"  # Amazon Associates tag
DISCLOSURE = "As an Amazon Associate, MTG Drops earns from qualifying purchases. Some links on this site are affiliate links."
def amazon(r):
    # Search URL (not /dp/) to avoid dead product links; only purchasable retail products carry amazon_query
    if r.get("amazon_query"):
        return "https://www.amazon.com/s?k=" + urllib.parse.quote_plus(r["amazon_query"]) + "&tag=" + AMAZON_TAG
def amz_btn(r):
    u = amazon(r)
    if not u: return ""
    label = "Buy on Amazon" if r["release_date"] <= datetime.date.today().isoformat() else "Pre-order on Amazon"
    return f'<p><a class=amz href="{E(u)}" rel="sponsored nofollow noopener" target="_blank">{label}</a></p>'
TODAY = datetime.date.today()
today = TODAY.isoformat()
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
def page(title, desc, body, path, jsonld=(), noindex=False):
    desc = trim(desc); u = url(path)
    robots = "<meta name=robots content=noindex>" if noindex else ""
    lds = "".join(ld(o) for o in jsonld)
    p = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name=description content="{E(desc)}">{robots}<link rel=canonical href="{u}">
<meta property=og:title content="{E(title)}"><meta property=og:description content="{E(desc)}"><meta property=og:type content=website><meta property=og:url content="{u}"><meta property=og:image content="{OG_IMAGE}"><meta property=og:image:width content=1200><meta property=og:image:height content=630><meta name=twitter:card content=summary_large_image>
<link rel=alternate type=application/rss+xml href="{BASE}/feed.xml" title="MTG Drops"><meta name='impact-site-verification' value='78f2b2fa-0831-48d2-a460-e2e3fa5a4eab'><meta name='impact-site-verification' value='c76059e5-ec5e-42d1-84a8-d9b58d1e5b68'><link rel=stylesheet href="{BASE}/style.css"><meta name="context7-site-verification" content="{CONTEXT7_SITE_KEY}">{lds}</head><body>
<blockquote data-context7-ask="true" aria-hidden="true" style="position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0">
  <h2>Search</h2>
  <p>{E(CONTEXT7_NOTE, quote=False)}</p>
</blockquote>
<header><a href="{BASE}/"><b>MTG Drops</b></a><a href="{BASE}/secret-lair.html">Secret Lair</a><a href="{BASE}/guides/">Guides</a><a href="{BASE}/newsletter.html">Newsletter</a><a href="{BASE}/sponsor.html">Sponsor</a><a href="{BASE}/feed.xml">RSS</a></header>
<main>{body}</main><footer><p><small><a href="{BASE}/">Release calendar</a> · <a href="{BASE}/secret-lair.html">Secret Lair drops</a> · <a href="{BASE}/guides/">Guides</a> · <a href="{BASE}/newsletter.html">Newsletter</a> · <a href="{BASE}/feed.xml">RSS</a></small></p><small>Dates from official/community sources; verify before buying. {E(DISCLOSURE)} Not affiliated with Wizards of the Coast.</small></footer></body></html>"""
    out = os.path.join("dist", path); os.makedirs(os.path.dirname(out), exist_ok=True); open(out, "w").write(p)
def card(r):
    if r.get("placeholder"):
        return f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span> <span class=st>{E(r["status"])}</span><h3>{E(r["name"])}</h3><div>{nice_date(r)}</div><p>{E(r["note"])}</p></div>'
    st = "" if r["status"] == "confirmed" else f' <span class=st>{E(r["status"])}</span>'
    return f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span>{st}<h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a></h3><div>{nice_date(r)}</div><p>{E(r["note"])}</p>{amz_btn(r)}</div>'
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
up = [r for r in data if r["release_date"] >= today]  # includes TBA (sorts after digits)
up = up + [r for r in data if r["release_date"] < today]
public = [r for r in data if not r.get("placeholder")]
btns = '<button class=on data-f="">All</button>' + "".join(f'<button data-f="{E(t)}">{E(t)}</button>' for t in types)
js = "<script>document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.f button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.card').forEach(c=>c.style.display=!b.dataset.f||c.dataset.type==b.dataset.f?'':'none')})</script>"
groups = {}
for r in up: groups.setdefault(mon_yyyy(r) if r["release_date"] >= today else "Already released", []).append(r)
months = "".join(f"<h2>{E(g)}</h2>" + "".join(card(r) for r in rs) for g, rs in groups.items())
ABOUT = "MTG Drops is a free Magic: The Gathering release calendar: every upcoming set, Commander precon, Universes Beyond and Secret Lair drop, with dates, prices, buy/skip verdicts and a weekly newsletter. Not affiliated with Wizards of the Coast, and not a Discord bot or eBay monitor."
HOME_DESC = "MTG Drops: free Magic: The Gathering release calendar. Every set, precon, Universes Beyond and Secret Lair drop, with dates, prices and buy/skip verdicts."
ORG = {"@type": "Organization", "@id": f"{SITE_URL}/#org", "name": "MTG Drops", "url": f"{SITE_URL}/", "logo": OG_IMAGE, "description": ABOUT}
home_ld = [{"@context": "https://schema.org", "@type": "WebSite", "@id": f"{SITE_URL}/#website", "name": "MTG Drops", "url": f"{SITE_URL}/", "description": ABOUT, "publisher": {"@id": f"{SITE_URL}/#org"}},
           {"@context": "https://schema.org", **ORG},
           {"@context": "https://schema.org", "@type": "ItemList", "name": "Upcoming Magic: The Gathering releases", "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate([r for r in up if not r.get("placeholder")])]}]
page("MTG Drops — Every upcoming MTG release, one calendar", HOME_DESC,
     f"<h1>What's dropping in Magic</h1><p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p><p>Every upcoming MTG product, with a short buy/skip note. New: <a href=\"{BASE}/guides/mtg-releases-fall-holiday-2026.html\">every MTG product releasing this fall/holiday 2026</a>, with gift picks, and the <a href=\"{BASE}/secret-lair.html\">Secret Lair drop schedule</a>.</p>{FORM}<p class=disc><small>{E(DISCLOSURE)}</small></p><div class=f>{btns}</div>" + months + js, "index.html", home_ld)
def title_for(r):
    sn = short_name(r); m = mon_yyyy(r).replace("Date TBA", "TBA")
    for t in (f"{sn} Release Date ({m}), Price & Preorder | MTG Drops", f"{sn} Release Date ({m}) | MTG Drops", f"{sn} Release Date, {m} | MTG Drops", f"{sn} Release Date | MTG Drops", f"{sn} ({m}) | MTG Drops", f"{sn} | MTG Drops"):
        if len(t) <= 60: return t
    return t
def related(r):
    if r.get("placeholder"): pool = public
    else: pool = [x for x in public if x is not r]
    pool = [x for x in pool if x is not r]
    key = lambda x: (0, abs((datetime.date.fromisoformat(x["release_date"]) - datetime.date.fromisoformat(r["release_date"])).days)) if dated(x) and dated(r) else ((1, 0) if not dated(x) else (2, 0))
    return sorted(pool, key=key)[:4]
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
    facts = ("<h2>Key facts</h2><ul>" + "".join(f"<li>{E(f)}</li>" for f in r["facts"]) + "</ul>") if r.get("facts") else ""
    ti = TYPE_INFO.get(r["type"]); tinfo = f"<h2>{E(ti[0])}</h2><p>{E(ti[1])}</p>" if ti else ""
    howto = f"<h2>{HOWTO[0]}</h2><p>{E(HOWTO[1])}</p>" if not r.get("placeholder") and (not dated(r) or r["release_date"] > today) else ""
    rel = related(r)
    relhtml = "<h2>Related releases</h2><ul>" + "".join(f'<li><a href="{BASE}/p/{x["slug"]}.html">{E(x["name"])}</a> — {nice_date(x)}</li>' for x in rel) + "</ul>"
    faq = [(f"When does {sn} release?", f"{nice_date(r)} ({r['status']})." + (f" {r['window']}." if r.get("window") else "") if dated(r) else f"The release date is TBA ({r['status']})." + (f" {r['window']}." if r.get("window") else "")),
           (f"How much does {sn} cost?", "; ".join(f"{p['label']}: {fmt(p)}" for p in prices) + "." if prices else "Pricing has not been announced yet (TBA)."),
           (f"Should I buy {sn}?", r["note"])]
    if r.get("contents"): faq.append((f"What's in {sn}?", "; ".join(r["contents"]) + "."))
    faqhtml = "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faq)
    prod = {"@context": "https://schema.org", "@type": "Product", "name": r["name"], "url": pu, "image": OG_IMAGE, "category": r["type"], "brand": {"@type": "Brand", "name": "Wizards of the Coast"}, "description": trim(r["note"], 300)}
    if dated(r): prod["releaseDate"] = r["release_date"]
    offers = [p for p in prices if p.get("offer", True)]
    avail = "https://schema.org/InStock" if dated(r) and r["release_date"] <= today else "https://schema.org/PreOrder"
    if offers:
        prod["offers"] = [{"@type": "Offer", "name": p["label"], "price": f"{p['usd']:.2f}", "priceCurrency": p.get("currency", "USD"), "availability": avail, "url": pu} for p in offers]
        main_ld = prod
    else:
        main_ld = {"@context": "https://schema.org", "@type": "WebPage", "name": title_for(r), "url": pu, "description": trim(r["note"], 300), "isPartOf": {"@id": f"{SITE_URL}/#website"}, "about": {"@type": "Thing", "name": r["name"]}}
    bc = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
        {"@type": "ListItem", "position": 2, "name": r["type"], "item": f"{SITE_URL}/secret-lair.html" if r["type"] == "Secret Lair" else f"{SITE_URL}/"},
        {"@type": "ListItem", "position": 3, "name": r["name"], "item": pu}]}
    crumbs = f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › {(f'<a href="{BASE}/secret-lair.html">Secret Lair</a>' if r["type"] == "Secret Lair" else E(r["type"]))} › {E(sn)}</nav>{hubl}'
    desc = f"{sn} release date: {nice_date(r)}. " + r["note"]
    page(title_for(r), desc,
         f'{crumbs}<span class=t>{E(r["type"])}</span><h1>{E(r["name"])}</h1><p><b>Release:</b> {nice_date(r)} ({E(r["status"])})</p>{win}<h2>Price</h2>{ptab}{contents}{facts}<h2>Buy or skip?</h2><p>{E(r["note"])}</p><p><a href="{tcg(r["name"])}" rel="sponsored nofollow">Check prices on TCGplayer</a></p>{amz_btn(r)}{"<p class=disc><small>"+E(DISCLOSURE)+"</small></p>" if amazon(r) else ""}{tinfo}{howto}{relhtml}{faqhtml}<p><small>Source: <a href="{E(r["source"])}">{E(r["source"])}</a></small></p>{fsrc}<p><small>Last updated: {today}</small></p>{FORM}',
         f"p/{r['slug']}.html", [main_ld, bc], noindex=bool(r.get("placeholder")))
# ---- Secret Lair hub (/secret-lair.html): generated from releases.json, so data updates keep it current ----
SL_SRC = {"about": "https://secretlair.wizards.com/us/en/about-us",
          "faq": "https://secretlair-support.wizards.com/hc/en-us/articles/45369886769300-About-Secret-Lair-FAQ",
          "lpr": "https://magic.wizards.com/en/news/announcements/speeding-up-secret-lair-shipping",
          "queue": "https://magic.wizards.com/en/news/announcements/secret-lair-corn-maze-superdrop"}
SL_ONSALE_DAYS = 30  # with no known sale_end, a drop counts as "on sale now" for this many days after it opens
sl = [r for r in data if r["type"] == "Secret Lair" and not r.get("placeholder")]
def sl_bucket(r):
    if not dated(r) or r["release_date"] > today: return "up"
    if r.get("sale_end"): return "now" if r["sale_end"] >= today else "past"
    return "now" if (TODAY - datetime.date.fromisoformat(r["release_date"])).days <= SL_ONSALE_DAYS else "past"
sl_now = sorted([r for r in sl if sl_bucket(r) == "now"], key=lambda r: r["release_date"], reverse=True)
sl_up = [r for r in sl if sl_bucket(r) == "up"]  # data is date-sorted; TBA sorts last
sl_past = sorted([r for r in sl if sl_bucket(r) == "past"], key=lambda r: r["release_date"], reverse=True)
def sl_price(r):
    ps = r.get("prices") or []
    if not ps: return "TBA"
    return "; ".join(f"{p['label']} {fmt(p)}" for p in ps[:3]) + ("; more options on the product page" if len(ps) > 3 else "")
def sl_when(r):
    if not dated(r): return "Date TBA"
    b = sl_bucket(r)
    return ("On sale since " if b == "now" else "Went on sale " if b == "past" else "On sale ") + nice_date(r)
def sl_card(r):
    cont = trim("; ".join(r["contents"]), 220) if r.get("contents") else "Contents TBA"
    st = "" if r["status"] == "confirmed" else f' <span class=st>{E(r["status"])}</span>'
    return (f'<div class=card data-type="Secret Lair"><h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a>{st}</h3>'
            f'<p><b>Date:</b> {E(sl_when(r))}</p>' + (f'<p><b>Sale details:</b> {E(r["window"])}</p>' if r.get("window") else "") +
            f'<p><b>Price:</b> {E(sl_price(r))}</p><p><b>Contents:</b> {E(cont)}</p><p><b>Our verdict:</b> {E(r["note"])}</p>'
            f'<p><a href="{BASE}/p/{r["slug"]}.html">Full details, card list and sources →</a></p></div>')
def sl_section(h, rs, empty):
    return f"<h2>{E(h)}</h2>" + ("".join(sl_card(r) for r in rs) if rs else f"<p>{E(empty)}</p>")
nxt = next((r for r in sl_up if dated(r)), None)
def names(rs): return "; ".join(f"{short_name(r)} ({nice_date(r) if dated(r) else 'date TBA'})" for r in rs)
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
SL_DESC = ("Secret Lair release schedule: drops on sale now, upcoming Secret Lair drops and recent sales, with dates, prices, card lists and buy/skip verdicts. Updated " + today + ".")
sl_ld = [
 {"@context": "https://schema.org", "@type": "CollectionPage", "@id": sl_url + "#page", "name": SL_TITLE, "url": sl_url, "description": trim(SL_DESC, 300), "dateModified": today, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}},
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
     f'<p><b>Last updated:</b> {today} · {len(sl_now)} on sale now · {len(sl_up)} upcoming · {len(sl_past)} recent / ended</p>'
     + sl_intro + f'<p>Planning holiday buys? See <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>, sets and Commander decks included.</p>'
     + sl_section("On sale now", sl_now, "No Secret Lair sale has opened in the last few weeks. See Upcoming below.")
     + sl_section("Upcoming Secret Lair drops", sl_up, "No upcoming Secret Lair drops are announced right now.")
     + sl_section("Recent / ended", sl_past, "Nothing here yet.")
     + '<p><small>Drops opened more than ' + str(SL_ONSALE_DAYS) + ' days ago are listed as recent / ended unless an end date is known; limited print runs may sell out sooner or stay in stock longer, so check MagicSecretLair.com.</small></p>'
     + "<h2>Secret Lair FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in sl_faq)
     + f'<h2>Get new Secret Lair drops by email</h2><p>What\'s Dropping is our free weekly email: new Secret Lair announcements, sale dates and a buy-or-skip verdict for each drop.</p>{FORM}'
     + f'<p class=disc><small>{E(DISCLOSURE)}</small></p><p><small>Last updated: {today}</small></p>',
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
    st = "" if r["status"] == "confirmed" else f' <span class=st>{E(r["status"])}</span>'
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
  f'<p><b>Last updated:</b> {today} · {len(g_items)} products from October to December 2026</p>'
  f'<p>Every Magic: The Gathering product on our calendar for October, November and December 2026: sets, Commander decks, Secret Lair drops, bundles and special releases, with release dates, MSRPs and our buy/skip verdict. Secret Lair sales are tracked on the <a href="{BASE}/secret-lair.html">Secret Lair hub</a>.</p>'
  "<h2>Best picks for gifts</h2>" + ("<p>Only products we already rate as a buy, and who each one suits:</p><ul>" + "".join(f'<li><a href="{BASE}/p/{r["slug"]}.html">{E(short_name(r))}</a> ({nice_date(r)}): for {E(r["gift_for"])}.</li>' for r in g_gifts) + "</ul>" if g_gifts else "<p>No buy-rated products this season yet.</p>")
  + "".join(f"<h2>{g_month_name(m)}</h2>" + ("".join(guide_item(r) for r in rs) if rs else "<p>Nothing scheduled yet.</p>") for m, rs in g_by.items())
  + ("<h2>Announced, no date yet</h2><p>Announced but not yet scheduled, so these may or may not land before the end of 2026.</p>" + "".join(guide_item(r) for r in g_tba) if g_tba else "")
  + f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  + "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in g_faq)
  + f"<h2>Get the weekly release email</h2><p>What's Dropping covers what's releasing next, date and price changes, and a buy-or-skip verdict for each product.</p>{FORM}<p><small>Last updated: {today}</small></p>")
g_list = g_items + g_tba
g_ld = [
 {"@context": "https://schema.org", "@type": "Article", "headline": G_H1, "url": g_url, "mainEntityOfPage": g_url, "image": OG_IMAGE, "datePublished": G_PUBLISHED, "dateModified": today,
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
GUIDES = [(G_SLUG, G_H1, "Every Magic product from October to December 2026, grouped by month, with prices, buy/skip verdicts and holiday gift picks.")]
gi_url = url("guides/index.html")
page("MTG Guides: Release Roundups & Gift Picks | MTG Drops", "MTG Drops guides: Magic: The Gathering release roundups, buying guides and gift picks, generated from our release calendar.",
     f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Guides</nav><h1>MTG Drops Guides</h1><p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
     + "".join(f'<div class=card><h2><a href="{BASE}/{p}">{E(t)}</a></h2><p>{E(d)}</p></div>' for p, t, d in GUIDES)
     + f'<p>Also see the <a href="{BASE}/secret-lair.html">Secret Lair drops hub</a> and the full <a href="{BASE}/">release calendar</a>.</p>{FORM}<p><small>Last updated: {today}</small></p>',
     "guides/index.html",
     [{"@context": "https://schema.org", "@type": "CollectionPage", "name": "MTG Drops Guides", "url": gi_url, "dateModified": today, "isPartOf": {"@id": f"{SITE_URL}/#website"}},
      {"@context": "https://schema.org", "@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": i+1, "url": url(p), "name": t} for i, (p, t, d) in enumerate(GUIDES)]},
      {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"}, {"@type": "ListItem", "position": 2, "name": "Guides", "item": gi_url}]}])
page("What's Dropping newsletter | MTG Drops", "Weekly MTG release newsletter.", f"<h1>What's Dropping</h1><p>One email a week: what releases, what's on preorder, buy or skip.</p><p>What's Dropping is a free weekly email from MTG Drops. Each issue covers the Magic: The Gathering products coming up next, new announcements from Wizards of the Coast (sets, Commander decks, Secret Lair drops and Universes Beyond), date and price changes, and a short buy-or-skip verdict for each product. It's short enough to read in a couple of minutes, and you can unsubscribe at any time from the link in every email.</p>{FORM}", "newsletter.html")
page("Sponsor MTG Drops", "Sponsor the MTG Drops MTG release calendar and newsletter.", "<h1>Sponsor MTG Drops</h1><p>Reach Magic players planning their next purchase: calendar placements and the weekly What's Dropping newsletter.</p><ul><li>Newsletter top slot (weekly)</li><li>Featured calendar card</li><li>Product-page sponsor</li></ul><p>MTG Drops readers are Magic: The Gathering players checking release dates, prices and preorders, so sponsorships fit game stores, singles and sealed retailers, accessory makers and Magic content creators.</p><p>Contact: sponsors@mtgdrops.com (placeholder)</p>", "sponsor.html")
items = "".join(f"<item><title>{E(r['name'])} — {r['release_date']}</title><link>{SITE_URL}/p/{r['slug']}.html</link><guid>{SITE_URL}/p/{r['slug']}.html</guid><description>{E(r['note'])}</description></item>" for r in up if not r.get("placeholder"))
open("dist/feed.xml", "w").write(f'<?xml version="1.0"?><rss version="2.0"><channel><title>MTG Drops</title><link>{SITE_URL}/</link><description>Upcoming MTG releases</description>{items}</channel></rss>')
open("dist/sitemap.xml","w").write('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{SITE_URL}/{p}</loc><lastmod>{today}</lastmod></url>" for p in ["","secret-lair.html","guides/"]+[g[0] for g in GUIDES]+["newsletter.html","sponsor.html"]+[f"p/{r['slug']}.html" for r in public])+"</urlset>")
open("dist/robots.txt","w").write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
open("dist/llms.txt","w").write(f"""# MTG Drops

> MTG Drops ({SITE_URL}/) is an independent release calendar for Magic: The Gathering: upcoming sets, Commander precons, Secret Lair drops and Universes Beyond products, each with release dates, known prices, a short buy/skip verdict and a free weekly newsletter. Not affiliated with Wizards of the Coast, and not a Discord bot or eBay monitor (it is unrelated to the "MTG Drop" Discord eBay-monitoring tool). Some links are affiliate links (Amazon Associates, TCGplayer).

## Search

{CONTEXT7_NOTE}

## Main pages
- [Release calendar]({SITE_URL}/): every upcoming MTG product grouped by month
- [Secret Lair drops]({SITE_URL}/secret-lair.html): Secret Lair schedule (on sale now, upcoming, recent), prices and buy/skip verdicts
- [Guides]({SITE_URL}/guides/): release roundups and gift picks
""" + "".join(f"- [{t}]({url(p)}): {d}\n" for p, t, d in GUIDES) + """- [Newsletter]({SITE_URL}/newsletter.html): weekly "What's Dropping" email
- [RSS feed]({SITE_URL}/feed.xml)
- [Sitemap]({SITE_URL}/sitemap.xml)

## Secret Lair drops

""" + SL_LLMS + """
## Releases
""" + "".join(f"- [{r['name']}]({SITE_URL}/p/{r['slug']}.html): {nice_date(r)}, {r['type']}, {r['status']}\n" for r in up if not r.get("placeholder")))
open("dist/CNAME","w").write("mtgdrops.com\n")
print(f"built {len(data)} products")
