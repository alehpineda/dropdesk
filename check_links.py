import re,os,sys,posixpath
BASE="/dropdesk"
bad=0
for d,_,fs in os.walk("dist"):
  for f in fs:
    if not f.endswith(".html"): continue
    src=os.path.join(d,f); rel=os.path.relpath(src,"dist")
    for h in re.findall(r'(?:href|src)="([^"]*)"',open(src).read()):
      h=h.split("#")[0].split("?")[0]
      if not h or re.match(r'^[a-z]+:',h) or h.startswith("//"): continue
      if h.startswith("/"):
        if not (h==BASE or h.startswith(BASE+"/")): print("BROKEN (outside prefix)",rel,h); bad+=1; continue
        t=h[len(BASE):].lstrip("/")
      else:
        t=posixpath.normpath(posixpath.join(posixpath.dirname(rel),h))+("/" if h.endswith("/") else "")
      p=os.path.join("dist",t)
      if t=="" or t.endswith("/") or os.path.isdir(p): p=os.path.join(p,"index.html")
      if not os.path.exists(p): print("BROKEN",rel,h); bad+=1
print("broken:",bad); sys.exit(bad>0)
