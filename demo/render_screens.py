"""Render text files to PNG terminal screenshots with headless Chromium.
Usage: python3 render_screens.py OUT_DIR TITLE=FILE ...   (CHROME env overrides the binary)"""
import html, os, subprocess, sys, tempfile

PAGE = """<!doctype html><meta charset=utf-8><body style="margin:0;background:#0f1419">
<div style="width:1180px;box-sizing:border-box;padding:0;font:15px/1.45 'DejaVu Sans Mono',monospace;color:#d6dbe0">
<div style="background:#1b2430;padding:9px 16px;color:#8a97a6;font-size:13px">{title}</div>
<pre style="margin:0;padding:16px 20px;white-space:pre-wrap;word-break:break-word">{body}</pre></div>"""

def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    chrome = os.environ.get("CHROME", "chromium")
    for spec in sys.argv[2:]:
        title, path = spec.split("=", 1)
        body = open(path, encoding="utf-8").read().rstrip("\n")
        body = "\n".join(html.escape(l) for l in body.split("\n"))
        height = 70 + 22 * (body.count("\n") + 2 + sum(len(l) // 120 for l in body.split("\n")))
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p.html")
            open(f, "w", encoding="utf-8").write(PAGE.format(title=html.escape(title), body=body))
            png = os.path.join(out, os.path.splitext(os.path.basename(path))[0] + ".png")
            subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", f"--window-size=1180,{height}",
                            f"--screenshot={png}", "file://" + f], check=True, capture_output=True)
            print(png)

if __name__ == "__main__":
    main()
