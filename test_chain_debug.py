"""Test the rewritten chain hunt algorithm with DEBUG logging."""
import sys, time, json, os
os.environ["PYTHONIOENCODING"] = "utf-8"
import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(message)s")
# Suppress noisy urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)

sys.path.insert(0, "backend")
from scraper import GeMScraper

scraper = GeMScraper()
url = "https://mkp.gem.gov.in/computer-displays-interactive-panels-with-cpu/search#/?q=interactive%20panel"
target = 450000

# Quick scrape for golden filters
data = scraper.scrape(url)
golden = [f for f in data["filters"] if f.get("isGolden")]
print(f"Products: {data['productCount']}, Golden Filters: {len(golden)}")

# Run the chain hunt
print("\n" + "=" * 70)
t0 = time.time()
result = scraper.smart_l1_discovery(
    category_url=url,
    target_price=target,
    golden_filters=golden,
    location=""
)
elapsed = time.time() - t0

print(f"\nDone in {elapsed:.1f}s | API Calls: {result.get('totalApiCalls')}")
print(f"Status: {result.get('status')} | Paths found: {result.get('totalPaths')}")

for i, path in enumerate(result.get("winningPaths", [])[:5]):
    steps = path.get("iterations", [])
    print(f"\n--- Path {i+1} ({len(steps)} steps, chain={path.get('chainLength')}) ---")
    for step in steps:
        fa = step["filterApplied"]
        prev = step.get("prevMinPrice", "?")
        new = step.get("newMinPrice", "?")
        new_str = f"Rs {new:,}" if isinstance(new, int) else str(new)
        prev_str = f"Rs {prev:,}" if isinstance(prev, int) else str(prev)
        print(f"  Step {step['iteration']}: {prev_str} -> {new_str} "
              f"| {fa['filterName']} = {fa['value']} "
              f"| products={step.get('newTotal','?')} sellers={step.get('sellerCount','?')}")

    if path.get("isUntapped"):
        print(f"  RESULT: UNTAPPED NICHE")
    elif path.get("status") == "PARTIAL":
        mp = path.get("nicheMinPrice")
        print(f"  RESULT: STUCK/PARTIAL (Max price reached: Rs {mp:,}), products={path.get('totalProducts')}")
    else:
        mp = path.get("nicheMinPrice")
        print(f"  RESULT: WIN - YOU ARE L1! Next cheapest: Rs {mp:,}, products={path.get('totalProducts')}")
    print(f"  Filters: {path.get('activeFilters')}")
