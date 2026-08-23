from curl_cffi import requests
import sys

url = "https://www.helmsmotor.com/all-inventory/index.htm?_ddcpreview=3283d1eb427644c58953c81f91d4ee7d&_toggleBasePageCache=false"
try:
    print(f"Fetching {url}...")
    resp = requests.get(url, impersonate="chrome", timeout=30, verify=False)
    print(f"Status: {resp.status_code}")
    print(f"Content length: {len(resp.text)}")
    if resp.status_code >= 400:
        print("Response text snippet:")
        print(resp.text[:500])
except Exception as e:
    print(f"Error: {e}")
