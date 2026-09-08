from urllib.parse import urlparse, urljoin

_NEW_KWS  = ['/new-', '/new/', '/shop/new', '/new-inventory', '/new-models', '/new-cars', '/new-vehicles', '/nuevos-']
_USED_KWS = ['/used-', '/used/', '/pre-owned', '/preowned', '/used-inventory', '/usados-', '/bargain-']
_CERT_KWS = ['/certified', '/cpo']
_ALL_KWS  = ['/all-', '/inventory/all', '/total-inventory']
_GEN_KWS  = ['/dealership/', '/serving-', '/about-', '/directions', '/compare/', '/research/', '/about/', '/areas-we-serve']

def test_inference(url):
    parsed = urlparse(url)
    domain = parsed.netloc
    path = parsed.path.lower()
    
    is_new  = any(k in path for k in _NEW_KWS)
    is_used = any(k in path for k in _USED_KWS)
    is_cert = any(k in path for k in _CERT_KWS)
    is_all  = any(k in path for k in _ALL_KWS) or (is_new and is_used)
    is_gen  = any(k in path for k in _GEN_KWS)
    
    print(f"Path: {path}")
    print(f"is_new: {is_new}, is_used: {is_used}, is_all: {is_all}, is_gen: {is_gen}")
    
    all_inv_path = '/all-inventory/index.htm'
    
    if is_all:
        base_path = all_inv_path
        print(f"Base Path: {base_path}")
        return f"https://{domain}{base_path}"
    
    return None

url = "https://www.helmsmotor.com/all-inventory/index.htm?_ddcpreview=3283d1eb427644c58953c81f91d4ee7d&_toggleBasePageCache=false"
res = test_inference(url)
print(f"Result: {res}")
