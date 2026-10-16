#!/usr/bin/env python3
"""MTG Drops static site builder. Usage: python3 build.py  -> dist/"""
import json, html, os, shutil, urllib.parse, datetime
AFFILIATE_ID = ""  # TCGplayer affiliate/partner id; blank = plain links
SITE_URL = "https://mtgdrops.com"
BASE = ""  # site served at the domain root (mtgdrops.com)
E = html.escape
data = sorted(json.load(open("data/releases.json")), key=lambda r: r["release_date"])
types = sorted({r["type"] for r in data})
CSS = """body{font-family:system-ui,sans-serif;margin:0;background:#0f1115;color:#e8e8ea}a{color:#7cc4ff}
header,footer{padding:1rem;background:#171a21}header a{margin-right:1rem}main{max-width:860px;margin:auto;padding:1rem}
.card{background:#1c2029;border-radius:10px;padding:1rem;margin:.6rem 0}.t{font-size:.75rem;background:#2d3546;padding:2px 8px;border-radius:9px}
.st{font-size:.75rem;color:#f3c26b}.f button{margin:.2rem;padding:.4rem .7rem;border-radius:8px;border:0;background:#2d3546;color:#fff}
.f button.on{background:#3a7bd5}input{padding:.5rem;border-radius:6px;border:0}form button{padding:.5rem 1rem}"""
def tcg(name):
    u = "https://www.tcgplayer.com/search/magic/product?q=" + urllib.parse.quote(name)
    return u + ("&partner=" + urllib.parse.quote(AFFILIATE_ID) if AFFILIATE_ID else "")
def page(title, desc, body, path):
    p = f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name=description content="{E(desc)}"><link rel=canonical href="{SITE_URL}/{path}">
<meta property=og:title content="{E(title)}"><meta property=og:description content="{E(desc)}"><meta property=og:type content=website>
<link rel=alternate type=application/rss+xml href="{BASE}/feed.xml" title="MTG Drops"><meta name='impact-site-verification' value='78f2b2fa-0831-48d2-a460-e2e3fa5a4eab'><link rel=stylesheet href="{BASE}/style.css"></head><body>
<header><a href="{BASE}/"><b>MTG Drops</b></a><a href="{BASE}/newsletter.html">Newsletter</a><a href="{BASE}/sponsor.html">Sponsor</a><a href="{BASE}/feed.xml">RSS</a></header>
<main>{body}</main><footer><small>Dates from official/community sources; verify before buying. TCGplayer links may be affiliate links. Not affiliated with Wizards of the Coast.</small></footer></body></html>"""
    out = os.path.join("dist", path); os.makedirs(os.path.dirname(out), exist_ok=True); open(out, "w").write(p)
def card(r):
    st = "" if r["status"] == "confirmed" else f' <span class=st>{E(r["status"])}</span>'
    return f'<div class=card data-type="{E(r["type"])}"><span class=t>{E(r["type"])}</span>{st}<h3><a href="{BASE}/p/{r["slug"]}.html">{E(r["name"])}</a></h3><div>{r["release_date"]}</div><p>{E(r["note"])}</p></div>'
FORM = '<form action="https://buttondown.com/api/emails/embed-subscribe/alehpineda.dropdesk" method="post" target="popupwindow"><input type=email name=email required placeholder="you@example.com"> <button>Get What\'s Dropping</button></form>'
shutil.rmtree("dist", ignore_errors=True); os.makedirs("dist/p")
open("dist/style.css", "w").write(CSS)
today = datetime.date.today().isoformat()
up = [r for r in data if r["release_date"] >= today] + [r for r in data if r["release_date"] < today]
btns = '<button class=on data-f="">All</button>' + "".join(f'<button data-f="{E(t)}">{E(t)}</button>' for t in types)
js = "<script>document.querySelectorAll('.f button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.f button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.card').forEach(c=>c.style.display=!b.dataset.f||c.dataset.type==b.dataset.f?'':'none')})</script>"
page("MTG Drops — Every upcoming MTG release, one calendar", "Upcoming Magic: The Gathering sets, Commander precons, Secret Lairs and Universes Beyond with buy/skip notes.",
     f"<h1>What's dropping in Magic</h1><p>Every upcoming MTG product, with a short buy/skip note.</p>{FORM}<div class=f>{btns}</div>" + "".join(card(r) for r in up) + js, "index.html")
for r in data:
    win = f"<p><b>Window:</b> {E(r['window'])}</p>" if r.get("window") else ""
    page(f"{r['name']} — release date & buy/skip | MTG Drops", r["note"][:155],
         f'<p><a href="{BASE}/">← Calendar</a></p><span class=t>{E(r["type"])}</span><h1>{E(r["name"])}</h1><p><b>Release:</b> {r["release_date"]} ({E(r["status"])})</p>{win}<h2>Buy or skip?</h2><p>{E(r["note"])}</p><p><a href="{tcg(r["name"])}" rel="sponsored nofollow">Check prices on TCGplayer</a></p><p><small>Source: <a href="{E(r["source"])}">{E(r["source"])}</a></small></p>{FORM}',
         f"p/{r['slug']}.html")
page("What's Dropping newsletter | MTG Drops", "Weekly MTG release newsletter.", f"<h1>What's Dropping</h1><p>One email a week: what releases, what's on preorder, buy or skip.</p>{FORM}", "newsletter.html")
page("Sponsor MTG Drops", "Sponsor the MTG Drops MTG release calendar and newsletter.", "<h1>Sponsor MTG Drops</h1><p>Reach Magic players planning their next purchase: calendar placements and the weekly What's Dropping newsletter.</p><ul><li>Newsletter top slot (weekly)</li><li>Featured calendar card</li><li>Product-page sponsor</li></ul><p>Contact: sponsors@mtgdrops.com (placeholder)</p>", "sponsor.html")
items = "".join(f"<item><title>{E(r['name'])} — {r['release_date']}</title><link>{SITE_URL}/p/{r['slug']}.html</link><guid>{SITE_URL}/p/{r['slug']}.html</guid><description>{E(r['note'])}</description></item>" for r in up)
open("dist/feed.xml", "w").write(f'<?xml version="1.0"?><rss version="2.0"><channel><title>MTG Drops</title><link>{SITE_URL}/</link><description>Upcoming MTG releases</description>{items}</channel></rss>')
open("dist/sitemap.xml","w").write('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+"".join(f"<url><loc>{SITE_URL}/{p}</loc></url>" for p in ["","newsletter.html","sponsor.html"]+[f"p/{r['slug']}.html" for r in data])+"</urlset>")
open("dist/robots.txt","w").write(f"User-agent: *\nSitemap: {SITE_URL}/sitemap.xml\n")
open("dist/CNAME","w").write("mtgdrops.com\n")
print(f"built {len(data)} products")
