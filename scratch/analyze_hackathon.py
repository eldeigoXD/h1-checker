import json
from curl_cffi import requests
from bs4 import BeautifulSoup
import re

url = "https://mojix.cms.dealer.com/hackathon.htm"
try:
    r = requests.get(url, impersonate="chrome120", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    
    links = []
    for a in soup.find_all('a', href=True):
        links.append({
            "text": a.get_text(strip=True),
            "href": a['href'],
            "class": a.get('class', [])
        })
        
    print(json.dumps({"status_code": r.status_code, "links": links}, indent=2))
except Exception as e:
    print("Error:", e)
