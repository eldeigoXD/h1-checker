from curl_cffi import requests
r = requests.get('https://centralmazda.cms.dealer.com/start-online.htm', impersonate='chrome120', timeout=10)
import re
print('accountId (script):', re.findall(r'"accountId"\s*:\s*"([^"]+)"', r.text))
print('data-account-id (html):', re.findall(r'data-account-id=["\']([^"\']+)["\']', r.text))
