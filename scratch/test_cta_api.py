import json
from curl_cffi import requests

payload = {
    "url": "https://mojix.cms.dealer.com/hackathon.htm"
}
r = requests.post("http://127.0.0.1:5000/api/extract-h1", json=payload, timeout=120)
data = r.json()

if data.get('bugs'):
    for b in data['bugs']:
        if b.get('category') in ['Link', 'Config']:
            print(f"[{b['type']}] {b['category']}: {b['message']}")
else:
    print("No bugs returned or failed.")
    print(r.text)
