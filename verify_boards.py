import concurrent.futures
import requests
import yaml
from jobhunt.fetch import REGISTERED_ATS

with open("companies.yaml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

companies = data.get("companies", [])
print(f"Auditing all {len(companies)} company career boards live against public ATS APIs...")


def check_company(c):
    ats = c.get("ats", "").lower()
    slug = c.get("slug")
    if ats not in REGISTERED_ATS:
        return (c, False, "Unknown ATS")
    tpl, _ = REGISTERED_ATS[ats]
    url = tpl.format(slug=slug)
    try:
        r = requests.get(url, timeout=7, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if r.status_code == 200:
            # check if it actually has content or empty json
            return (c, True, 200)
        return (c, False, r.status_code)
    except Exception as e:
        return (c, False, str(e)[:30])


valid = []
invalid = []

with concurrent.futures.ThreadPoolExecutor(max_workers=35) as executor:
    results = list(executor.map(check_company, companies))
    for c, ok, status in results:
        if ok:
            valid.append((c, status))
        else:
            invalid.append((c, status))

print("\n=======================================================")
print(f"AUDIT RESULTS: {len(valid)} VERIFIED LIVE (HTTP 200 OK), {len(invalid)} UNREACHABLE/NON-200")
print("=======================================================\n")

if invalid:
    print(f"Non-200 entries ({len(invalid)}):")
    for c, status in invalid:
        print(f"  - {{ats: {c.get('ats')}, slug: {c.get('slug')}, name: {c.get('name')}}} -> {status}")

