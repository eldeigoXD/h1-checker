import urllib3; urllib3.disable_warnings()
from app import validate_inventory, get_selenium_driver
import json

url = 'https://www.capitalcitykia.com/new-inventory/kia-carnival-hybrid-concord-nh.htm'
nav_links = [
    {"text": "New Inventory", "href": "/new-inventory/index.htm"},
    {"text": "Used Inventory", "href": "/used-inventory/index.htm"}
]

# We need a real initial_html to simulate the new logic
import requests as real_requests # using real requests for simplicity in test if curl_cffi is being weird
try:
    from curl_cffi import requests
    resp = requests.get(url, impersonate="chrome120", timeout=30)
    initial_html = resp.text
except Exception as e:
    print(f"Fetch failed: {e}")
    initial_html = None

print("Starting validate_inventory...")
try:
    bugs, info = validate_inventory(url, nav_links, initial_html)
    print("Success!")
    print(json.dumps(info, indent=2))
except Exception as e:
    import traceback
    print("FAILED with exception:")
    traceback.print_exc()
