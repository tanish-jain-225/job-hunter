import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
app_path = ROOT / "app.py"

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Find the string HTML_TEMPLATE = """ ... """
match = re.search(r'HTML_TEMPLATE = """(.*?)"""', content, re.DOTALL)
if match:
    html_content = match.group(1)
    out_path = ROOT / "scratch" / "index_original.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out:
        out.write(html_content)
    print("Successfully extracted HTML_TEMPLATE to scratch/index_original.html")
else:
    print("Could not find HTML_TEMPLATE in app.py")
