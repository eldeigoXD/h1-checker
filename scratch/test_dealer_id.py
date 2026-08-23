import sys, os, re
sys.path.insert(0, os.getcwd())

# Use the session approach from app.py
from curl_cffi import requests as cffi_requests

session = cffi_requests.Session()
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# First visit root to get cookies
session.get('https://www.maxfordrichmond.com/', impersonate='chrome120', timeout=15)

r = session.get('https://www.maxfordrichmond.com/new-inventory/expedition-suv-richmond-missouri.htm', 
    impersonate='chrome120', timeout=15)
print('Status:', r.status_code)

if r.status_code == 200:
    html = r.text
    
    # Find dealer IDs from pictures.dealer.com paths
    ids = re.findall(r'pictures\.dealer\.com/m/([^/"\'&\s]+)/', html)
    print('IDs from pictures.dealer.com:', list(set(ids))[:5])
    
    # data-account-id
    accs = re.findall(r'data-account-id=["\']([^"\']+)["\']', html)
    print('data-account-id:', list(set(accs))[:5])

    # accountId in scripts  
    accs2 = re.findall(r'"accountId"\s*:\s*"([^"]+)"', html)
    print('accountId in scripts:', list(set(accs2))[:5])
    
    # DDC standard account pattern
    accs3 = re.findall(r'accountId%22%3A%22([^%"]+)', html)
    print('URL-encoded accountId:', list(set(accs3))[:5])
    
    # Generic ddc account
    for pat in [r'ddc[_\-]?account[_\-]?id["\s:=\']+([a-z0-9\-_]{5,40})', 
                r'["\']accountId["\']\s*:\s*["\']([a-z0-9\-_]{5,40})["\']',
                r'account_id\s*=\s*["\']([a-z0-9\-_]{5,40})["\']']:
        found = re.findall(pat, html, re.IGNORECASE)
        if found:
            print(f'Pattern {pat[:30]}... found:', list(set(found))[:3])
    
    # Save HTML excerpt for manual inspection
    with open('scratch/page_sample.html', 'w', encoding='utf-8') as f:
        f.write(html[:50000])
    print('Saved first 50k chars to scratch/page_sample.html')
else:
    print('Could not fetch page, status:', r.status_code)
