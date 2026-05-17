import sys
sys.path.insert(0, "backend")
from scraper import GeMScraper

s = GeMScraper()
d = s.scrape("https://mkp.gem.gov.in/furniture-and-furnishings-accommodation-furniture-furniture-revolving-chair-v5-/search")

golden = [f for f in d["filters"] if f.get("isGolden")]
nongolden = [f for f in d["filters"] if not f.get("isGolden") and f.get("values")]

print(f"Golden: {len(golden)}, Non-golden with values: {len(nongolden)}")
print()
print("=== GOLDEN ===")
for f in golden:
    print(f"  {f['filterName']} ({f['filterKey']}): {f['values']}")
print()
print("=== NON-GOLDEN (spec filters with values) ===")
for f in nongolden:
    print(f"  {f['filterName']} ({f['filterKey']}): {f['values'][:8]}")
