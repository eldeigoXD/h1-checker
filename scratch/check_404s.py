import json
from curl_cffi import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

url = "https://mojix.cms.dealer.com/hackathon.htm"
try:
    r = requests.get(url, impersonate="chrome120", timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    
    links = set()
    for a in soup.find_all('a', href=True):
        links.add(a['href'])
    
    results = {}
    for href in links:
        if href.startswith(('tel:', 'mailto:', '#', 'javascript:')):
            continue
        full_url = urljoin(url, href)
        try:
            res = requests.head(full_url, impersonate="chrome120", timeout=5, allow_redirects=True)
            results[href] = res.status_code
        except Exception as e:
            results[href] = str(e)
            
    print(json.dumps(results, indent=2))
except Exception as e:
    print("Error:", e)
