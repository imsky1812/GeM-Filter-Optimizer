import requests
import json
import time

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

url = "https://mkp.gem.gov.in/furniture-and-furnishings-accommodation-furniture-furniture-revolving-chair-v5-/search?page=1&format=json"

try:
    print(f"Fetching {url}...")
    r = session.get(url, timeout=15)
    data = r.json()
    
    facets = data.get("facets", {})
    admin = facets.get("administrative", {}).get("facet_list", [])
    print("Administrative Facets:")
    for f in admin:
        print(f" - {f.get('name')} (code: {f.get('code')})")
        
    products = data.get("results", [])
    print(f"Products returned: {len(products)}")
    if products:
        p = products[0]
        print("\nFirst Product Keys:", list(p.keys()))
        dump_str = json.dumps(p).lower()
        print(f"Contains 'mse': {'mse' in dump_str}")
        print(f"Contains 'make in india': {'make in india' in dump_str}")
        
        # Check specific fields
        for field in ['make_in_india', 'mse', 'startup', 'is_mse', 'is_mii']:
            if field in p:
                print(f"Found {field}: {p[field]}")
        
        if 'seller' in p:
            print("Seller obj keys:", p['seller'].keys())
except Exception as e:
    print(f"Error: {e}")
