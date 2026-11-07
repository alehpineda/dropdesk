#!/usr/bin/env python3
"""MTG Drops static site builder. Usage: python3 build.py  -> dist/"""
import json, html, os, re, shutil, urllib.parse, datetime, hashlib
# TCGplayer Impact (contract accepted 2026-10-31). Tracking link from Active Contracts.
# Deep links append ?u=<percent-encoded landing page> (Impact: "Create a Deep Link for an Ad").
# Path is /c/{partner}/{ad}/{campaign}. The old www.tcgplayer.com ?partner= query is not this program.
IMPACT_PARTNER_ID = "7984768"         # Impact account / media partner id
IMPACT_AD_ID = "1780961"
IMPACT_CAMPAIGN_ID = "21018"
IMPACT_MEDIA_PROPERTY_ID = "9018299"  # mtgdrops.com channel in Create-a-link; not a tracking-path segment
TCG_IMPACT_BASE = f"https://partner.tcgplayer.com/c/{IMPACT_PARTNER_ID}/{IMPACT_AD_ID}/{IMPACT_CAMPAIGN_ID}"
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
    dest = "https://www.tcgplayer.com/search/magic/product?q=" + urllib.parse.quote(name)
    # safe="" percent-encodes the destination, including its already-encoded q=, so one decode restores the search URL.
    # IMPACT_MEDIA_PROPERTY_ID stays off the click URL: the contract tracking link does not include it.
    return TCG_IMPACT_BASE + "?u=" + urllib.parse.quote(dest, safe="")
AMAZON_TAG = "mtgdrops-20"  # Amazon Associates tag
DISCLOSURE = "As an Amazon Associate, MTG Drops earns from qualifying purchases. MTG Drops also earns a commission on qualifying purchases through TCGplayer affiliate links. Some links on this site are affiliate links."
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
<link rel=alternate type=application/rss+xml href="{BASE}/feed.xml" title="MTG Drops"><link rel="alternate" type="text/plain" href="{BASE}/llms.txt" title="llms.txt"><link rel="sitemap" type="application/xml" href="{BASE}/sitemap.xml"><meta name='impact-site-verification' value='78f2b2fa-0831-48d2-a460-e2e3fa5a4eab'><meta name='impact-site-verification' value='c76059e5-ec5e-42d1-84a8-d9b58d1e5b68'><link rel=icon href="{BASE}/favicon.ico" sizes=any><link rel=icon type=image/png sizes=192x192 href="{BASE}/icon-192.png"><link rel=apple-touch-icon href="{BASE}/icon-192.png"><link rel=stylesheet href="{BASE}/style.css"><meta name="context7-site-verification" content="{CONTEXT7_SITE_KEY}">{lds}</head><body>
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
first27 = next((g for g in groups if g.endswith("2027")), None)
months = "".join(f"<h2>{E(g)}</h2>" + (f'<p>Planning ahead? See the full <a href="{BASE}/guides/mtg-2027-release-schedule.html">MTG 2027 release schedule</a>.</p>' if g == first27 else "") + "".join(card(r) for r in rs) for g, rs in groups.items())
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
# Next Secret Lair answer (home line, home FAQ, hub card, hub FAQ). Rolls forward with the build date: the next dated,
# not-delayed, not-sold-out Secret Lair sale that hasn't opened yet (a drop stays "next" on its sale day only until its opening hour,
# e.g. 9 AM PT; the workflow rebuilds after that hour), then the one after it.
# If nothing is dated, the answer says the next drop is TBA; dates only ever come from releases.json.
def sl_sale_open(r):
    """True once a Secret Lair sale has opened: any earlier day, or sale day at/after its opening hour (from the window, default 9 AM PT).
    Uses the real clock only for a normal build; a BUILD_DATE test build treats sale day as not yet open."""
    if r["release_date"] < today: return True
    if r["release_date"] > today or os.environ.get("BUILD_DATE"): return False
    from zoneinfo import ZoneInfo
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([AP])M PT", r.get("window") or "")
    h, mi = ((int(m.group(1)) % 12 + (12 if m.group(3) == "P" else 0)), int(m.group(2) or 0)) if m else (9, 0)
    now = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    return now.date().isoformat() > today or (now.hour, now.minute) >= (h, mi)
sl_dated_next = sorted([r for r in data if r["type"] == "Secret Lair" and not r.get("placeholder") and dated(r) and not r.get("delayed")
                        and not r.get("sold_out") and not sl_sale_open(r)], key=lambda r: r["release_date"])
h_sl = sl_dated_next[0] if sl_dated_next else None          # next dated sale (None = TBA)
sl_after = sl_dated_next[1] if len(sl_dated_next) > 1 else None
h_sold = [r for r in public if r.get("sold_out")]
# Curated wording for drops whose sale time/verdict we re-checked by hand. Each entry is used only while its anchors are still
# in that release's data (window/note), so editing the data can't make the copy contradict it; otherwise the generic copy is used.
# Verdict phrases are the ones already in each release's note (no new verdicts).
SL_NEXT_CHECKED = "2026-11-02"  # date the curated next-drop facts below were re-checked against their release entries
SL_NEXT_COPY = {
    "countdown-kit-marvels-history-of-heroes": dict(win=("9 AM PT", "limited quantity"), anchor="Wait unless you're a Marvel collector",
        time="9 AM PT", home_time="9 AM PT", extra=" (limited quantity)", lead="Wait unless you're a Marvel collector, and price out the singles.",
        after="wait unless you're a Marvel collector"),
    "secret-lair-star-trek-set-phasers-superdrop": dict(win=("9 AM PT / 12 PM ET", "while supplies last", "pre-queue from 8 AM PT"), anchor="Buy only if you really like Star Trek; otherwise skip",
        time="9 a.m. PT / 12 PM ET", home_time="9 AM PT / 12 PM ET, pre-queue from 8 AM PT", extra=" (while supplies last; the pre-queue opens at 8 a.m. PT)", lead="Buy only if you really like Star Trek; otherwise skip.",
        after="buy only if you really like Star Trek; otherwise skip"),
}
def sl_cur(r):
    c = SL_NEXT_COPY.get(r["slug"])
    return c if c and all(a in (r.get("window") or "") for a in c["win"]) and c["anchor"] in r["note"] else None
def sl_time(r, home=False):
    c = sl_cur(r)
    if c: return " at " + c["home_time" if home else "time"]
    return " at 9 AM PT" if "9 AM PT" in (r.get("window") or "") else ""
def sl_cost(r, home=False):
    ps = r.get("prices") or []
    if not ps: return ""
    if len(ps) == 1: return fmt(ps[0]) if home else f" for {fmt(ps[0])}"
    lo, hi = min(p["usd"] for p in ps), max(p["usd"] for p in ps)
    about = any("about" in p["label"].lower() for p in ps)
    s = ("about " if about else "") + (f"${lo:,.0f}–${hi:,.0f}" if lo == int(lo) and hi == int(hi) else f"${lo:,.2f}–${hi:,.2f}") + (" per drop" if any("each drop" in p["label"].lower() for p in ps) else "")
    return s if home else f" ({s})"
def sl_checked_date(rs): return min(SL_NEXT_CHECKED if sl_cur(r) else (r.get("last_checked") or SL_NEXT_CHECKED) for r in rs)
def sl_drop_link(r): return f'<a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a>'
SL_TBA = "The next Secret Lair drop is TBA: no upcoming Secret Lair sale has a date on our calendar yet."
def sl_head_label(r):
    """Short 'Name, Mon D' for the hub title and H1. Set Phasers keeps the name buyers search."""
    key = "Set Phasers to Superdrop"
    label = key if key in r["name"] else short_name(r)
    d = datetime.date.fromisoformat(r["release_date"])
    return f"{label}, {MON[d.month-1]} {d.day}"
def sl_next_copy(linked):
    if not h_sl: return SL_TBA
    nm = lambda r: sl_drop_link(r) if linked else r["name"]
    c = sl_cur(h_sl)
    s = (f"The next dated Secret Lair sale is {nm(h_sl)}, on sale {nice_date(h_sl)}{sl_time(h_sl)}{sl_cost(h_sl)} at MagicSecretLair.com{c['extra'] if c else ''}. "
         + (f"{c['lead']} " if c else "See its page for our buy/skip verdict. "))
    if sl_after:
        ca = sl_cur(sl_after)
        s += f"After that, {nm(sl_after)} opens {nice_date(sl_after)}{sl_time(sl_after)} at MagicSecretLair.com" + (f": {ca['after']}." if ca else ".")
    else:
        s += "No later Secret Lair sale has a date yet."
    return s.strip()
if h_sl:
    _hc = sl_cost(h_sl, home=True)
    home_next_sl = (f'<p><b>Next Secret Lair drop:</b> {sl_drop_link(h_sl)} goes on sale {nice_date(h_sl)}{sl_time(h_sl, home=True)} '
                    f'({_hc + ", " if _hc else ""}MagicSecretLair.com). <a href="{BASE}/secret-lair.html">Secret Lair schedule</a>.</p>'
                    + checked({"last_checked": sl_checked_date([h_sl]), "source": h_sl["source"]}, with_sources=False))
else:
    home_next_sl = f'<p><b>Next Secret Lair drop:</b> TBA. No upcoming Secret Lair sale has a date on our calendar yet. <a href="{BASE}/secret-lair.html">Secret Lair schedule</a>.</p>'
def and_list(xs): return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
home_faq = []
if h_next: home_faq.append(("What is the next MTG set?", f'{plink(h_next, h_next["name"])} releases {nice_date(h_next)} ({E(h_next["status"])})' + (f', with prerelease events {E(h_next["prerelease"])}' if h_next.get("prerelease") else "") + "."))
if h_2027: home_faq.append(("What MTG sets release in 2027?", f"{len(h_2027)} sets are confirmed for 2027: " + and_list([f"{plink(r, r['name'])} ({nice_date(r)})" for r in h_2027]) + "."
                             + (" Commander decks are confirmed alongside " + and_list([plink(r) for r in h_cmd27]) + ", with decklists still to come." if h_cmd27 else "")
                             + f' Every 2027 date is in our <a href="{BASE}/guides/mtg-2027-release-schedule.html">MTG 2027 release schedule</a>.'))
h_sl_when = (f'{plink(h_sl, h_sl["name"])} goes on sale {nice_date(h_sl)}{sl_time(h_sl, home=True)}{sl_cost(h_sl)}' if h_sl
             else "The next Secret Lair drop is TBA: no upcoming Secret Lair sale has a date on our calendar yet")
home_faq.append(("When is the next Secret Lair drop?", h_sl_when + f'. See every drop on the <a href="{BASE}/secret-lair.html">Secret Lair schedule</a>.'))
if h_sold: home_faq.append(("Which recent MTG releases are sold out?", and_list([plink(r) + f" ({nice_date(r)})" for r in h_sold]) + " sold out at the official store. Check each page before paying resale prices."))
home_faq.append(("How often is the MTG Drops calendar updated?", "We check official Wizards of the Coast announcements and reputable MTG news every Tuesday and Friday. Each entry shows the date it was last checked and links to its sources."))
home_faq.append(("How do I add MTG release dates to Google Calendar?",
 "Use the Add to Google Calendar link on this page (https://calendar.google.com/calendar/r?cid=webcal://mtgdrops.com/calendar.ics). If it does not open a subscribe dialog, in Google Calendar choose Other calendars, then From URL, and paste https://mtgdrops.com/calendar.ics. Apple Calendar can open webcal://mtgdrops.com/calendar.ics. Outlook can subscribe from the web with the same https URL. The file itself is https://mtgdrops.com/calendar.ics. Secret Lair dates alone are a separate feed at https://mtgdrops.com/secret-lair.ics."))
home_faq_html = "<h2>MTG release FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{a}</p>" for q, a in home_faq)
# How-to sits next to the existing calendar.ics links. It does not add a new feed file.
CAL_HOWTO = (
 f'<h2 id="add-to-google-calendar">Add MTG release dates to Google Calendar</h2>'
 f'<p>Every dated release is already in <a href="{BASE}/calendar.ics">calendar.ics</a>. Subscribe once and later dates show up in the same calendar. '
 'These steps use the feed links already on this page.</p>'
 '<ol>'
 '<li><b>Google Calendar.</b> Open <a href="https://calendar.google.com/calendar/r?cid=webcal://mtgdrops.com/calendar.ics" rel=nofollow>Add to Google Calendar</a> and confirm the calendar named "MTG Drops: MTG release calendar".</li>'
 '<li><b>If that link does not open a subscribe dialog:</b> in Google Calendar on the web, choose Other calendars (+), then From URL, and paste <code>https://mtgdrops.com/calendar.ics</code>.</li>'
 f'<li><b>Apple Calendar.</b> Open <a href="webcal://mtgdrops.com/calendar.ics" rel=nofollow>Apple / Outlook (webcal)</a>, or <a href="{BASE}/calendar.ics">download the .ics</a> and open it. Subscribe, so later releases are added, instead of importing a one-time copy.</li>'
 '<li><b>Outlook.</b> Choose Calendar, Add calendar, Subscribe from web, and paste <code>https://mtgdrops.com/calendar.ics</code>. The webcal link also opens in many desktop calendar apps.</li>'
 f'<li><b>Secret Lair dates only.</b> The same three links are on the <a href="{BASE}/secret-lair.html">Secret Lair page</a> for <a href="{BASE}/secret-lair.ics">secret-lair.ics</a>. The feed on this page is every dated release.</li>'
 '</ol>'
 '<p><small>The feed asks calendar apps to refresh about once a day. Dates still come from the same sources as the rest of the site, so verify a date before you buy.</small></p>')
ICS_LINKS = {"calendar.ics": "every MTG release", "secret-lair.ics": "Secret Lair drops only"}
def ics_link(f): return (f'<a href="https://calendar.google.com/calendar/r?cid=webcal://mtgdrops.com/{f}" rel=nofollow>Add to Google Calendar</a> · '
                         f'<a href="webcal://mtgdrops.com/{f}" rel=nofollow>Apple / Outlook (webcal)</a> · <a href="{BASE}/{f}">Download .ics</a>')
home_ld = [{"@context": "https://schema.org", "@type": "WebSite", "@id": f"{SITE_URL}/#website", "name": "MTG Drops", "url": f"{SITE_URL}/", "description": ABOUT, "publisher": {"@id": f"{SITE_URL}/#org"}},
           {"@context": "https://schema.org", **ORG},
           {"@context": "https://schema.org", "@type": "CollectionPage", "@id": f"{SITE_URL}/#page", "name": "MTG Release Calendar 2026–2027", "url": f"{SITE_URL}/", "description": HOME_DESC, "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "mainEntity": {"@id": f"{SITE_URL}/#releases"}},
           {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in home_faq]},
           {"@context": "https://schema.org", "@type": "ItemList", "@id": f"{SITE_URL}/#releases", "name": "Upcoming Magic: The Gathering releases", "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate([r for r in up if not r.get("placeholder")])]}]
page("MTG Release Calendar 2026–2027 | MTG Drops", HOME_DESC,
     f"<h1>MTG Release Calendar 2026–2027</h1><p><b>What's dropping in Magic.</b> Last updated: {tdate()}</p><p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p><p>Every upcoming MTG product, with a short buy/skip note. New: <a href=\"{BASE}/guides/mtg-releases-fall-holiday-2026.html\">every MTG product releasing this fall/holiday 2026</a>, with gift picks, the <a href=\"{BASE}/guides/star-trek-mtg-release-guide.html\">MTG Star Trek release guide</a>, and the <a href=\"{BASE}/secret-lair.html\">Secret Lair drop schedule</a>.</p>{FORM}<p class=disc><small>{E(DISCLOSURE)}</small></p><p><b>Calendar feed:</b> {ics_link("calendar.ics")}</p>{CAL_HOWTO}{home_next_sl}<div class=f>{btns}</div>" + months + home_faq_html + js, "index.html", home_ld)
def title_for(r):
    sn = short_name(r); m = mon_yyyy(r).replace("Date TBA", "TBA")
    for t in (f"{sn} Release Date ({m}), Price & Preorder | MTG Drops", f"{sn} Release Date ({m}) | MTG Drops", f"{sn} Release Date, {m} | MTG Drops", f"{sn} Release Date | MTG Drops", f"{sn} ({m}) | MTG Drops", f"{sn} | MTG Drops"):
        if len(t) <= 60: return t
    return t
def franchise(r):
    # Shared universe for related-product links. An explicit releases.json "universe" wins, so a Marvel
    # product whose slug does not say "marvel" (Spider-Mania) still joins the group; otherwise a slug
    # containing "marvel" is the Marvel universe.
    u = (r.get("universe") or "").strip().lower()
    if u: return u
    return "marvel" if "marvel" in r["slug"] else None
def related(r):
    if r.get("placeholder"): pool = public
    else: pool = [x for x in public if x is not r]
    pool = [x for x in pool if x is not r]
    sib = [x for x in pool if dated(x) and x["release_date"] == r["release_date"] and {x["type"], r["type"]} & {"Commander Precon"} and ({x["type"], r["type"]} - {"Commander Precon"}) <= set(SETS) and x["type"] != r["type"]]
    pool = [x for x in pool if x not in sib]
    fran = franchise(r)
    univ = [x for x in pool if fran and franchise(x) == fran]
    pool = [x for x in pool if x not in univ]
    key = lambda x: (0, abs((datetime.date.fromisoformat(x["release_date"]) - datetime.date.fromisoformat(r["release_date"])).days)) if dated(x) and dated(r) else ((1, 0) if not dated(x) else (2, 0))
    # Same-date set/commander pair first, then every other release in the same universe (a TBA drop such as
    # Doomsdrop stays linked even though undated products sort last), then the nearest other releases.
    picked = sib + sorted(univ, key=key) + sorted(pool, key=key)
    return picked[:max(4, len(sib) + len(univ))]
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
# ---- Set Phasers deepen (Nov 7, 2026). One product only. ----
# Settled verdict stays "Buy only if you really like Star Trek; otherwise skip."
# Per-drop "buy this first" lines are Draft — pending owner OK, and labeled Proposed.
# Five foil drops are 5 x $39.99 = $199.95, which is $0.04 under Wizards' $199.99 threshold.
PHASERS_SLUG = "secret-lair-star-trek-set-phasers-superdrop"
PHASERS_SETTLED = "Buy only if you really like Star Trek; otherwise skip."
PHASERS_SET_VERDICT = "Buy for drafting/Trek fans; skip sealed speculation."
PHASERS_CMD_VERDICT = "buy regular, skip CE at markup"
PHASERS_WIZ = "https://magic.wizards.com/en/news/announcements/secret-lair-set-phasers-to-superdrop"
PHASERS_SCRYFALL = "https://scryfall.com/"
PHASERS_ACCOUNT = "https://myaccounts.wizards.com/registration"
PHASERS_CHECKED = "2026-11-07"
PHASERS_PICK_ONE = "Lower Decks if you want the Thrasios and Silas Renn partners; otherwise Beam Me Up for blink and enter-the-battlefield staples."
PHASERS_PICK_TWO = ("Lower Decks and Beam Me Up for playables. Add tlhIngan maH only if you want the red ritual package. "
                    "KHAAAAAAAAN is theme plus mid staples. New Worlds is only for the land art. The sixth drop is unrevealed, so there is no pick.")
PHASERS_BEAM = [("Eerie Interlude", 768), ("Momentary Blink", 19), ("Essence Flux", 62), ("Conjurer's Closet", 340)]
PHASERS_KHAN = [("Wrath of the Skies", 284), ("Commandeer", 427), ("Illusionist's Gambit", 37), ("Buried Alive", 332), ("Genesis Wave", 39), ("Fracture", 28)]
PHASERS_LD = [("Inti, Seneschal of the Sun", 106), ("Kambal, Profiteering Mayor", 597),
              ("Silas Renn foil (Commander 2016; Scryfall listed no non-foil price)", 1139),
              ("Thrasios foil (Commander 2016)", 2714), ("Weatherlight", 141)]
PHASERS_KLINGON = [("Demand Answers", 83), ("Relentless Assault", 354), ("Seething Song", 1109), ("War's Toll", 1068), ("Warstorm Surge", 147)]
def money_c(c):
    c = int(c)
    return f"${c // 100:,}.{c % 100:02d}"
def phasers_link(href, text, nofollow=False):
    rel = " rel=nofollow" if nofollow else ""
    return f'<a href="{E(href)}"{rel}>{E(text)}</a>'
def faq_visible(a):
    """Plain FAQ answers are escaped. An answer that already contains a tag is HTML from this file."""
    return a if "<" in a else E(a)
def _usd_cents(rel, label):
    hits = [p["usd"] for p in rel.get("prices") or [] if p["label"] == label]
    if len(hits) != 1: raise SystemExit(f"price missing: {rel['slug']} {label}")
    return int(round(hits[0] * 100))
def phasers_facts():
    r = next(x for x in data if x["slug"] == PHASERS_SLUG)
    st = next(x for x in data if x["slug"] == "star-trek")
    cmd = next(x for x in data if x["slug"] == "star-trek-commander")
    if r.get("last_checked") != PHASERS_CHECKED: raise SystemExit("Set Phasers last_checked must be " + PHASERS_CHECKED)
    if PHASERS_SETTLED not in r["note"]: raise SystemExit("Set Phasers settled verdict missing")
    if PHASERS_SET_VERDICT not in st["note"]: raise SystemExit("Star Trek set verdict missing")
    if PHASERS_CMD_VERDICT not in cmd["note"]: raise SystemExit("Star Trek Commander verdict missing")
    if "Transporter Boondoggle" not in (r.get("window") or "") or "199.99" not in (r.get("window") or ""):
        raise SystemExit("Set Phasers window is missing the bonus threshold")
    if "ship" in (r.get("window") or "").lower(): raise SystemExit("Set Phasers window now mentions shipping; update the not-announced line")
    if len(r.get("inside") or []) != 5: raise SystemExit("Set Phasers should list five revealed drops, not a guessed sixth")
    if not any("sixth" in c.lower() for c in r.get("contents") or []): raise SystemExit("Set Phasers contents should say the sixth drop is unrevealed")
    nonfoil, foil = _usd_cents(r, "Each drop, non-foil"), _usd_cents(r, "Each drop, foil")
    five, six = 5 * foil, 6 * nonfoil
    mix33, mix42 = 3 * foil + 3 * nonfoil, 4 * foil + 2 * nonfoil
    threshold = 19999
    if (nonfoil, foil, five, six, threshold - five, threshold - six, mix33, mix42) != (2999, 3999, 19995, 17994, 4, 2005, 20994, 21994):
        raise SystemExit(f"Set Phasers bonus math drifted: nonfoil={nonfoil} foil={foil} five={five} six={six} mix33={mix33} mix42={mix42}")
    beam, khan, ld, klingon = (sum(c for _, c in rows) for rows in (PHASERS_BEAM, PHASERS_KHAN, PHASERS_LD, PHASERS_KLINGON))
    partners = PHASERS_LD[2][1] + PHASERS_LD[3][1]
    if (beam, khan, ld, klingon, partners) != (1189, 1147, 4697, 2761, 3853):
        raise SystemExit(f"Set Phasers Scryfall totals drifted: {beam} {khan} {ld} {klingon} {partners}")
    inside = json.dumps(r["inside"])
    for needle in ("Eerie Interlude", "Momentary Blink", "Essence Flux", "Conjurer's Closet", "Wrath of the Skies", "Commandeer",
                   "Illusionist's Gambit", "Buried Alive", "Genesis Wave", "Fracture", "Inti, Seneschal of the Sun",
                   "Kambal, Profiteering Mayor", "Silas Renn", "Thrasios", "Weatherlight", "Demand Answers", "Relentless Assault",
                   "Seething Song", "War's Toll", "Warstorm Surge", "Alayna Danner", "U.S.S. Cerritos"):
        if needle not in inside: raise SystemExit("Set Phasers inside list is missing " + needle)
    st_inside, cmd_inside = json.dumps(st["inside"]), json.dumps(cmd["inside"])
    for needle, blob in (("14 cards", st_inside), ("actor-signed headliner", st_inside), ("9 Play Boosters", st_inside),
                         ("Ready-to-play 100-card deck", cmd_inside), ("Same 100-card list in surge foil", cmd_inside)):
        if needle not in blob: raise SystemExit("Star Trek product text missing: " + needle)
    bg = dict(st.get("buy_guide") or [])
    if "easiest gift for a Trek fan" not in bg.get("Bundles / Beam Me Up Bundles", ""): raise SystemExit("Star Trek bundle line missing")
    if "not as a sealed investment" not in bg.get("Collector Boosters", ""): raise SystemExit("Star Trek collector line missing")
    if "Secret Lair debut" not in r["note"]: raise SystemExit("Set Phasers note lost the partner debut line")
    return dict(r=r, st=st, cmd=cmd, nonfoil=money_c(nonfoil), foil=money_c(foil), five_foil=money_c(five), six_nonfoil=money_c(six),
                five_short=money_c(threshold - five), six_short=money_c(threshold - six), mix33=money_c(mix33), mix42=money_c(mix42),
                threshold=money_c(threshold), play=money_c(_usd_cents(st, "Play Booster")), collector=money_c(_usd_cents(st, "Collector Booster")),
                bundle=money_c(_usd_cents(st, "Bundle")), cmd_price=money_c(_usd_cents(cmd, "Commander Deck (each)")),
                ce=money_c(_usd_cents(cmd, "Collector's Edition (each)")), beam=money_c(beam), khan=money_c(khan), ld=money_c(ld),
                klingon=money_c(klingon), partners=money_c(partners), promo=money_c(258),
                self_path=f"{BASE}/p/{PHASERS_SLUG}.html", st_path=f"{BASE}/p/star-trek.html", cmd_path=f"{BASE}/p/star-trek-commander.html",
                guide_path=f"{BASE}/guides/star-trek-mtg-release-guide.html")
def phasers_time_answer(href):
    return ("Set Phasers to Superdrop goes on sale Nov 9, 2026 at 9 a.m. PT (11 a.m. CT / 12 p.m. ET) at "
            + phasers_link(SL_STORE, "MagicSecretLair.com")
            + ". The pre-queue opens at 8 a.m. PT. Add any product and proceed to checkout before 9 a.m. PT; shoppers already in the pre-queue get a random spot when the sale opens. "
            "A cart does not reserve the drop. The order is secured only when checkout is completed. Have a Wizards account ready, with shipping and payment saved. Steps: "
            + phasers_link(href, "sale-day checklist") + ". Last checked Nov 7, 2026.")
def phasers_which_answer(href):
    return ("Draft — pending owner OK. The settled verdict is unchanged: Buy only if you really like Star Trek; otherwise skip. "
            f"<span class=st>Proposed</span> — one drop: {E(PHASERS_PICK_ONE)} "
            f"<span class=st>Proposed</span> — two drops: {E(PHASERS_PICK_TWO)} "
            "Details: " + phasers_link(href, "If you only buy one or two drops") + ".")
def phasers_bonus_answer(f):
    return (f"Wizards adds one foil Return of the Wildspeaker, printed as \"Transporter Boondoggle,\" for every {f['threshold']} spent on this Superdrop, while supplies last "
            f"({phasers_link(PHASERS_WIZ, 'Wizards')}). Five foil drops are 5 × {f['foil']} = {f['five_foil']}, which is {f['five_short']} under {f['threshold']}, so that cart is short of the published threshold. "
            f"Six non-foil drops are 6 × {f['nonfoil']} = {f['six_nonfoil']}, which is {f['six_short']} short, so non-foil drops alone need foils or extra drops. "
            f"Three foil and three non-foil is {f['mix33']}. Four foil and two non-foil is {f['mix42']}. Those two carts are over {f['threshold']}. "
            f"The promo is a foil Secret Lair treatment. A non-foil Return of the Wildspeaker was about {f['promo']} on {phasers_link(PHASERS_SCRYFALL, 'Scryfall', nofollow=True)} on Nov 7, 2026; do not treat that as the promo's price. "
            "Last checked Nov 7, 2026.")
def phasers_collector_answer(f):
    return ("They answer different wants, and this page does not call the Superdrop the better buy. Buy the Superdrop only if you really like Star Trek; otherwise skip. "
            f"A Star Trek Collector Booster is {f['collector']} MSRP and is for foil Booster Fun cards and the actor-signed headliners, not a sealed investment. "
            f"The set verdict stays: {PHASERS_SET_VERDICT} "
            f"A Star Trek Bundle ({f['bundle']} MSRP) or a regular Commander deck ({f['cmd_price']} MSRP) usually gives more playable Magic for the money. "
            f"Skip Collector's Edition Commander decks marked up above the {f['ce']} MSRP. See "
            + phasers_link("#superdrop-vs-star-trek", "Superdrop vs Star Trek Play / Collector / Commander") + ".")
def phasers_ship_answer():
    return ("Not announced. The " + phasers_link(PHASERS_WIZ, "Wizards")
            + " announcement does not give a shipping window for Set Phasers to Superdrop. Orders over $99 ship free under Wizards' terms (see "
            + phasers_link(SL_STORE, "MagicSecretLair.com")
            + " for details). That is a shipping-cost rule, not a delivery date. Last checked Nov 7, 2026.")
def phasers_singles_answer(f):
    return (f"Often, if you only want the playable cards in a staple-heavy drop. These are about-prices from the cheapest listed printings on {phasers_link(PHASERS_SCRYFALL, 'Scryfall', nofollow=True)} on Nov 7, 2026, not our sale prices. "
            f"Beam Me Up playables are about {f['beam']} versus {f['nonfoil']} sealed, so singles usually win for playables and sealed is for the art and theme. "
            f"KHAAAAAAAAN playables are about {f['khan']} versus {f['nonfoil']} sealed, so singles win for playables. "
            f"Lower Decks is about {f['ld']} with the foil Thrasios and Silas Renn partners included, versus {f['nonfoil']} sealed, so the sealed non-foil drop can cost less than buying both partners. "
            f"tlhIngan maH is about {f['klingon']} versus {f['nonfoil']} sealed, roughly even, and sealed is the Klingon reversible art. "
            "New Worlds is themed basic lands by Alayna Danner, with no meaningful non-themed singles comparison, so sealed is for the art. Card-by-card figures: "
            + phasers_link("#sealed-vs-singles", "Sealed drop vs singles build") + ". Last checked Nov 7, 2026.")
def phasers_extra_faqs(f):
    return [
        ("What time does the Star Trek Secret Lair go on sale?", phasers_time_answer("#sale-day-checklist")),
        ("Which Set Phasers drops are worth buying?", phasers_which_answer("#one-or-two-drops")),
        ("What is the Transporter Boondoggle bonus card?", phasers_bonus_answer(f)),
        ("Is the Star Trek Secret Lair better than Star Trek Collector Boosters?", phasers_collector_answer(f)),
        ("When will Set Phasers to Superdrop ship?", phasers_ship_answer()),
        ("Is it cheaper to buy Set Phasers singles instead of the sealed drops?", phasers_singles_answer(f)),
    ]
def phasers_hub_faqs():
    page = f"{BASE}/p/{PHASERS_SLUG}.html"
    return [
        ("What time does the Star Trek Secret Lair go on sale?", phasers_time_answer(page + "#sale-day-checklist")),
        ("Which Set Phasers drops are worth buying?", phasers_which_answer(page + "#one-or-two-drops")),
    ]
def _singles_bits(rows):
    return "; ".join(f"{E(name)} {money_c(cents)}" for name, cents in rows)
def _itemlist(name, names, urls):
    els = []
    for i, (n, u) in enumerate(zip(names, urls)):
        el = {"@type": "ListItem", "position": i + 1, "name": n}
        if u: el["url"] = u
        els.append(el)
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name, "numberOfItems": len(els), "itemListElement": els}
def set_phasers_deepen():
    f = phasers_facts()
    st_abs, cmd_abs = SITE_URL + f["st_path"], SITE_URL + f["cmd_path"]
    self_abs = SITE_URL + f["self_path"]
    answer = (
        "<p><b>When is the Star Trek Secret Lair and is it worth it?</b> Secret Lair x Star Trek: Set Phasers to Superdrop goes on sale Nov 9, 2026 at 9 a.m. PT (11 a.m. CT / 12 p.m. ET) at "
        + phasers_link(SL_STORE, "MagicSecretLair.com")
        + f", with a pre-queue from 8 a.m. PT. It's six themed drops at {f['nonfoil']} non-foil / {f['foil']} foil each ("
        + phasers_link(PHASERS_WIZ, "Wizards")
        + f"), and spending {f['threshold']}+ adds the Transporter Boondoggle bonus while supplies last. Buy it if you really like Star Trek. Otherwise skip — a "
        + phasers_link(f["st_path"], "Star Trek Bundle")
        + " or " + phasers_link(f["cmd_path"], "regular Commander deck")
        + " usually gives more playable Magic for the money. <i>Last checked: Nov 7, 2026.</i></p>")
    suits = (
        "<h2 id=one-or-two-drops>If you only buy one or two drops</h2>"
        "<p>Who each revealed drop suits. These notes are not a ranking. The sixth drop is not revealed, so this page does not guess its cards.</p><ul>"
        "<li><b>Beam Me Up.</b> Four reversible blink and enter-the-battlefield cards: Eerie Interlude, Momentary Blink, Essence Flux, and Conjurer's Closet. Suits a blink or enter-the-battlefield deck that wants the Trek treatment.</li>"
        "<li><b>KHAAAAAAAAN.</b> Wrath of Khan theme, including Buried Alive, Genesis Wave, Commandeer, and Wrath of the Skies. Suits theme collectors and decks that want those reprints.</li>"
        "<li><b>Lower Decks.</b> Secret Lair debut of Thrasios, Triton Hero and Silas Renn, Seeker Adept, plus Inti, Kambal, and Weatherlight as \"U.S.S. Cerritos, California-Class.\" Suits partner-commander players and Lower Decks fans.</li>"
        "<li><b>tlhIngan maH.</b> Five reversible English/Klingon red cards, including Seething Song. Suits players who want that red package or the Klingon art.</li>"
        "<li><b>New Worlds.</b> Ten basic lands by Alayna Danner, two of each basic. Suits buyers who want the land art.</li>"
        "<li><b>Sixth drop.</b> Not revealed. No card list on this page, and no pick.</li></ul>"
        "<div class=card><p><b>Draft — pending owner OK.</b> The lines in this box are Proposed \"buy this first\" picks. They are not the page verdict. The verdict stays: "
        + E(PHASERS_SETTLED) + "</p><ul>"
        f"<li><span class=st>Proposed</span> <b>One drop:</b> {E(PHASERS_PICK_ONE)}</li>"
        f"<li><span class=st>Proposed</span> <b>Two drops:</b> {E(PHASERS_PICK_TWO)}</li></ul></div>")
    bonus = (
        "<h2 id=transporter-boondoggle>Transporter Boondoggle ($199.99 threshold)</h2>"
        + checked({"last_checked": PHASERS_CHECKED, "source": PHASERS_WIZ}, with_sources=True)
        + f"<p>For every {f['threshold']} spent, {phasers_link(PHASERS_WIZ, 'Wizards')} adds one foil Return of the Wildspeaker as \"Transporter Boondoggle,\" while supplies last. List prices on Nov 7, 2026:</p><ul>"
        f"<li>Five foil drops: 5 × {f['foil']} = {f['five_foil']}. That is {f['five_short']} under {f['threshold']}, so five foil drops are short of the published threshold.</li>"
        f"<li>Six non-foil drops: 6 × {f['nonfoil']} = {f['six_nonfoil']}. That is {f['six_short']} short, so non-foil drops alone need foils or extra drops.</li>"
        f"<li>Three foil and three non-foil: {f['mix33']}, over {f['threshold']}.</li>"
        f"<li>Four foil and two non-foil: {f['mix42']}, over {f['threshold']}.</li></ul>"
        f"<p>The promo is a foil Secret Lair treatment. {phasers_link(PHASERS_SCRYFALL, 'Scryfall', nofollow=True)} listed a non-foil Return of the Wildspeaker at about {f['promo']} on Nov 7, 2026. Do not equate that printing with this foil promo. No other bonus is announced.</p>")
    cmp_rows = [
        ("Secret Lair x Star Trek: Set Phasers to Superdrop", f["self_path"], self_abs,
         "Six themed drops. Five are revealed: Beam Me Up, KHAAAAAAAAN, Lower Decks, tlhIngan maH, and New Worlds. The sixth drop is not revealed.",
         f"{f['nonfoil']} non-foil / {f['foil']} foil per drop (Wizards sale price)", PHASERS_SETTLED),
        ("Star Trek Play Booster", f["st_path"], st_abs, "14-card Play Booster for drafting.", f"{f['play']} MSRP", PHASERS_SET_VERDICT),
        ("Star Trek Collector Booster", f["st_path"], st_abs, "Collector Booster. Only place to find the 7 actor-signed headliner cards.", f"{f['collector']} MSRP",
         "Only worth it if you're chasing foil Booster Fun cards or the actor-signed headliners, not as a sealed investment."),
        ("Star Trek Bundle", f["st_path"], st_abs, "9 Play Boosters, lands, and accessories.", f"{f['bundle']} MSRP",
         "Easiest gift for a Trek fan. " + PHASERS_SET_VERDICT),
        ("Star Trek Commander deck (regular)", f["cmd_path"], cmd_abs, "Ready-to-play 100-card deck.", f"{f['cmd_price']} MSRP", "Buy regular, skip CE at markup."),
        ("Star Trek Collector's Edition Commander deck", f["cmd_path"], cmd_abs, "Same 100-card list in surge foil.", f"{f['ce']} MSRP", "Skip CE at markup."),
    ]
    cmp_html = "".join("<tr><td>" + phasers_link(path, name) + f"</td><td>{E(what)}</td><td>{E(price)}</td><td>{E(who)}</td></tr>" for name, path, _abs, what, price, who in cmp_rows)
    vs = (
        "<h2 id=superdrop-vs-star-trek>Superdrop vs Star Trek Play / Collector / Commander</h2>"
        f"<p>What you get, the price, and who it is for. Star Trek prices are MSRP from {phasers_link(f['st_path'], f['st']['name'])} and {phasers_link(f['cmd_path'], 'Star Trek Commander Decks')}. "
        f"Superdrop prices are the Wizards sale price. The verdicts below are the ones already on those pages, not new set-level calls. Full notes: {phasers_link(f['guide_path'], 'MTG Star Trek release guide')}. "
        "A Star Trek Bundle or regular Commander deck usually gives more playable Magic for the money.</p>"
        "<table><tr><th>Product</th><th>What you get</th><th>Price</th><th>Who it's for</th></tr>" + cmp_html + "</table>")
    singles_rows = [
        ("Beam Me Up", f"about {f['beam']} — " + _singles_bits(PHASERS_BEAM), "Singles usually win for playables. Sealed is for the art and theme."),
        ("KHAAAAAAAAN", f"about {f['khan']} — " + _singles_bits(PHASERS_KHAN), "Singles win for playables."),
        ("Lower Decks", f"about {f['ld']} — " + _singles_bits(PHASERS_LD), f"Sealed non-foil can cost less than buying both foil partners (about {f['partners']} together)."),
        ("tlhIngan maH", f"about {f['klingon']} — " + _singles_bits(PHASERS_KLINGON), "Roughly even with the non-foil drop. Sealed is for the Klingon reversible art."),
        ("New Worlds", "No meaningful non-themed singles price. Themed basics by Alayna Danner.", "Sealed is for the art."),
    ]
    singles_html = "".join(f"<tr><td>{E(drop)}</td><td>{f['nonfoil']}</td><td>{bits}</td><td>{E(read)}</td></tr>" for drop, bits, read in singles_rows)
    singles = (
        "<h2 id=sealed-vs-singles>Sealed drop vs singles build (dated Nov 7)</h2>"
        + checked({"last_checked": PHASERS_CHECKED, "source": PHASERS_SCRYFALL}, with_sources=True)
        + "<p>Cheapest listed printings on Scryfall, Nov 7, 2026, in USD. These are market snapshots, not our sale prices, and not a resale database. The sealed column is the Wizards non-foil drop price.</p>"
        "<table><tr><th>Drop</th><th>Sealed non-foil</th><th>Playable singles (Scryfall, Nov 7)</th><th>Read</th></tr>" + singles_html + "</table>"
        f"<p>The Read column uses the {f['nonfoil']} non-foil price. A foil drop is {f['foil']}. At {f['foil']}, Beam Me Up and KHAAAAAAAAN singles still cost less, tlhIngan maH singles (about {f['klingon']}) cost less, "
        f"and Lower Decks is above the two foil partners (about {f['partners']}) and below the five-card total (about {f['ld']}). "
        f"The Transporter Boondoggle promo is a foil Secret Lair Return of the Wildspeaker. Scryfall's non-foil printing was about {f['promo']} on Nov 7, 2026. Do not equate that with the promo.</p>")
    sale = (
        "<h2 id=sale-day-checklist>Sale-day checklist</h2>"
        + checked({"last_checked": PHASERS_CHECKED, "source": PHASERS_WIZ}, with_sources=True)
        + "<ol>"
        f"<li><b>Sale:</b> Nov 9, 2026, 9 a.m. PT / 11 a.m. CT / 12 p.m. ET, only at {phasers_link(SL_STORE, 'MagicSecretLair.com')}.</li>"
        "<li><b>Pre-queue:</b> 8 a.m. PT (10 a.m. CT / 11 a.m. ET), one hour before the sale. Add any product and proceed to checkout before 9 a.m. PT. Shoppers already in the pre-queue get a random spot when the sale opens. After 9 a.m. PT, you join in the order you reach checkout.</li>"
        f"<li><b>Account ready:</b> create a Wizards account and save shipping and payment at {phasers_link(PHASERS_ACCOUNT, 'myaccounts.wizards.com/registration')}. Double-check the shipping address. Wizards lists both on the sale checklist.</li>"
        "<li><b>Cart does not reserve.</b> Adding products to your cart does not reserve them. The order is secured only when checkout is completed.</li>"
        f"<li><b>Shipping window:</b> not announced. The {phasers_link(PHASERS_WIZ, 'Wizards')} announcement does not say when these orders ship.</li>"
        f"<li><b>Shipping cost:</b> orders over $99 ship free under Wizards' terms (see {phasers_link(SL_STORE, 'MagicSecretLair.com')} for details). That is not a delivery date.</li>"
        "<li><b>While supplies last,</b> including the Transporter Boondoggle promo.</li>"
        "</ol>")
    html_out = answer + suits + bonus + vs + singles + sale
    anchor = self_abs
    lists = [
        _itemlist("Superdrop vs Star Trek Play / Collector / Commander", [row[0] for row in cmp_rows], [row[2] for row in cmp_rows]),
        _itemlist("Sealed drop vs singles build, Nov 7, 2026",
                  [f"{drop} — {read}" for drop, _bits, read in singles_rows], [anchor + "#sealed-vs-singles"] * len(singles_rows)),
        _itemlist("Set Phasers one-or-two-drop picks (Draft — pending owner OK)",
                  ["Proposed — one drop: " + PHASERS_PICK_ONE, "Proposed — two drops: " + PHASERS_PICK_TWO],
                  [anchor + "#one-or-two-drops", anchor + "#one-or-two-drops"]),
    ]
    return html_out, phasers_extra_faqs(f), lists
def _page_ld(html_text):
    return [json.loads(raw) for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_text)]
def _walk_types(o, acc):
    if isinstance(o, dict):
        t = o.get("@type")
        if isinstance(t, str): acc.add(t)
        elif isinstance(t, list): acc.update(x for x in t if isinstance(x, str))
        for v in o.values(): _walk_types(v, acc)
    elif isinstance(o, list):
        for v in o: _walk_types(v, acc)
    return acc
def _visible_faqs(html_text, h2):
    i = html_text.find(h2)
    if i < 0: raise SystemExit("missing heading " + h2)
    rest = html_text[i + len(h2):]
    j = rest.find("<h2")
    block = rest if j < 0 else rest[:j]
    pairs = re.findall(r"<h3>(.*?)</h3><p>(.*?)</p>", block, flags=re.S)
    if not pairs: raise SystemExit("no faqs under " + h2)
    return [(html.unescape(q), a) for q, a in pairs]
def _assert_faq_match(html_text, h2):
    vis = _visible_faqs(html_text, h2)
    pages = [o for o in _page_ld(html_text) if o.get("@type") == "FAQPage"]
    if len(pages) != 1: raise SystemExit(f"{h2}: expected 1 FAQPage, found {len(pages)}")
    ld = [(q["name"], q["acceptedAnswer"]["text"]) for q in pages[0]["mainEntity"]]
    got = [(q, plain(a)) for q, a in vis]
    if got != ld:
        for i, (a, b) in enumerate(zip(got, ld)):
            if a != b: raise SystemExit(f"FAQ mismatch at {i}: visible {a!r} vs ld {b!r}")
        raise SystemExit(f"FAQ count visible {len(got)} vs ld {len(ld)}")
    return got
def _assert_no_banned(html_text):
    acc = set()
    for o in _page_ld(html_text): _walk_types(o, acc)
    bad = acc & {"Review", "AggregateRating", "Rating", "Event"}
    if bad: raise SystemExit("banned JSON-LD: " + ", ".join(sorted(bad)))
    return acc
def _assert_phasers_page(path):
    html_text = open(path).read()
    types = _assert_no_banned(html_text)
    for need in ("FAQPage", "ItemList", "Product", "WebPage", "BreadcrumbList"):
        if need not in types: raise SystemExit("Set Phasers JSON-LD missing " + need)
    got = _assert_faq_match(html_text, "<h2>FAQ</h2>")
    questions = [q for q, _ in got]
    for q in ("What time does the Star Trek Secret Lair go on sale?", "Which Set Phasers drops are worth buying?",
              "What is the Transporter Boondoggle bonus card?", "Is the Star Trek Secret Lair better than Star Trek Collector Boosters?",
              "When will Set Phasers to Superdrop ship?", "Is it cheaper to buy Set Phasers singles instead of the sealed drops?",
              "Should I buy Star Trek Superdrop?"):
        if q not in questions: raise SystemExit("missing FAQ: " + q)
    which = dict(got)["Which Set Phasers drops are worth buying?"]
    if "Draft — pending owner OK" not in which or "Proposed" not in which: raise SystemExit("which-drops FAQ must say Draft and Proposed")
    buy_at = html_text.find("<h2>Buy or skip?</h2>")
    tcg_at = html_text.find("Check prices on TCGplayer")
    h2s = ["<h2 id=one-or-two-drops>If you only buy one or two drops</h2>",
           "<h2 id=transporter-boondoggle>Transporter Boondoggle ($199.99 threshold)</h2>",
           "<h2 id=superdrop-vs-star-trek>Superdrop vs Star Trek Play / Collector / Commander</h2>",
           "<h2 id=sealed-vs-singles>Sealed drop vs singles build (dated Nov 7)</h2>",
           "<h2 id=sale-day-checklist>Sale-day checklist</h2>"]
    pos = html_text.find("<h2>What's inside</h2>")
    if pos < 0 or pos > buy_at: raise SystemExit("What's inside must stay before Buy or skip")
    pos = buy_at
    for h in h2s:
        p = html_text.find(h)
        if p < pos or p > tcg_at: raise SystemExit("section out of order: " + h)
        pos = p
    if "Fan-collectible and theme play, not a speculative pickup." not in html_text: raise SystemExit("base verdict paragraph missing")
    if "$0.04 under $199.99" not in html_text: raise SystemExit("five-foil shortfall missing")
    if "hits threshold" in html_text: raise SystemExit("do not claim five foil drops hit $199.99")
    if "not announced" not in html_text.lower(): raise SystemExit("shipping window must stay not announced")
    title = html.unescape(re.search(r"<title>(.*?)</title>", html_text).group(1))
    if len(title) > 60: raise SystemExit(f"title too long ({len(title)}): {title}")
    if "context7-site-verification" not in html_text: raise SystemExit("Context7 meta missing")
    names = [o.get("name") for o in _page_ld(html_text) if o.get("@type") == "ItemList"]
    for name in ("Superdrop vs Star Trek Play / Collector / Commander", "Sealed drop vs singles build, Nov 7, 2026",
                 "Set Phasers one-or-two-drop picks (Draft — pending owner OK)"):
        if name not in names: raise SystemExit("missing ItemList: " + name)
    if "buttondown.com" not in html_text or "As an Amazon Associate" not in html_text: raise SystemExit("disclosure or newsletter CTA missing")
def _assert_phasers_hub(path):
    html_text = open(path).read()
    _assert_no_banned(html_text)
    got = dict(_assert_faq_match(html_text, "<h2>Secret Lair FAQ</h2>"))
    for q in ("What time does the Star Trek Secret Lair go on sale?", "Which Set Phasers drops are worth buying?"):
        if q not in got: raise SystemExit("hub missing FAQ: " + q)
    if "Draft — pending owner OK" not in got["Which Set Phasers drops are worth buying?"] or "Proposed" not in got["Which Set Phasers drops are worth buying?"]:
        raise SystemExit("hub which-drops FAQ must say Draft and Proposed")
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
    if r.get("prerelease_verdict"): faq.append((f"Should I buy a {sn} prerelease kit?", r["prerelease_verdict"]))
    deepen_html = ""
    phasers_ld = []
    if r["slug"] == PHASERS_SLUG:
        deepen_html, extra_faqs, itemlists = set_phasers_deepen()
        shown = [(q, E(a)) for q, a in faq] + extra_faqs
        faqhtml = "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{a}</p>" for q, a in shown)
        phasers_ld = [{"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in shown]}] + itemlists
    else:
        faqhtml = "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in faq)
    pre_html = f'<h3>Prerelease kits</h3><p><span class=t>Buy / Wait / Skip</span> {E(r["prerelease_verdict"])}</p>' if r.get("prerelease_verdict") else ""
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
    # Same reverse-link rule as the 2027 schedule: one paragraph on the product page, guide title as the anchor.
    if r["release_date"][:4] == "2027":
        y27 = f'<p>Every 2027 set and Commander deck: <a href="{BASE}/guides/mtg-2027-release-schedule.html">MTG 2027 release schedule</a>.</p>'
    elif dated(r) and "2026-10-01" <= r["release_date"] <= "2026-12-31":
        y27 = f'<p>Every MTG product releasing fall/holiday 2026: <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>.</p>'
    else:
        y27 = ""
    crumbs = f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › {(f'<a href="{BASE}/secret-lair.html">Secret Lair</a>' if r["type"] == "Secret Lair" else E(r["type"]))} › {E(sn)}</nav>{hubl}'
    desc = r.get("meta_desc") or f"{sn} release date: {nice_date(r)}. " + r["note"]
    page(title_for(r), desc,
         f'{crumbs}<span class=t>{E(r["type"])}</span><h1>{E(r["name"])}</h1><p><b>Release:</b> {nice_date(r)} ({E(r["status"])}){f" · <b>Prerelease:</b> {E(r['prerelease'])}" if r.get("prerelease") else ""}{" · <b>Sold out</b> at the official store" if r.get("sold_out") else ""}{" · <b>Delayed</b>: stock may arrive after this date" if r.get("delayed") else ""}</p>{win}<h2>Price</h2>{ptab}{contents}{facts}<h2>Buy or skip?</h2><p>{E(r["note"])}{(" " + E(r["buy_guide_intro"])) if r.get("buy_guide_intro") else ""}</p>{("<ul>" + "".join(f"<li><b>{E(k)}:</b> {E(v)}</li>" for k, v in r["buy_guide"]) + "</ul>") if r.get("buy_guide") else ""}{pre_html}{f"<p><i>{E(r['preorder_call'])}</i></p>" if r.get("preorder_call") else ""}{("<p>Other Commander decks coming in 2027: " + ", ".join(plink(x, x["name"]) + f" ({nice_date(x)})" for x in h_cmd27 if x is not r) + ".</p>") if r.get("preorder_call") and r in h_cmd27 else ""}{deepen_html}<p><a href="{tcg(r.get("tcg_query") or r["name"])}" rel="sponsored nofollow">Check prices on TCGplayer</a></p>{amz_btn(r)}<p class=disc><small>{E(DISCLOSURE)}</small></p>{tinfo}{howto}{relhtml}{y27}{faqhtml}<p><small>Source: <a href="{E(r["source"])}">{E(r["source"])}</a></small></p>{fsrc}{checked(r, with_sources=False)}<p><small>Last updated: {tdate()}</small></p>{FORM}',
         f"p/{r['slug']}.html", main_ld + phasers_ld + [bc], noindex=bool(r.get("placeholder")), og=(card[1], 1200, 630) if card else None)
    if r["slug"] == PHASERS_SLUG: _assert_phasers_page(os.path.join("dist", f"p/{r['slug']}.html"))
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
def names(rs): return "; ".join(f"{short_name(r)} (" + ("delayed, was due " if r.get("delayed") else "") + f"{nice_date(r) if dated(r) else 'date TBA'})" for r in rs)
sl_shown = [r for r in (h_sl, sl_after) if r]
sl_next_others = [r for r in sl_up if r not in sl_shown]
_sl_fs = {short_name(sl_after).lower(): sl_after["source"]} if sl_after else {}
sl_next_block = (f'<h2>Next Secret Lair drop</h2><div class=card><p>{sl_next_copy(True)}</p>'
                 + (checked({"last_checked": sl_checked_date(sl_shown), "source": h_sl["source"], "field_sources": _sl_fs}) if h_sl else "")
                 + "</div>")
sl_faq = [
 ("What is the next Secret Lair drop?",
  sl_next_copy(False)
  + (f" Also announced: {names(sl_next_others)}." if sl_next_others else "")),
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
sl_faq += phasers_hub_faqs()
sl_intro = (f'<h2>What is Secret Lair and how do drops work?</h2>'
 f'<p>Secret Lair is Wizards of the Coast\'s direct-to-fan line of collectible Magic: The Gathering cards, sold at MagicSecretLair.com. '
 f'A drop is an exclusive, limited-time selection of usually 4 to 8 cards with new art or treatments, often a crossover with an artist or franchise, and most drops come in both foil and non-foil editions (<a href="{SL_SRC["about"]}">Secret Lair: About</a>). '
 f'Sales open at 9 a.m. PT, with a pre-queue from 8 a.m. PT (<a href="{SL_SRC["queue"]}">Wizards</a>). '
 f'Since 2024, most drops are limited print runs printed before the sale rather than print-to-demand, so popular drops can sell out before the sale ends; a few remain print-to-demand (<a href="{SL_SRC["lpr"]}">Wizards</a>, <a href="{SL_SRC["faq"]}">Secret Lair FAQ</a>). '
 f'Standard 2026 drops cost $29.99 non-foil or $39.99 traditional foil; Superdrops bundle several drops, and larger products such as Countdown Kits and Festival in a Box are priced on their own.</p>')
sl_list = sl_now + sl_up + sl_past
sl_url = f"{SITE_URL}/secret-lair.html"
# Title and H1 lead with the next drop so "next Secret Lair" answers name the sale. The schedule framing stays in the subtitle.
if h_sl:
    _sl_head = sl_head_label(h_sl)
    SL_TITLE = f"Next Secret Lair: {_sl_head} | MTG Drops"
    SL_H1 = f"Next Secret Lair: {_sl_head}"
    SL_DESC = f"Next Secret Lair: {_sl_head}. Schedule of drops on sale now, upcoming and recent, with dates, prices and buy/skip verdicts."
else:
    SL_TITLE = "Secret Lair Drops: Schedule, Prices & Verdicts | MTG Drops"
    SL_H1 = "Secret Lair Drops: Schedule, Prices & Verdicts"
    SL_DESC = "Secret Lair release schedule: drops on sale now, upcoming Secret Lair drops and recent sales, with dates, prices, card lists and buy/skip verdicts."
# Fair description of Secret Lair GG from its homepage (fetched 2026-11-03): drop and card database, calendar, BUY/TOSS-UP/SKIP vs sale price. No dig at their copy.
SL_GG = "https://secretlair.gg/"
sl_vs = (
 '<h2>MTG Drops vs Secret Lair GG</h2>'
 '<p>MTG Drops is a free Magic: The Gathering release calendar. It lists upcoming sets, Commander precons, Universes Beyond products and Secret Lair drops, each with a date, known prices and a short buy, wait or skip verdict. '
 f'You can subscribe every release (<a href="{BASE}/calendar.ics">calendar.ics</a>) or Secret Lair dates only (<a href="{BASE}/secret-lair.ics">secret-lair.ics</a>) in Google Calendar, Apple Calendar or Outlook. '
 'It is not a per-card price database, and it does not sell cards.</p>'
 f'<p><a href="{SL_GG}" rel=nofollow>Secret Lair GG</a> is a Secret Lair tracker. It keeps a database of drops and individual cards, a release calendar with countdowns, and BUY, TOSS-UP or SKIP calls that compare a drop\'s singles value with its sale price. It is built around Secret Lair, not the rest of the Magic release calendar.</p>'
 '<p>Use MTG Drops when you want the full release calendar, a buy/skip note and a calendar feed. Use Secret Lair GG when you want a Secret Lair card list and a singles-versus-price read on one drop. The two sites answer different questions. This page does not copy their price database. '
 'What each site covers was checked against the Secret Lair GG homepage on Nov 3, 2026.</p>')
sl_ld = [
 {"@context": "https://schema.org", "@type": "CollectionPage", "@id": sl_url + "#page", "name": SL_TITLE, "url": sl_url, "description": trim(SL_DESC, 300), "dateModified": PD, "isPartOf": {"@id": f"{SITE_URL}/#website"}, "publisher": {"@id": f"{SITE_URL}/#org"}},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "Secret Lair drops: on sale now, upcoming and recent", "itemListOrder": "https://schema.org/ItemListUnordered", "numberOfItems": len(sl_list),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate(sl_list)]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Secret Lair", "item": sl_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in sl_faq]},
]
# Dated sealed-vs-singles blurb for sold-out drops (editorial; no Product/Review schema).
# Goblin Storm / Dandân comps are TabletopMeta market evidence (Nov 3, 2026); those drops are not in releases.json.
TTM_SL = "https://www.tabletopmeta.com/blog/mtg-secret-lair"
_ss = next((r for r in sl if r["slug"] == "secret-lair-strange-school"), None)
_dd = next((r for r in sl if r["slug"] == "secret-lair-duality-distorted"), None)
_atl = next((r for r in sl if r["slug"] == "secret-lair-atlanta"), None)
_bb = next((r for r in sl if r["slug"] == "secret-lair-reality-fracture-bundle-bundles"), None)
_sealed_links = []
if _ss: _sealed_links.append(plink(_ss, short_name(_ss)))
if _dd: _sealed_links.append(plink(_dd, short_name(_dd)))
if _atl: _sealed_links.append(plink(_atl, short_name(_atl)))
if _bb: _sealed_links.append(plink(_bb, short_name(_bb)))
sl_sealed_html = (
  '<h2 id="sealed-vs-singles">Sealed vs singles on sold-out drops</h2>'
  '<div class=card>'
  f'<p>Last checked Nov 3, 2026 · source <a href="{TTM_SL}" rel=nofollow>TabletopMeta Secret Lair guide</a>. '
  'Goblin Storm and Dandân are not on our calendar; we cite them only as sealed-versus-singles market evidence.</p>'
  '<p>TabletopMeta\'s Nov 3 comps: Goblin Storm about $492.76 sealed versus about $230 in singles; '
  'Dandân about $222 sealed versus about $70 to build from singles. Sealed resale often runs well above the cards you\'d actually play.</p>'
  '<p><b>Our call for sold-out drops we list</b>'
  + ((" (" + "; ".join(_sealed_links) + ")") if _sealed_links else "")
  + ': Wait — don\'t pay resale for the sealed drop; buy the singles you\'ll actually play. '
  'For the Reality Fracture Bundle Bundles package, Skip resale: it already cost more than buying the parts at list.</p>'
  '</div>'
)
page(SL_TITLE, SL_DESC,
     f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › Secret Lair</nav><h1>{E(SL_H1)}</h1>'
     f'<p>Secret Lair drops: schedule, prices and verdicts. The heading is the next dated sale. The lists below are what is on sale now, what is coming up, and what has ended.</p>'
     f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
     f'<p><b>Last updated:</b> {tdate()} · {len(sl_now)} on sale now · {len(sl_up)} upcoming · {len(sl_past)} recent / ended</p>'
     + sl_next_block
     + f'<p><b>Secret Lair calendar feed:</b> {ics_link("secret-lair.ics")} Includes a timed sale (Nov 9, 9 AM PT) and a separate pre-queue (Nov 9, 8 AM PT) for Set Phasers to Superdrop; other drops stay all-day dates.</p>'
     + sl_intro + f'<p>Planning holiday buys? See <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>, sets and Commander decks included.</p>'
     + sl_vs
     + sl_section("On sale now", sl_now, "No Secret Lair sale has opened in the last few weeks. See Upcoming below.")
     + sl_section("Upcoming Secret Lair drops", sl_up, "No upcoming Secret Lair drops are announced right now.")
     + sl_section("Recent / ended", sl_past, "Nothing here yet.")
     + sl_sealed_html
     + '<p><small>Drops opened more than ' + str(SL_ONSALE_DAYS) + ' days ago are listed as recent / ended unless an end date is known; limited print runs may sell out sooner or stay in stock longer, so check MagicSecretLair.com.</small></p>'
     + "<h2>Secret Lair FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{faq_visible(a)}</p>" for q, a in sl_faq)
     + f'<h2>Get new Secret Lair drops by email</h2><p>What\'s Dropping is our free weekly email: new Secret Lair announcements, sale dates and a buy-or-skip verdict for each drop.</p>{FORM}'
     + f'<p class=disc><small>{E(DISCLOSURE)}</small></p><p><small>Last updated: {tdate()}</small></p>',
     "secret-lair.html", sl_ld)
_assert_phasers_hub("dist/secret-lair.html")
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
# ---- November 2026 buy/preorder section (fall guide, under the intro). Every price, date and verdict comes from releases.json;
# a curated one-line "why" is used only while the entry's verdict is still the one it was written for, otherwise the entry's own note shows.
G_NOV_CHECKED = "2026-10-31"
G_NOV_ID = "november-2026"
def g_r(slug): return next(r for r in data if r["slug"] == slug)
nv_kit, nv_ph, nv_st, nv_cmd = g_r("countdown-kit-marvels-history-of-heroes"), g_r("secret-lair-star-trek-set-phasers-superdrop"), g_r("star-trek"), g_r("star-trek-commander")
def nv_label(r, expected, special):
    v = r.get("verdict")
    return special if v == expected else (VERDICT_LABEL.get(v, v) if v else "No verdict yet")
def nv_why(r, expected, why): return why if r.get("verdict") == expected else r["note"]
def nv_prices(r, labels=None): return "; ".join(f"{p['label']}: {fmt(p)}" for p in (r.get("prices") or []) if not labels or p["label"] in labels) or "TBA"
_bmu = next((b for a, b in (nv_st.get("buy_guide") or []) if a.startswith("Bundles")), "")
_bmu_usd = re.findall(r"\$(\d+\.\d\d) MSRP \(8 Play Boosters", _bmu)
nv_st_price = nv_prices(nv_st) + (f"; Beam Me Up Bundle: ${_bmu_usd[0]}" if _bmu_usd else "")
nv_pre_link = f'<a href="{BASE}/guides/star-trek-mtg-release-guide.html#prerelease-kits">Star Trek prerelease</a>'
nv_rows = [
 ("Nov 2", plink(nv_kit, nv_kit["name"]), nv_prices(nv_kit), nv_label(nv_kit, "wait", "Wait unless you're a Marvel collector"),
  nv_why(nv_kit, "wait", "30 Marvel-art cards, mostly reprints plus 2 early Darkhold Destiny uncommons, about $6.67 a card; limited quantity at MagicSecretLair.com from 9 AM PT. Price out the singles you'd actually play.")),
 ("Nov 6–12", nv_pre_link + " (local game stores)", "Set by each store", ("Buy for the event; Wait if you only want cards; Skip as speculation" if nv_st.get("prerelease_verdict") else "No verdict yet"),
  ("Each Prerelease Pack is 6 Play Boosters, 1 traditional foil rare or mythic rare, a deck box and a spindown; Play Boosters hit stores Nov 13 at $6.99 MSRP." if nv_st.get("prerelease_verdict") else "Prerelease events at local game stores; see the Star Trek guide.")),
 ("Nov 9", plink(nv_ph, nv_ph["name"]), "About $30 non-foil / $40 foil per drop" if nv_ph.get("prices") else "TBA", nv_label(nv_ph, "buy", "Buy if you really like Star Trek; otherwise Skip"),
  nv_why(nv_ph, "buy", "6 Star Trek drops (5 revealed so far), 9 AM PT / 12 PM ET at MagicSecretLair.com: fan-collectible and theme play, not a speculative pickup.")),
 ("Nov 13", plink(nv_st, nv_st["name"]) + " (Play Boosters, Collector Boosters, Bundle, Beam Me Up Bundle)", nv_st_price, nv_label(nv_st, "buy", "Buy (Play Boosters / Bundle); Collector Boosters only for chase cards"),
  nv_why(nv_st, "buy", "For drafting and Trek fans; skip sealed speculation. Collector Boosters and both Bundles may arrive after Nov 13 in Europe or Asia-Pacific.")),
 ("Nov 13", plink(nv_cmd, "Star Trek Commander Decks"), nv_prices(nv_cmd), nv_label(nv_cmd, "buy", "Buy regular decks; Skip Collector's Editions at markup"),
  nv_why(nv_cmd, "buy", "Regular decks preorder near MSRP and Collector's Editions well above it (NerdSnack). In North America the decks may arrive after Nov 13 (Wizards, Oct 16): check your preorder's ship date.")),
]
nv_left = [(r, t) for r, t in (
 (g_r("secret-lair-chaos-vault-reality-fracture"), "delayed globally (Wizards, Oct 19). Wait for stock at the $89.99 MSRP; pre-release retailer listings ran $159.99–$189.99."),
 (g_r("secret-lair-atlanta"), "sold out at the official store ($249.99). Wait: don't overpay on resale (eBay listings over $450, per MTG Rocks)."),
 (g_r("mystery-booster-commander-edition"), "only sold inside Festival in a Box: Atlanta 2026, now sold out. Wait: MTG Rocks expects it to return with future MagicCon Festival in a Box releases, so don't pay resale."),
 (g_r("secret-lair-strange-school"), "sold out on launch day (Oct 26). Wait: don't pay resale for the sealed drop; buy the singles you'll actually play."),
 (g_r("secret-lair-duality-distorted"), "sold out on launch day (Oct 26). Wait: don't pay resale for the sealed drop; buy the singles you'll actually play."),
) if r.get("verdict") == "wait"]
_corn = g_r("secret-lair-corn-maze-superdrop"); _bb = g_r("secret-lair-reality-fracture-bundle-bundles"); _spm = g_r("spider-mania-commander")
_ce_name = "Star Trek Collector's Edition Commander decks"
nv_dont = [f"{plink(nv_cmd, _ce_name)} above their {fmt(nv_cmd['prices'][1])} MSRP: buy the {fmt(nv_cmd['prices'][0])} regular decks instead."
           if len(nv_cmd.get("prices") or []) > 1 else None,
           f"Sealed {plink(nv_st, 'Star Trek')} boxes bought to speculate on.",
           f"{plink(_corn, _corn['short_name'])} as a holiday gift: Wizards expects US orders to ship Dec 15, 2026 – Mar 15, 2027." if "Dec 15, 2026" in (_corn.get("window") or "") else None,
           f"{plink(_bb, _bb['short_name'])} on resale (our verdict: Skip)." if _bb.get("verdict") == "skip" else None,
           f"{plink(_spm, _spm['short_name'])} (Dec 4, unconfirmed leak): wait for Wizards to confirm it and show the decklist." if _spm.get("verdict") == "wait" and _spm["status"] != "confirmed" else None]
nv_dont = [x for x in nv_dont if x]
# Dated Star Trek street prices, fetched 2026-11-03. Do not change a number without a new fetch and a new date.
# Never print a percent off: the table shows MSRP and the store low only.
# Play Booster Display is 30 packs (releases.json inside text, from Wizards), so box MSRP is 30 x $6.99.
# Older sets used 36-pack displays. Star Trek does not, so this table does not use 36 x $6.99.
# Source A (Play Booster Display): https://mtgcompare.app/us/p/star-trek-play-booster-box
#   Page said "checked 20 min ago". Store low $117.95 at Poke-Collect. TCGplayer line on that page $118.62. Shipping excluded.
# Source B (other rows): https://mtgcompare.app/us/preorders/star-trek
#   Page said "Prices checked 2 hours ago".
#   Bundle $42.99 Double Infinity Gaming; Draft Night $86.99 Double Infinity Gaming;
#   Collector Booster box $449.99 Gate City Games; Beam Me Up Bundle $99.99 at 4GS Games;
#   regular Commander low Klingon Fury $49.95 Galactic Toys;
#   Collector's Edition Commander store low $159.99 Cole Street Game Vault (Federation Fleet);
#   that same Collector's Edition section showed a TCGplayer preorder at $215.58;
#   Enterprise-Q Scene Box $33.95 Lazarus Games.
# Source C: https://www.coolstuffinc.com/p/443286 fetched the same day. Draft Night was Out of Stock and the page
#   did not display a price. A Nov 2 public listing had shown $94.99 against the $119.99 MSRP. That $94.99 is not today's low.
ST_PRE_CHECKED = "2026-11-03"
ST_PRE_PAGE = "https://mtgcompare.app/us/preorders/star-trek"
ST_PLAY_PAGE = "https://mtgcompare.app/us/p/star-trek-play-booster-box"
CSI_DRAFT = "https://www.coolstuffinc.com/p/443286"
GR_BF = "https://www.gamesradar.com/black-friday-magic-the-gathering-deals-and-savings/"
# Retailer windows checked live Nov 5, 2026. Do not print a projected Amazon date.
BF_DATES_CHECKED = "2026-11-05"
TARGET_BF_USA = "https://www.usatoday.com/story/shopping/deals/black-friday/2026/10/28/target-early-black-friday-sale-dates/92483386007/"
TARGET_BF_AL = "https://www.al.com/shopping/2026/11/when-is-target-black-friday-2026-sale-dates-and-early-deals.html"
WALMART_BF_SRC = "https://corporate.walmart.com/news/2026/10/walmart-unwraps-three-major-holiday-shopping-events"
_st_inside = json.dumps(nv_st["inside"])
if "30 per box" not in _st_inside or "12 per box" not in _st_inside:
    raise SystemExit("Star Trek display pack counts missing from releases.json; not printing a box MSRP")
_pb_usd = next(p["usd"] for p in nv_st["prices"] if p["label"] == "Play Booster")
_cpack = next(p["usd"] for p in nv_st["prices"] if p["label"] == "Collector Booster")
_bundle_msrp = next(p["usd"] for p in nv_st["prices"] if p["label"] == "Bundle")
_cmd_msrp = next(p["usd"] for p in nv_cmd["prices"] if p["label"].startswith("Commander Deck"))
_ce_msrp = next(p["usd"] for p in nv_cmd["prices"] if "Collector" in p["label"])
def _inside_msrp(label):
    m = re.search(re.escape(label) + r" \$(\d+\.\d\d)", _st_inside)
    if not m: raise SystemExit("missing Star Trek MSRP in releases.json: " + label)
    return float(m.group(1))
_bmu_msrp, _draft_msrp, _scene_msrp = _inside_msrp("Beam Me Up Bundle"), _inside_msrp("Draft Night"), _inside_msrp("Scene Box")
_play_box_msrp, _coll_box_msrp = round(30 * _pb_usd, 2), round(12 * _cpack, 2)
def retail_links(query, amz_url=None):
    amz = amz_url or ("https://www.amazon.com/s?k=" + urllib.parse.quote_plus(query) + "&tag=" + AMAZON_TAG)
    return (f'<a href="{E(tcg(query))}" rel="sponsored nofollow">TCGplayer</a> · '
            f'<a href="{E(amz)}" rel="sponsored nofollow noopener" target="_blank">Amazon</a>')
def _prow(product, msrp, street, where, query, amz_url=None):
    return f"<tr><td>{product}</td><td>{E(msrp)}</td><td>{E(street)}</td><td>{where}</td><td>{retail_links(query, amz_url)}</td></tr>"
_st_link = plink(nv_st, "MTG Star Trek")
_cmd_link = plink(nv_cmd, "Star Trek Commander")
st_price_rows = [
 _prow(f"Play Booster Display (box, 30 packs) — {_st_link}", fmt({"usd": _play_box_msrp}) + f" (30 × {fmt({'usd': _pb_usd})})", "$117.95",
        "Poke-Collect, via MTG Compare. The same page showed TCGplayer at $118.62.", "Magic The Gathering Star Trek Play Booster Box"),
 _prow(f"Draft Night — {_st_link}", fmt({"usd": _draft_msrp}), "$86.99",
        "Double Infinity Gaming, via MTG Compare.", "Magic The Gathering Star Trek Draft Night"),
 _prow(f"Bundle — {_st_link}", fmt({"usd": _bundle_msrp}), "$42.99",
        "Double Infinity Gaming, via MTG Compare.", "Magic The Gathering Star Trek Bundle", amazon(nv_st)),
 _prow(f"Commander deck (regular) — {_cmd_link}", fmt({"usd": _cmd_msrp}) + " each", "$49.95",
        "Lowest single deck: Klingon Fury at Galactic Toys. Other regular decks on the page were $54.95 to $64.99.", "Magic The Gathering Star Trek Commander Deck"),
 _prow(f"Collector's Edition Commander deck — {_cmd_link}", fmt({"usd": _ce_msrp}) + " each", "$159.99",
        "Federation Fleet at Cole Street Game Vault. The same section showed a TCGplayer preorder at $215.58.", "Magic The Gathering Star Trek Collector Edition Commander Deck"),
 _prow(f"Collector Booster box (12 packs) — {_st_link}", fmt({"usd": _coll_box_msrp}) + f" (12 × {fmt({'usd': _cpack})})", "$449.99",
        "Gate City Games, via MTG Compare. Keystone Games listed $455.88 on the same page.", "Magic The Gathering Star Trek Collector Booster Box"),
 _prow(f"Beam Me Up Bundle — {_st_link}", fmt({"usd": _bmu_msrp}), "$99.99",
        "4GS Games, via MTG Compare.", "Magic The Gathering Star Trek Beam Me Up Bundle"),
 _prow(f"Scene Box (Enterprise-Q) — {_st_link}", fmt({"usd": _scene_msrp}), "$33.95",
        "Lazarus Games, via MTG Compare. Divergent Timeline was also $33.95.", "Magic The Gathering Star Trek Scene Box"),
]
st_price_html = (
 f'<h3 id="star-trek-preorder-prices">Star Trek preorder prices, Nov 3</h3>'
 + checked({"last_checked": ST_PRE_CHECKED, "source": ST_PRE_PAGE, "field_sources": {"play box": ST_PLAY_PAGE, "coolstuffinc draft night": CSI_DRAFT, "wizards": nv_st["source"]}})
 + "<p>MSRP is Wizards' price (Play Booster, Collector Booster and Bundle from the set entry; Draft Night, Beam Me Up Bundle and Scene Box from the same Wizards product list stored on that entry). "
 "A display MSRP is pack-count arithmetic: the Star Trek Play Booster Display is 30 packs, not a 36-pack display, and the Collector Booster box is 12. Both counts are in Wizards' collecting article, already stored on the set entry. "
 "Street low is the cheapest US store preorder <a href=\"" + ST_PRE_PAGE + "\" rel=nofollow>MTG Compare</a> showed on Nov 3, 2026, except the Play Booster Display, which uses the "
 f'<a href="{ST_PLAY_PAGE}" rel=nofollow>Play Booster Box page</a> fetched the same day because it was a few dollars lower. '
 "Those prices exclude shipping and tax. This table does not state a percent off.</p>"
 + "<table><tr><th>Product</th><th>MSRP</th><th>Street low, Nov 3</th><th>Where we saw the low</th><th>Check prices</th></tr>"
 + "".join(st_price_rows) + "</table>"
 + "<p><small>Footnotes, all Nov 3, 2026 unless noted. "
 f"Play Booster Display: <a href=\"{ST_PLAY_PAGE}\" rel=nofollow>MTG Compare</a> said the $117.95 Poke-Collect preorder was checked 20 minutes before we fetched the page. Shipping there was quoted at $6.71 to $9.16. "
 f"The other rows are from <a href=\"{ST_PRE_PAGE}\" rel=nofollow>MTG Compare's Star Trek preorder page</a>, which said its prices had been checked 2 hours earlier. "
 "Bundle $42.99 and Draft Night $86.99 were both Double Infinity Gaming, each with $9.90 shipping on that page. "
 f"CoolStuffInc's <a href=\"{CSI_DRAFT}\" rel=nofollow>Draft Night page</a> was Out of Stock and showed no price when we opened it. "
 "On Nov 2 that listing had shown $94.99 against the $119.99 MSRP, so $94.99 is not the Nov 3 low. "
 "Collector's Edition store lows were at the $159.99 MSRP; the $215.58 figure is the TCGplayer preorder MTG Compare printed beside Federation Fleet, not the cheapest store. "
 "MTG Compare still listed a Star Trek Beginner Box. Wizards removed that product, so it is not in this table. "
 "Check prices uses our Amazon Associates tag (mtgdrops-20) and TCGplayer Impact links. The Bundle's Amazon link is the approved product page. The other Amazon links are searches.</small></p>")
g_nov_html = (f'<h2 id="{G_NOV_ID}">What MTG to buy or preorder in November 2026</h2>'
  + checked({"last_checked": G_NOV_CHECKED, "source": nv_kit["source"], "field_sources": {"st": nv_st["source"], "ph": nv_ph["source"], "delays": nv_cmd["field_sources"]["delays"]}})
  + "<p>Four buying moments in 12 days. Here is our call on each, week by week, with Wizards' MSRPs (store prices vary). Click a product for its sources. "
  f'Street prices for the Star Trek products are in <a href="#star-trek-preorder-prices">Star Trek preorder prices, Nov 3</a>.</p>'
  + "<table><tr><th>Date</th><th>Product</th><th>MSRP</th><th>Buy / Wait / Skip</th><th>Why</th></tr>"
  + "".join(f"<tr><td>{E(d)}</td><td>{p}</td><td>{E(m)}</td><td><b>{E(v)}</b></td><td>{E(w)}</td></tr>" for d, p, m, v, w in nv_rows) + "</table>"
  + st_price_html
  + "<h3>Still open from October</h3><ul>" + "".join(f"<li>{plink(r, r.get('short_name') or r['name'])}: {E(t)}</li>" for r, t in nv_left) + "</ul>"
  + "<h3>Don't preorder</h3><ul>" + "".join(f"<li>{x}</li>" for x in nv_dont) + "</ul>"
  + f'<p><b>How we decide:</b> Buy means worth it at MSRP for the people we name, Wait means hold for better stock, a better price or more information, and Skip means not worth it at the current price. The free <a href="{BASE}/newsletter.html">What\'s Dropping newsletter</a> flags new verdicts and price or date changes every Monday.</p>')
# Black Friday category verdicts. Owner approved these for publish on Nov 3, 2026.
# Published timing calls (substance unchanged from the former Proposed lines):
# - Star Trek Play Booster box and Bundle: Wait
# - Star Trek Collector Booster box above MSRP: Skip / Wait for singles
# - Star Trek Commander: don't pay above MSRP; expect Black Friday discounts
#   (the "buy regular, skip CE at markup" line is the existing verdict, not a new one)
# - Older 2026 Commander decks and beginner/starter products: Wait for Black Friday
# Settled, reused verbatim from the product notes:
# - Star Trek set: "Buy for drafting/Trek fans; skip sealed speculation."
# - Set Phasers: "Buy only if you really like Star Trek; otherwise skip."
# - Sold-out drops: "Wait: don't pay resale for the sealed drop; buy the singles you'll actually play."
# The "not discounted at MagicSecretLair.com" sentence is the settled Secret Lair exception.
# It is not a new per-drop verdict.
# Countdown Kit stays on sale in our data. This section must not call it sold out. The poller owns that flip.
_st_settled = "Buy for drafting/Trek fans; skip sealed speculation."
_ph_settled = "Buy only if you really like Star Trek; otherwise skip."
_cmd_settled = "buy regular, skip CE at markup"
_sold_settled = "Wait: don't pay resale for the sealed drop; buy the singles you'll actually play."
for _need, _blob in ((_st_settled, nv_st["note"]), (_ph_settled, nv_ph["note"]), (_cmd_settled, nv_cmd["note"]),
                     (_sold_settled, g_r("secret-lair-strange-school")["note"])):
    if _need not in _blob: raise SystemExit("settled verdict missing from releases.json: " + _need)
_rf = g_r("secret-lair-chaos-vault-reality-fracture")
G_BF_ID = "black-friday-2026"
bf_rows = [
 (f'{plink(nv_st, "Star Trek Play Booster box")} and {plink(nv_st, "Bundle")}',
  f"Already under MSRP before the Nov 13 release. Nov 3 store lows: Play Booster Display $117.95 (MSRP {fmt({'usd': _play_box_msrp})}) and Bundle $42.99 (MSRP {fmt({'usd': _bundle_msrp})}). See the Nov 3 price table. GamesRadar (updated Nov 2, 2026) says cuts often start in mid-November.",
  "Wait",
  f"The set-level verdict stays: {_st_settled} This row is only about timing. Street prices are already under MSRP, so there is no need to preorder today if you can check again nearer Nov 27."),
 (f'{plink(nv_st, "Star Trek Collector Booster box")} above MSRP',
  f"Pack-math MSRP is {fmt({'usd': _coll_box_msrp})} (12 × {fmt({'usd': _cpack})}). On Nov 3 the cheapest store preorder was $449.99, which is under that figure. This call applies when a listing is above {fmt({'usd': _coll_box_msrp})}.",
  "Skip above MSRP / Wait for singles",
  "Collector Boosters are for chase cards, not a sealed bet. Skip a box priced above MSRP and buy the singles you want after release, once prices settle."),
 (plink(nv_cmd, "Star Trek Commander decks"),
  f"Regular decks are {fmt({'usd': _cmd_msrp})} MSRP and Collector's Editions are {fmt({'usd': _ce_msrp})} MSRP. On Nov 3 the lowest regular deck MTG Compare showed was Klingon Fury at $49.95. Collector's Edition store lows were {fmt({'usd': _ce_msrp})}, with a TCGplayer preorder at $215.58 on the Federation Fleet section.",
  f"Settled: {_cmd_settled}. Don't pay above MSRP; expect Black Friday discounts.",
  f"Existing verdict, unchanged: {_cmd_settled}. Don't pay more than the MSRP, and expect stores to discount these decks."),
 ("Older 2026 Commander decks and beginner or starter products",
  "GamesRadar (updated Nov 2, 2026) says that if previous years hold, Commander decks a few months old should see $10 off the sticker price, or more when the deck is older. That is their pattern. We did not measure a percent off.",
  "Wait for Black Friday",
  f"This is for Commander precons and beginner or starter products already in stores from earlier in 2026. It is not the Nov 13 Star Trek decks, and it is not {plink(_spm, _spm['short_name'])}, which is still an unconfirmed leak. Wizards removed the Star Trek Beginner Box, so a leftover listing of that box is not a product we are telling you to buy."),
 (plink(_rf, _rf["short_name"]),
  "Delayed globally (Wizards, Oct 19). Pre-release retailer listings ran $159.99–$189.99 against the $89.99 MSRP.",
  "Wait (settled)",
  "Wait for stock at the $89.99 MSRP. Don't overpay: wait for MSRP stock unless you love the Secret Lair mythic art."),
 (plink(nv_ph, "Secret Lair, including Set Phasers to Superdrop"),
  "Sold at MagicSecretLair.com at the drop's listed price. Set Phasers to Superdrop goes on sale Nov 9, about $30 non-foil or $40 foil per drop. A sold-out drop is not restocked there for Black Friday.",
  f"Settled: {_ph_settled} Not discounted at MagicSecretLair.",
  f"{_ph_settled} For a drop that has already sold out at the official store: {_sold_settled}"),
]
_bf_cmd_extra = (f" {plink(_spm, _spm['short_name'])} is still an unconfirmed leak, so it is not a Black Friday buy: wait until Wizards confirms it and shows the decklist."
                 if _spm.get("verdict") == "wait" and _spm["status"] != "confirmed" else "")
_bf_bundle_extra = f" {plink(_bb, _bb['short_name'])} stays Skip on resale." if _bb.get("verdict") == "skip" else ""
_bf_corn = (f" {plink(_corn, _corn['short_name'])}: Wizards expects US orders to ship Dec 15, 2026 – Mar 15, 2027. Don't count on it under the tree."
            if "Dec 15, 2026" in (_corn.get("window") or "") else "")
g_bf_dates = (
 f'<h3 id="retailer-early-sales">Retailer early-sale dates</h3>'
 + checked({"last_checked": BF_DATES_CHECKED, "source": TARGET_BF_USA, "field_sources": {"al.com": TARGET_BF_AL, "walmart": WALMART_BF_SRC}})
 + "<p>These are announced store calendars, not a list of Magic discounts. A window can open without any given MTG box being reduced. "
 "Black Friday is Nov 27, 2026. Cyber Monday is Nov 30, 2026. Last checked Nov 5, 2026.</p><ul>"
 + f'<li><b>Target early Black Friday sale:</b> Thu Nov 5 – Sat Nov 7, 2026. Target also runs a daily Deal of the Day from Nov 1 through Dec 24, and new weekend offers afterward. '
 f'Sources: <a href="{TARGET_BF_USA}" rel=nofollow>USA Today</a>, <a href="{TARGET_BF_AL}" rel=nofollow>al.com</a>.</li>'
 + f'<li><b>Walmart Early Black Friday Deals:</b> Nov 12–15, 2026. <b>Walmart Black Friday Deals:</b> Nov 23–29, 2026 '
 "(online at 12:01 a.m. ET; in stores Nov 12 and Nov 27 at 6 a.m. local; Walmart+ early access on Nov 12 and Nov 23). "
 f'<b>Walmart Cyber Monday:</b> Nov 30 – Dec 2, 2026. Source: <a href="{WALMART_BF_SRC}" rel=nofollow>Walmart</a>.</li>'
 + "<li><b>Amazon US:</b> Amazon has not announced US Black Friday dates yet. Black Friday is Nov 27 and Cyber Monday is Nov 30.</li>"
 + "</ul>")
g_bf_frame = (
 "<h3>Holiday boxes: buy, wait, or skip</h3>"
 + "<p>The calls in the table are unchanged. Here is how they apply to Commander decks, beginner and starter boxes, bundles, and older Secret Lairs.</p><ul>"
 + f"<li><b>Commander decks.</b> Older 2026 Commander decks already in stores: Wait for Black Friday. {plink(nv_cmd, 'Star Trek Commander decks')}: buy regular decks, skip Collector's Editions at markup. Don't pay above MSRP, and expect Black Friday discounts.{_bf_cmd_extra}</li>"
 + "<li><b>Beginner and starter boxes.</b> Beginner or starter products already in stores from earlier in 2026: Wait for Black Friday. Wizards removed the Star Trek Beginner Box, so a leftover listing of that box is not a product we are telling you to buy.</li>"
 + f"<li><b>Bundles.</b> {plink(nv_st, 'Star Trek Bundle')}: Wait. On Nov 3 a store listed it at $42.99, under the {fmt({'usd': _bundle_msrp})} MSRP.{_bf_bundle_extra}</li>"
 + f"<li><b>Older Secret Lairs.</b> Not discounted at MagicSecretLair.com. {plink(nv_ph, 'Set Phasers to Superdrop')} on Nov 9: {_ph_settled} A drop that has already sold out at the official store: {_sold_settled}{_bf_corn}</li>"
 + "</ul>"
 + f'<p>Compare a percent-off tag with what the box costs on an ordinary day. For Commander decks, check {retail_links("Magic The Gathering Commander Deck")}. The <a href="#star-trek-preorder-prices">Nov 3 Star Trek table</a> has a Check prices column for that set. Amazon links use the mtgdrops-20 tag. TCGplayer links are Impact affiliate links.</p>')
g_bf_html = (
 f'<h2 id="{G_BF_ID}">Black Friday 2026: buy now or wait?</h2>'
 + checked({"last_checked": ST_PRE_CHECKED, "source": GR_BF, "field_sources": {"mtg compare": ST_PRE_PAGE, "play box": ST_PLAY_PAGE}})
 + "<p><b>Should you buy MTG now or wait for Black Friday 2026?</b> For most sealed Magic, the call is to wait. "
 "Black Friday is Nov 27, 2026, and Cyber Monday is Nov 30, 2026. "
 f'<a href="{GR_BF}" rel=nofollow>GamesRadar</a> (updated Nov 2, 2026) says the official Magic deals start on Nov 27, with price cuts often showing up from mid-November, and that discounts usually continue through Cyber Monday. '
 f"Star Trek Play Booster boxes and Bundles were already listed below MSRP at some stores before the Nov 13 release (see <a href=\"#star-trek-preorder-prices\">the Nov 3 price table</a>). "
 f"Secret Lair is the exception: drops are not discounted at MagicSecretLair.com, so buy Set Phasers to Superdrop on Nov 9 only if you really like Star Trek. Last checked: Nov 3, 2026.</p>"
 + "<h3>When MTG Black Friday deals start</h3>"
 + f'<p>The sale date is Friday, Nov 27, 2026. The Monday after it, Cyber Monday, is Nov 30, 2026. '
 f'<a href="{GR_BF}" rel=nofollow>GamesRadar</a> says Magic discounts usually begin earlier than that Friday, from around the middle of November, and then hang on past Black Friday itself. '
 "We don't run a live deal tracker. The dates above are the calendar, plus that GamesRadar timing note. "
 f'<a href="#retailer-early-sales">Retailer early-sale dates</a> are a separate check.</p>'
 + g_bf_dates
 + "<h3>Buy now, wait, or skip</h3>"
 + "<p>The November table above is the week-by-week call for this month. This table is the Black Friday timing call.</p>"
 + "<table><tr><th>Category</th><th>Typical deal pattern</th><th>Our call</th><th>Why</th></tr>"
 + "".join(f"<tr><td>{c}</td><td>{E(p)}</td><td><b>{E(v)}</b></td><td>{w}</td></tr>" for c, p, v, w in bf_rows)
 + "</table>"
 + g_bf_frame
 + "<h3>Gift-buyer warnings</h3><ul>"
 + (f"<li><b>US shipping warning — {plink(_corn, _corn['short_name'])}:</b> Wizards expects US orders to ship Dec 15, 2026 – Mar 15, 2027. Don't count on it under the tree.</li>" if "Dec 15, 2026" in (_corn.get("window") or "") else "")
 + f"<li>{plink(nv_kit, nv_kit['short_name'])} is still listed as on sale on our Secret Lair page. Check MagicSecretLair.com before you pay anyone else. If the official listing is gone, {_sold_settled}</li>"
 + f"<li>Star Trek Collector Boosters, Bundles, Beam Me Up Bundles and Draft Night may arrive after Nov 13 in Europe or Asia-Pacific, and the Commander decks may arrive after Nov 13 in North America (Wizards, Oct 16). Read the ship date on a preorder before you treat it as a gift that will be here in November.</li>"
 + "</ul>"
 + "<h3>Where to check prices</h3>"
 + f'<p>Use the Check prices links in the <a href="#star-trek-preorder-prices">Nov 3 Star Trek table</a> (Amazon tag mtgdrops-20, TCGplayer Impact). '
 f'Or start from <a href="{E(tcg("Magic The Gathering Star Trek"))}" rel="sponsored nofollow">TCGplayer</a> and '
 f'<a href="{E(amazon(nv_st))}" rel="sponsored nofollow noopener" target="_blank">Amazon</a>. '
 "We don't track live deal prices. The street lows above are a dated check, not a feed, and a store can change them the same day.</p>")
_kit_note = nv_kit["note"]
nv_faq = [
 ("Which MTG products are worth preordering this month?",
  f"For November 2026: the Star Trek set ({nv_label(nv_st, 'buy', 'Buy')} for drafting and Trek fans; Play Boosters {fmt(nv_st['prices'][0])}, Bundle {fmt(nv_st['prices'][2])}) and the regular Star Trek Commander decks ({fmt(nv_cmd['prices'][0])}, {nv_label(nv_cmd, 'buy', 'Buy')}; skip Collector's Editions at markup). "
  f"Set Phasers to Superdrop (Nov 9): {nv_label(nv_ph, 'buy', 'buy if you really like Star Trek, otherwise skip')}. The Marvel History of Heroes Countdown Kit (Nov 2, {fmt(nv_kit['prices'][0])}): {nv_label(nv_kit, 'wait', 'wait unless you are a Marvel collector')}. Don't preorder anything above MSRP to speculate."),
 ("Is the Marvel History of Heroes Countdown Kit worth $199.99?",
  f"{_kit_note} It goes on sale {nice_date(nv_kit)} at 9 AM PT, only at MagicSecretLair.com."),
 ("Should I preorder the Star Trek Bundle or Collector Boosters?",
  " ".join(f"{a}: {b}" for a, b in (nv_st.get("buy_guide") or []) if a in ("Bundles / Beam Me Up Bundles", "Collector Boosters")) or nv_st["note"]),
 ("Will Star Trek Commander decks be in stores on Nov 13?",
  f"Maybe not in North America. {nv_cmd['window'].replace('Preorders open. ', '')}. Check your preorder's ship date; Play Boosters and Prerelease Packs are on track everywhere."),
]
g_faq = [((f"What MTG products come out in {g_month_name(m)}?" if m == "2026-11" else f"What MTG products release in {g_month_name(m)}?"),
          (f"{g_names(rs)}." if rs else f"Nothing is on our calendar for {g_month_name(m)} yet.")
          + (f" Star Trek prerelease events run {nv_st['prerelease']} at local game stores, and the set reaches MTG Arena Nov 10, 2026." if m == "2026-11" and nv_st.get("prerelease") else "")
          + " Dates marked unconfirmed can still change.") for m, rs in g_by.items()]
g_faq = nv_faq[:1] + [q for q in g_faq if q[0].startswith("What MTG products come out in November")] + nv_faq[1:] + [q for q in g_faq if not q[0].startswith("What MTG products come out in November")]
g_faq.append(("What is the best MTG gift for the 2026 holidays?",
              ("Our picks, all rated buy: " + "; ".join(f"{short_name(r)} for {r['gift_for'].split(':')[0]}" for r in g_gifts) + ". If you're unsure, a gift card for a local game store avoids guessing.") if g_gifts else "We don't have any items rated buy for this season yet."))
if nxt_set: g_faq.append(("What is the next MTG set after 2026?", f"{nxt_set['name']}, releasing {nice_date(nxt_set)} ({nxt_set['status']})."))
g_faq += [
 ("When do MTG Black Friday deals start in 2026?",
  "Black Friday is Nov 27, 2026, and Cyber Monday is Nov 30, 2026. GamesRadar (updated Nov 2, 2026) says the official Magic deals start on Nov 27, with price cuts often appearing from mid-November, and that discounts usually continue through Cyber Monday. "
  "Retailer windows, last checked Nov 5, 2026: Target's early Black Friday sale is Thu Nov 5 – Sat Nov 7, 2026, with a daily Deal of the Day from Nov 1 through Dec 24 and new weekend offers afterward. "
  "Walmart Early Black Friday Deals are Nov 12–15. Walmart Black Friday Deals are Nov 23–29 (online at 12:01 a.m. ET; in stores Nov 12 and Nov 27 at 6 a.m. local; Walmart+ early access on Nov 12 and Nov 23). Walmart's Cyber Monday is Nov 30 – Dec 2. "
  "Amazon has not announced US Black Friday dates yet."),
 ("Should I wait for Black Friday to buy MTG Star Trek?",
  f"Wait on a Star Trek Play Booster box or Bundle. On Nov 3, 2026, MTG Compare showed store preorders under MSRP ($117.95 for a Play Booster Display against the {fmt({'usd': _play_box_msrp})} pack-math MSRP, and $42.99 for a Bundle against {fmt({'usd': _bundle_msrp})}). The set-level verdict is unchanged: {_st_settled} Skip a Collector Booster box priced above {fmt({'usd': _coll_box_msrp})} and wait for singles. Commander stays: {_cmd_settled}. Don't pay above MSRP, and expect Black Friday discounts."),
 ("Are Secret Lair drops discounted on Black Friday?",
  f"No. Secret Lair drops are not discounted for Black Friday at MagicSecretLair.com. Set Phasers to Superdrop goes on sale Nov 9, 2026: {_ph_settled} For a drop that has already sold out at the official store: {_sold_settled}"),
 ("What MTG products are worth buying on Black Friday?",
  "Older 2026 Commander decks and beginner or starter products already in stores, where GamesRadar expects about $10 off sticker if previous years hold. A Star Trek Bundle or Play Booster box that is still under MSRP can be the Black Friday buy if you wanted one for drafting. Skip a Collector Booster box above MSRP, skip sealed product bought to speculate, and do not count on a Secret Lair discount at MagicSecretLair.com."),
 ("Is it better to buy MTG Commander decks on Black Friday?",
  f"For Commander decks that have been out for a few months, yes, wait for Black Friday. GamesRadar (updated Nov 2, 2026) says those decks have typically been about $10 off sticker, or more when the deck is older. For Star Trek Commander the settled verdict is: {_cmd_settled}. Don't pay above the {fmt({'usd': _cmd_msrp})} or {fmt({'usd': _ce_msrp})} MSRP, and expect discounts. On Nov 3, MTG Compare already showed Klingon Fury at $49.95."),
]
g_body = (f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › <a href="{BASE}/guides/">Guides</a> › Fall/Holiday 2026</nav><h1>{E(G_H1)}</h1>'
  f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
  f'<p><b>Last updated:</b> {tdate()} · {len(g_items)} products from October to December 2026</p>'
  f'<p>Every Magic: The Gathering product on our calendar for October, November and December 2026: sets, Commander decks, Secret Lair drops, bundles and special releases, with release dates, MSRPs and our buy/skip verdict. Secret Lair sales are tracked on the <a href="{BASE}/secret-lair.html">Secret Lair hub</a>, and November\'s biggest release has its own <a href="{BASE}/guides/star-trek-mtg-release-guide.html">Star Trek release guide</a>. Looking further ahead? See the <a href="{BASE}/guides/mtg-2027-release-schedule.html">MTG 2027 release schedule</a>. Deciding what to lock in now? Start with <a href="#{G_NOV_ID}">what to buy or preorder in November 2026</a>, then <a href="#{G_BF_ID}">Black Friday 2026: buy now or wait</a>.</p>'
  + g_nov_html
  + g_bf_html
  + "<h2>Best picks for gifts</h2>" + (f'<p>Only products we already rate as a buy, and who each one suits. For whether to buy one now or wait until Black Friday, see <a href="#{G_BF_ID}">Black Friday 2026: buy now or wait</a>.</p><ul>' + "".join(f'<li><a href="{BASE}/p/{r["slug"]}.html">{E(short_name(r))}</a> ({nice_date(r)}): for {E(r["gift_for"])}.</li>' for r in g_gifts) + "</ul>" if g_gifts else "<p>No buy-rated products this season yet.</p>")
  + "".join(f"<h2>{g_month_name(m)}</h2>" + ("".join(guide_item(r) for r in rs) if rs else "<p>Nothing scheduled yet.</p>") for m, rs in g_by.items())
  + ("<h2>Announced, no date yet</h2><p>Announced but not yet scheduled, so these may or may not land before the end of 2026.</p>" + "".join(guide_item(r) for r in g_tba) if g_tba else "")
  + f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  + "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in g_faq)
  + f"<h2>Get the weekly release email</h2><p>What's Dropping covers what's releasing next, date and price changes, and a buy-or-skip verdict for each product.</p>{FORM}<p><small>Last updated: {tdate()}</small></p>")
g_list = g_items + g_tba
# This page's JSON-LD: Article + FAQPage + both ItemLists + BreadcrumbList (+ Organization).
# Retailer sale windows stay in the HTML / BF ItemList. Do not add Product, Review,
# AggregateRating, Rating, Offer, or Event. dateModified lives on the Article so the build
# can still stamp it when the page hash changes (visible "Last updated" uses the same date).
g_ld = [
 {"@context": "https://schema.org", "@type": "Article", "headline": G_H1, "url": g_url, "mainEntityOfPage": g_url, "image": OG_IMAGE, "datePublished": G_PUBLISHED, "dateModified": PD,
  "author": {"@id": f"{SITE_URL}/#org"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "isPartOf": {"@id": f"{SITE_URL}/#website"},
  "description": "Every Magic: The Gathering product releasing October to December 2026, with dates, prices, buy/skip verdicts, a November 2026 buy/preorder table, dated Star Trek street prices, Black Friday buy-now-or-wait calls and holiday gift picks."},
 {"@context": "https://schema.org", **ORG},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "MTG releases, October to December 2026", "numberOfItems": len(g_list),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate(g_list)]},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "Black Friday 2026: buy now or wait", "numberOfItems": len(bf_rows),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "name": plain(c), "description": p + " Call: " + v + ". " + plain(w)} for i, (c, p, v, w) in enumerate(bf_rows)]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{SITE_URL}/guides/"},
   {"@type": "ListItem", "position": 3, "name": "Fall/Holiday 2026 MTG releases", "item": g_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in g_faq]},
]
def _ld_types(o, acc):
    if isinstance(o, dict):
        t = o.get("@type")
        if isinstance(t, str): acc.add(t)
        elif isinstance(t, list): acc.update(t)
        for v in o.values(): _ld_types(v, acc)
    elif isinstance(o, list):
        for v in o: _ld_types(v, acc)
_g_types = set(); _ld_types(g_ld, _g_types)
_G_LD_OK = {"ItemList", "BreadcrumbList", "ListItem", "Article", "FAQPage", "Question", "Answer", "Organization", "Brand", "WebSite"}
_G_LD_BAN = {"Review", "AggregateRating", "Rating", "Event"}
if _g_types & _G_LD_BAN:
    raise SystemExit("fall guide JSON-LD must not include Review/AggregateRating/Rating/Event: " + str(sorted(_g_types & _G_LD_BAN)))
if _g_types - _G_LD_OK:
    raise SystemExit("fall guide JSON-LD has unexpected types: " + str(sorted(_g_types - _G_LD_OK)))
G_DESC = "What MTG to buy or preorder in November 2026, with Star Trek street prices and Black Friday 2026 buy-now-or-wait calls, plus every Oct–Dec release."
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
if st_set.get("prerelease_verdict"): st_faq.append(("Should I buy a Star Trek prerelease kit?", st_set["prerelease_verdict"]))
st_pre = (f'<div class=card><h3 id="prerelease-kits">Prerelease kits</h3><p><span class=t>Buy / Wait / Skip</span> {E(st_set["prerelease_verdict"])}</p>'
          f'<p><small>Prerelease pack contents and dates per {st_a("collect")}.</small></p>{checked(st_set, with_sources=False)}</div>') if st_set.get("prerelease_verdict") else ""
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
  + st_pre
  + f'<div class=card><h3><a href="{BASE}/p/{st_cmd["slug"]}.html">{E(st_cmd["name"])}</a></h3><p>{vtag(st_cmd)}{E(st_cmd["note"])}</p>' + (f'<p><b>Good gift for:</b> {E(st_cmd["gift_for"])}.</p>' if st_cmd.get("gift_for") else "") + f'{amz_btn(st_cmd)}</div>'
  "<h3>Value at MSRP</h3><p>Simple arithmetic from Wizards' MSRPs, so you can compare the boxes:</p><ul>" + "".join(f"<li><b>{E(a)}:</b> {E(b)}</li>" for a, b in st_math) + "</ul>"
  "<p>If you want to collect the signed cards or the surge foil Booster Fun, that is Collector Booster territory; for drafting or a first taste of the set, Play Boosters, a Bundle or Draft Night are the cheaper way in. Prices in stores often fall after release, so preordering mainly makes sense if you want the product on day one.</p>"
  f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in st_faq)
  + f'<p>More releases: <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a>, the <a href="{BASE}/guides/mtg-2027-release-schedule.html">MTG 2027 release schedule</a>, the <a href="{BASE}/secret-lair.html">Secret Lair drop schedule</a> and the full <a href="{BASE}/">release calendar</a>.</p>'
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
# ---- Guide 3: MTG 2027 release schedule (dates/notes from releases.json; set-count and MagicCon facts from Wizards' Jul 17, 2026 announcement) ----
Y_SRC = "https://magic.wizards.com/en/news/announcements/everything-announced-for-the-magic-multiverse-in-2027"
Y_SLUG = "guides/mtg-2027-release-schedule.html"; y_url = url(Y_SLUG)
Y_TITLE = "MTG 2027 Release Schedule: Every Set & Precon | MTG Drops"
Y_H1 = "MTG 2027 Release Schedule: Every Set and Commander Deck"
Y_PUBLISHED = "2026-10-24"
y_items = [r for r in data if dated(r) and r["release_date"][:4] == "2027"]
y_sets = [r for r in y_items if r["type"] in ("Main Set", "Universes Beyond")]
y_cmd = [r for r in y_items if r["type"] == "Commander Precon"]
y_months = sorted({r["release_date"][:7] for r in y_items})
def y_link(r): return E(r["name"]) if r.get("placeholder") else f'<a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a>'
def y_item(r):
    ps = r.get("prices") or []
    price = "; ".join(f"{p['label']}: {fmt(p)}" for p in ps) if ps else "TBA"
    win = f'<p><b>Also:</b> {E(r["window"])}</p>' if r.get("window") else ""
    return (f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span>{badges(r)}<h3>{y_link(r)}</h3>'
            f'<p><b>Date:</b> {nice_date(r)}</p>{win}<p><b>Price:</b> {E(price)}</p><p>{vtag(r)}{E(r["note"])}</p>{"" if r.get("placeholder") else amz_btn(r)}</div>')
def y_when(r): return f"{short_name(r)} ({nice_date(r)}" + ("" if r["status"] == "confirmed" else f", {r['status']}") + ")"
y_first = y_sets[0] if y_sets else None
y_faq = []
if y_first: y_faq.append(("What is the first MTG set of 2027?", f"{y_first['name']}, releasing {nice_date(y_first)} ({y_first['status']})." + (f" {y_first['window']}." if y_first.get("window") else "")))
y_faq.append(("What MTG sets release in 2027?", "On our calendar: " + "; ".join(y_when(r) for r in y_sets) + ". Wizards says 2027 has three Magic Multiverse sets and three Universes Beyond sets, alternating between the two, so not every 2027 set is announced yet."))
y_faq.append(("Which 2027 MTG sets have Commander decks?", ("Announced so far: " + "; ".join(y_when(r) for r in y_cmd) + ".") if y_cmd else "None announced yet."))
y_pre = [r for r in y_items if r.get("window") and "reorder" in r["window"]]
y_faq.append(("Can you preorder 2027 MTG sets yet?", (("Wizards says preorders are open for " + " and ".join(short_name(r) for r in y_pre) + ". ") if y_pre else "") + "The other 2027 products have no announced preorder details on our calendar yet. None of the 2027 products has a verdict from us yet, because decklists, card previews or prices are still missing."))
y_faq.append(("How many MagicCons are there in 2027?", "Wizards says there will be four MagicCons in 2027, including the first MagicCon in Japan."))
y_body = (f'<nav class=bc aria-label=Breadcrumb><a href="{BASE}/">MTG Drops</a> › <a href="{BASE}/guides/">Guides</a> › 2027 release schedule</nav><h1>{E(Y_H1)}</h1>'
  f'<p class=about><small><b>About MTG Drops:</b> {E(ABOUT)}</small></p>'
  f'<p><b>Last updated:</b> {tdate()} · {len(y_items)} products dated in 2027</p>'
  f'<p>Every Magic: The Gathering product on our calendar for 2027: premier sets, Universes Beyond sets and Commander decks, with release dates, known MSRPs, preorder status and sources. Wizards says 2027 will have <a href="{Y_SRC}">three Magic Multiverse sets and three Universes Beyond sets</a>, alternating between the two, and four MagicCons, including the first one in Japan. Each product page lists its sources, and dates that are not confirmed yet are tagged. For what\'s releasing before then, see <a href="{BASE}/guides/mtg-releases-fall-holiday-2026.html">every MTG product releasing this fall/holiday 2026</a> and the <a href="{BASE}/guides/star-trek-mtg-release-guide.html">Star Trek release guide</a>.</p>'
  "<h2>2027 at a glance</h2><table><tr><th>Date</th><th>Product</th><th>Type</th></tr>" + "".join(f"<tr><td>{nice_date(r)}</td><td>{y_link(r)}</td><td>{E(r['type'])}{'' if r['status'] == 'confirmed' else ' (' + E(r['status']) + ')'}</td></tr>" for r in y_items) + "</table>"
  + "".join(f"<h2>{g_month_name(m)}</h2>" + "".join(y_item(r) for r in y_items if r["release_date"][:7] == m) for m in y_months)
  + "<h2>Should you preorder 2027 sets now?</h2><p>None of the 2027 products has a buy, wait or skip verdict from us yet: card previews, decklists or prices are still missing for each of them. We add a verdict once there's enough to judge, and the weekly email flags it when we do.</p>"
  + f'<p class=disc><small>{E(DISCLOSURE)}</small></p>'
  + "<h2>FAQ</h2>" + "".join(f"<h3>{E(q)}</h3><p>{E(a)}</p>" for q, a in y_faq)
  + f'<p>More releases: the <a href="{BASE}/secret-lair.html">Secret Lair drop schedule</a> and the full <a href="{BASE}/">release calendar</a>.</p>'
  + f"<h2>Get the weekly release email</h2><p>What's Dropping covers what's releasing next, date and price changes, and a buy-or-skip verdict for each product.</p>{FORM}<p><small>Last updated: {tdate()}</small></p>")
Y_DESC = "MTG 2027 release schedule: Nauctis, Darkhold Destiny, Kamigawa: Titanbreach, Zhalfir and their Commander decks, with dates, MSRPs and preorder status."
y_pub = [r for r in y_items if not r.get("placeholder")]
y_ld = [
 {"@context": "https://schema.org", "@type": "Article", "headline": Y_H1, "url": y_url, "mainEntityOfPage": y_url, "image": OG_IMAGE, "datePublished": Y_PUBLISHED, "dateModified": PD,
  "author": {"@id": f"{SITE_URL}/#org"}, "publisher": {"@id": f"{SITE_URL}/#org"}, "isPartOf": {"@id": f"{SITE_URL}/#website"},
  "description": Y_DESC, "citation": [Y_SRC]},
 {"@context": "https://schema.org", **ORG},
 {"@context": "https://schema.org", "@type": "ItemList", "name": "MTG releases in 2027", "numberOfItems": len(y_pub),
  "itemListElement": [{"@type": "ListItem", "position": i+1, "url": f"{SITE_URL}/p/{r['slug']}.html", "name": r["name"]} for i, r in enumerate(y_pub)]},
 {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
   {"@type": "ListItem", "position": 1, "name": "MTG Drops", "item": f"{SITE_URL}/"},
   {"@type": "ListItem", "position": 2, "name": "Guides", "item": f"{SITE_URL}/guides/"},
   {"@type": "ListItem", "position": 3, "name": "MTG 2027 release schedule", "item": y_url}]},
 {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in y_faq]},
]
page(Y_TITLE, Y_DESC, y_body, Y_SLUG, y_ld)
GUIDES = [(G_SLUG, G_H1, "Every Magic product from October to December 2026, grouped by month, with prices, buy/skip verdicts, a dated Star Trek preorder price table, Black Friday buy-now-or-wait calls with dated retailer early-sale windows, holiday gift picks and a week-by-week table of what to buy or preorder in November 2026."),
          (ST_SLUG, ST_H1, "Everything in the Nov 13, 2026 Star Trek set: every product and MSRP, the four Commander decks, key dates, signed cards and what to buy."),
          (Y_SLUG, Y_H1, "Every 2027 MTG set and Commander deck on our calendar: Nauctis, Darkhold Destiny, Titanbreach and Zhalfir, with dates, MSRPs and preorder status.")]
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
# Default: all-day events (DTSTART;VALUE=DATE, DTEND = next day). Set Phasers to Superdrop is the exception:
# timed SALE (Nov 9 9 AM PT) + separate PRE-QUEUE (Nov 9 8 AM PT) as UTC DTSTART/DTEND, no all-day duplicate.
# Stable UIDs (<slug>@mtgdrops.com), DTSTAMP from the entry's last_checked date so an unchanged entry produces
# byte-identical output, CRLF line endings, lines folded at 75 octets. These are calendar events, not schema.org Event.
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
        # Set Phasers: timed sale (9 AM PT) + pre-queue (8 AM PT) as UTC; skip all-day VALUE=DATE for this slug.
        # Nov 9, 2026 is after the Nov 1 DST end, so PT = UTC-8 (9 AM PT = 17:00Z, 8 AM PT = 16:00Z).
        if r["slug"] == "secret-lair-star-trek-set-phasers-superdrop":
            nm = short_name(r)
            dsc = f"{r['type']}. {r['note']} Details: {link}"
            ev.append((r["slug"], "20261109T170000Z", "20261109T180000Z", nm + " sale (9 AM PT)", "Sale opens 9 AM PT on MagicSecretLair.com. " + dsc, link, stamp, True))
            ev.append((r["slug"] + "-prequeue", "20261109T160000Z", "20261109T170000Z", nm + " pre-queue (8 AM PT)", "Pre-queue opens 8 AM PT on MagicSecretLair.com. " + dsc, link, stamp, True))
            continue
        ev.append((r["slug"], d0, d0 + datetime.timedelta(days=1), short_name(r) + flag, f"{r['type']}. {r['note']} Details: {link}", link, stamp, False))
        if r.get("prerelease") == "Nov 6–12, 2026" and r["slug"] == "star-trek":  # prerelease week as its own multi-day event
            ev.append((r["slug"] + "-prerelease", datetime.date(2026, 11, 6), datetime.date(2026, 11, 13), short_name(r) + " prerelease (local game stores)", f"Prerelease events at local game stores, the week before the {nice_date(r)} release (Wizards). Details: {link}", link, stamp, False))
    return ev
def ics(name, desc, rs):
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MTG Drops//Release calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
         "X-WR-CALNAME:" + ics_esc(name), "X-WR-CALDESC:" + ics_esc(desc), "REFRESH-INTERVAL;VALUE=DURATION:P1D", "X-PUBLISHED-TTL:P1D"]
    for uid, a, b, summ, dsc, link, stamp, timed in ics_events(rs):
        if timed:
            L += ["BEGIN:VEVENT", f"UID:{uid}@mtgdrops.com", f"DTSTAMP:{stamp}", f"DTSTART:{a}", f"DTEND:{b}",
                  "SUMMARY:" + ics_esc(summ), "DESCRIPTION:" + ics_esc(dsc), f"URL:{link}", "END:VEVENT"]
        else:
            L += ["BEGIN:VEVENT", f"UID:{uid}@mtgdrops.com", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{a:%Y%m%d}", f"DTEND;VALUE=DATE:{b:%Y%m%d}",
                  "SUMMARY:" + ics_esc(summ), "DESCRIPTION:" + ics_esc(dsc), f"URL:{link}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return b"".join(ics_fold(l) + b"\r\n" for l in L)
open("dist/calendar.ics", "wb").write(ics("MTG Drops: MTG release calendar", "Every upcoming Magic: The Gathering release from mtgdrops.com", data))
open("dist/secret-lair.ics", "wb").write(ics("MTG Drops: Secret Lair drops", "Secret Lair drop dates from mtgdrops.com/secret-lair.html", [r for r in data if r["type"] == "Secret Lair"]))
# Persist page dates (committed). Only pages built this run are kept.
_pd_new = json.dumps(dict(sorted(new_dates.items())), indent=1, sort_keys=True) + "\n"
if not os.path.exists(PAGE_DATES_FILE) or open(PAGE_DATES_FILE).read() != _pd_new: open(PAGE_DATES_FILE, "w").write(_pd_new)
open("dist/robots.txt","w").write(f"User-agent: *\nAllow: /\nContent-Signal: ai-train=no, search=yes, ai-input=yes\nSitemap: {SITE_URL}/sitemap.xml\n")
# GitHub Pages publishes dist as a static artifact and does not run Jekyll. .nojekyll is still
# emitted so a Jekyll build would not drop dot-directories such as .well-known. There is no
# _headers file; Pages cannot set Content-Type or Link response headers.
open("dist/.nojekyll","w").write("")
# Agent Skills Discovery RFC v0.2.0 (https://schemas.agentskills.io/discovery/0.2.0/schema.json).
# llms.txt, the sitemap, and the api-catalog linkset stay where they already are (llms.txt, the
# HTML <link> hints, and /.well-known/api-catalog). This index lists skills only.
# GitHub Pages serves /.well-known/agent-skills/ as this same index.json (the no-slash path 301s
# there). There is no separate extensionless file: the directory name is agent-skills.
AGENT_SKILLS_SCHEMA = "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
WHATS_DROPPING_DESC = ("Find what Magic: The Gathering products are dropping this week on the MTG Drops release calendar, including dates, prices, and buy/skip verdicts. Use when asked what is releasing, what to preorder, or what the calendar says.")
SECRET_LAIR_DESC = ("Read the MTG Drops Secret Lair schedule and separate drops that are on sale now from upcoming and ended ones, with dates, prices, and buy/skip verdicts. Use when asked which Secret Lair is on sale, when a drop goes on sale, or whether a drop is worth buying.")
def agent_skill_md(name, description, body):
    """SKILL.md bytes: YAML frontmatter (name + description) then markdown. Digest is sha256 of these bytes."""
    text = f"---\nname: {name}\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n{body.strip()}\n"
    return text.encode("utf-8")
def write_agent_skill(name, description, body):
    raw = agent_skill_md(name, description, body)
    path = os.path.join("dist/.well-known/agent-skills", name, "SKILL.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(raw)
    return {"name": name, "type": "skill-md", "description": description,
            "url": f"/.well-known/agent-skills/{name}/SKILL.md",
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
whats_dropping_body = f"""# What's dropping this week

MTG Drops ({SITE_URL}/) is an independent Magic: The Gathering release calendar. It lists upcoming sets, Commander precons, Universes Beyond products, and Secret Lair drops, each with a date, known prices, and a short buy/skip verdict. It is not a store, a Discord bot, or an eBay monitor, and it is not affiliated with Wizards of the Coast.

Use this skill to answer what is releasing this week or soon, what a product costs, and whether MTG Drops says to buy, wait, or skip. Read the live pages below. Dates, prices, and verdicts come from those pages.

## Release calendar

Open {SITE_URL}/.

The page is titled "MTG Release Calendar 2026–2027". Under the calendar feed, "Add MTG release dates to Google Calendar" explains how to subscribe calendar.ics in Google Calendar, Apple Calendar, and Outlook. Products are grouped under month headings such as "Nov 2026". A dated product stays under its month heading through its release date. Starting the next day it is listed under "Already released", unless it is marked delayed. Delayed products stay in the upcoming groups. A product whose date is TBA stays under "Date TBA".

There is no "this week" filter and no date-range API. For this week, open the current month and read each card's date. The type buttons (All, and one per product type) only hide cards in a browser. The HTML includes every card.

Each product card shows:

- A type label (for example Main Set, Universes Beyond, Commander Precon, or Secret Lair).
- A status label such as "unconfirmed" when status is not confirmed, plus "sold out" or "delayed" when those flags are set. Delayed means the announced date has passed and stock may arrive after that date.
- The product name. It links to {SITE_URL}/p/{{slug}}.html. A placeholder that has no page yet is plain text, with no product URL.
- The release date, written like "Nov 13, 2026", or "TBA". When a prerelease window is announced, the date line adds "Prerelease" and that window.
- A short note. That note is the buy/skip writeup.
- "Last checked", with source links, when the entry records a check date.

## Product page

On {SITE_URL}/p/{{slug}}.html read:

- The Release line: date, status, and, when present, prerelease, sold out, and delayed.
- The Price section.
- The "Buy or skip?" section. The paragraph there is the verdict. Some products also have a structured verdict of buy, wait, skip, or mixed. Guide pages show that as "Verdict: Buy" (or Wait, Skip, or Mixed). On the calendar card, use the note.

The page links to TCGplayer and sometimes Amazon. Those are affiliate links. See Affiliate disclosure below. MTG Drops does not sell the product.

## Other ways to read the same calendar

- {SITE_URL}/calendar.ics — iCalendar feed of dated releases (all-day events). The event URL is the product page. When a placeholder is included, its event URL is the home page.
- {SITE_URL}/feed.xml — RSS of every product that has a page, upcoming and delayed first, then already released. Each item links to the product page and uses the note as the description.
- {SITE_URL}/llms.txt — curated text overview. The Releases section lists every product that has a page, in that same order. Each line has the date, type, and status, and notes when an item is delayed. The Main pages section links the calendar, guides, newsletter, and feeds.
- {SITE_URL}/guides/mtg-releases-fall-holiday-2026.html#november-2026 — a week-by-week buy/preorder table for November 2026 only, on the fall/holiday guide, with a dated Star Trek preorder price table under that heading (#star-trek-preorder-prices). It is not a general weekly feed. The Black Friday buy-now-or-wait section is {SITE_URL}/guides/mtg-releases-fall-holiday-2026.html#black-friday-2026. That section includes dated retailer early-sale windows (Target Thu Nov 5 – Sat Nov 7, Walmart Nov 12–15 and Nov 23–29, and a line that Amazon has not announced US Black Friday dates yet; last checked Nov 5, 2026). It does not change the published buy/wait/skip calls. Other months on that guide are listed under their own headings. The 2027 schedule is {SITE_URL}/guides/mtg-2027-release-schedule.html.
- {SITE_URL}/newsletter.html — describes the free Monday email "What's Dropping" (US Central time). The signup form posts to Buttondown. There is no newsletter API.

## Asking a question

{SITE_URL}/llms.txt has a Search section. It documents a Context7 ask endpoint. Append `&query=` and the URL-encoded question to the endpoint printed there. The response is documentation that answers the question, with a source link for each part. No API key is needed. If nothing matches, it says so. Treat that as a search over the published pages, not as live store stock or a price feed. When the calendar or a product page disagrees with a paraphrase, use the page.

## What is not published

data/releases.json is build input. It is not served. There is no JSON releases API. The sitemap of public pages is {SITE_URL}/sitemap.xml. The linkset at {SITE_URL}/.well-known/api-catalog points at the same Context7 ask endpoint, with llms.txt as its service doc.

## Affiliate disclosure

Every page states: "{DISCLOSURE}"

Dates come from official and community sources. Verify before buying. Contact: contact@mtgdrops.com.
"""
secret_lair_body = f"""# Secret Lair schedule

Use this skill for Secret Lair questions: what is on sale now, what is upcoming, when a drop goes on sale, what it costs, and the buy/skip verdict. Read the live hub. Dates, prices, and verdicts come from that page.

## Hub page

Open {SITE_URL}/secret-lair.html.

The title and the H1 lead with the next dated sale (name and date). A subtitle under the H1 keeps the schedule framing. If no upcoming sale has a date, the title stays the schedule title.

Under the title, a line counts the three buckets, in the form "N on sale now · N upcoming · N recent / ended".

Then, in this order:

1. "Next Secret Lair drop". This is the next dated Secret Lair sale that is not delayed and not sold out, on or after today. It stays "next" through its sale day. If no such sale has a date, the page says the next drop is TBA.
2. A link to the Secret Lair calendar feed, {SITE_URL}/secret-lair.ics. That file is the feed. The Google, Apple, and download links on the page point at it.
3. "What is Secret Lair and how do drops work?", then "MTG Drops vs Secret Lair GG" (what this calendar covers versus the Secret Lair tracker at secretlair.gg).
4. "On sale now".
5. "Upcoming Secret Lair drops".
6. "Recent / ended".
7. "Secret Lair FAQ", including what is on sale now, what is next, the usual sale time, foil versus non-foil, and print-to-demand. The lists above are the schedule. When a drop's own card is more specific than the general FAQ, use the card.

Each drop card shows:

- The name, linked to {SITE_URL}/p/{{slug}}.html, plus "sold out" or "delayed" when those flags are set.
- Date: one of "On sale since {{date}}" (opened, still in the on-sale window), "On sale {{date}}" (not opened yet), "Went on sale {{date}}", "Went on sale {{date}}; sold out", "Date TBA", or a delayed line ("Delayed: was due {{date}}; Wizards says stock may arrive shortly after").
- Sale details, when that drop has a known window (time, store, end, or quantity). The window on the card overrides the general FAQ line that recent sales open at 9 a.m. PT, with a pre-queue from 8 a.m. PT, at MagicSecretLair.com.
- Price: the prices recorded for that drop. Standard 2026 drops are often $29.99 non-foil and $39.99 foil. Superdrops, bundles, and larger products are priced on their own. Read the card.
- Contents.
- "Our verdict": the buy/skip note for that drop.
- "Last checked", with sources, when a check date is recorded.

The product page repeats the release date and status, the price section, the card list when one is published, and "Buy or skip?".

## How a drop is bucketed

The hub applies these rules in order:

- Delayed: upcoming. A delayed drop is never listed as on sale now. Stock may arrive after the announced date.
- Sold out, and the sale date is today or earlier: recent / ended.
- No numeric date, or the sale date is still in the future: upcoming. TBA is upcoming.
- A known sale end date: on sale now while that end date is today or later; otherwise recent / ended.
- Otherwise (no sale end date): on sale now while the drop opened {SL_ONSALE_DAYS} or fewer days ago, then recent / ended. The hub says drops opened more than {SL_ONSALE_DAYS} days ago are listed as recent / ended unless an end date is known.

Limited print runs can sell out sooner, or stay listed at the store longer, than that window. For current stock, check Wizards' own store, MagicSecretLair.com: {SL_STORE}. MTG Drops does not sell Secret Lair products and does not take orders.

## Same facts elsewhere

{SITE_URL}/llms.txt lists every hub drop under "Secret Lair drops", labeled "on sale now", "upcoming", or "recent/ended", with the date line and price.

{SITE_URL}/secret-lair.ics is an iCalendar feed of Secret Lair drops only.

The home calendar ({SITE_URL}/) also includes Secret Lair cards in the month groups, and a "Next Secret Lair drop" line that links to this hub. For on-sale versus upcoming, use the hub sections.

## Asking a question

The Search section of {SITE_URL}/llms.txt documents the Context7 ask endpoint. Append `&query=` and the URL-encoded question to the endpoint printed there. It returns documentation with a source link for each part. No API key is needed. If nothing matches, it says so. It is not a stock or checkout API. For whether a drop is on sale, read the hub.

## What is not published

There is no JSON API of drops. data/releases.json is build input and is not served.

## Affiliate disclosure

Every page states: "{DISCLOSURE}"

Dates come from official and community sources. Verify before buying. Not affiliated with Wizards of the Coast. Contact: contact@mtgdrops.com.
"""
agent_skills = [
    write_agent_skill("whats-dropping", WHATS_DROPPING_DESC, whats_dropping_body),
    write_agent_skill("secret-lair", SECRET_LAIR_DESC, secret_lair_body),
]
os.makedirs("dist/.well-known/agent-skills", exist_ok=True)
open("dist/.well-known/agent-skills/index.json", "w").write(json.dumps({
    "$schema": AGENT_SKILLS_SCHEMA,
    "skills": agent_skills,
}, indent=2) + "\n")
# Ask URL copied from live https://mtgdrops.com/llms.txt (the &query=<URL-encoded question> suffix there is a template, not part of the endpoint).
open("dist/.well-known/api-catalog","w").write(json.dumps({"linkset": [
 {"anchor": f"{SITE_URL}/.well-known/api-catalog", "item": [
  {"href": CONTEXT7_ASK_URL, "title": "MTG Drops Context7 ask"}]},
 {"anchor": CONTEXT7_ASK_URL, "service-doc": [
  {"href": f"{SITE_URL}/llms.txt", "type": "text/plain", "title": "llms.txt"}]}
]}, indent=2) + "\n")
open("dist/llms.txt","w").write(f"""# MTG Drops

> MTG Drops ({SITE_URL}/) is an independent release calendar for Magic: The Gathering: upcoming sets, Commander precons, Secret Lair drops and Universes Beyond products, each with release dates, known prices, a short buy/skip verdict and a free weekly newsletter. Not affiliated with Wizards of the Coast, and not a Discord bot or eBay monitor (it is unrelated to the "MTG Drop" Discord eBay-monitoring tool). Some links are affiliate links (Amazon Associates, TCGplayer).

## Search

{CONTEXT7_NOTE}

## Main pages
- [Release calendar]({SITE_URL}/): every upcoming MTG product grouped by month, plus how to add calendar.ics to Google Calendar, Apple Calendar, or Outlook
- [Secret Lair drops]({SITE_URL}/secret-lair.html): next drop in the title, schedule (on sale now, upcoming, recent), prices, buy/skip verdicts, and how MTG Drops compares with Secret Lair GG
- [Guides]({SITE_URL}/guides/): release roundups and gift picks
""" + "".join(f"- [{t}]({url(p)}): {d}\n" for p, t, d in GUIDES) + f"""- [Newsletter]({SITE_URL}/newsletter.html): weekly "What's Dropping" email
- [Sponsor]({SITE_URL}/sponsor.html): media kit, sponsorship placements and disclosure policy (contact sponsors@mtgdrops.com)
- [RSS feed]({SITE_URL}/feed.xml)
- [Calendar feed (.ics), every release]({SITE_URL}/calendar.ics) and [Secret Lair only]({SITE_URL}/secret-lair.ics)
- [Sitemap]({SITE_URL}/sitemap.xml)

## Secret Lair drops

""" + SL_LLMS + """
## Releases
""" + "".join(f"- [{r['name']}]({SITE_URL}/p/{r['slug']}.html): {nice_date(r)}, {r['type']}, {r['status']}" + ("; delayed, stock may arrive after this date" if r.get("delayed") else "") + "\n" for r in up if not r.get("placeholder")))
open("dist/CNAME","w").write("mtgdrops.com\n")
print(f"built {len(data)} products")
