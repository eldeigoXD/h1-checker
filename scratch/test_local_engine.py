import sys
import os
sys.path.append(os.getcwd())

import app
from app import local_inventory_inference

# Manually inspect LOCAL_MODELS
print(f"LOCAL_MODELS keys: {list(app.LOCAL_MODELS.keys())[:20]}")
print(f"Is 'bronco' in models? {'bronco' in app.LOCAL_MODELS}")

url = "https://www.cioccafordquakertown.com/2026-ford-bronco.htm"
html = "<html><title>2026 Ford Bronco</title><body></body></html>"

print(f"Testing URL: {url}")
res = local_inventory_inference(url, html)
print(f"Final Result: {res}")
