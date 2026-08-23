import re
from bs4 import BeautifulSoup as BS

raw_source = """<div class="facet-filters d-flex align-items-baseline flex-wrap flex-nowrap-lg"><div class="d-lg-flex align-items-baseline"><ul class="facet-filter-list mb-0 list-inline"><li class="my-1"><strong class="d-inline-block flex-shrink-0 mr-3" role="status" aria-live="polite"><span class="d-sm-none">8 Vehicles</span><span class="d-none d-sm-inline">8 Vehicles</span></strong></li><li class="my-1 d-none d-lg-inline-block"></li><li class="my-1 d-none d-lg-inline-block"></li></ul></div><div class="ml-auto d-lg-none"><button type="button" id="show-filters-modal-button" class="btn btn-default btn-block ddc-font-size-large font-weight-bold"><i class="ddc-icon ddc-icon-filter-list-controls"></i> Filter / Sort </button></div><div class="ml-auto flex-shrink-0 d-none d-lg-block"><label for="sortBy" class="sr-only">Sort by</label><select id="sortBy" class="form-control font-size-ios-zoom-override"><option value="">Sort by</option><option value="year asc">Year: Old to New</option><option value="year desc">Year: New To Old</option><option value="normalBodyStyle asc">Bodystyle: A to Z</option><option value="normalBodyStyle desc">Bodystyle: Z to A</option><option value="normalExteriorColor asc">Color: A to Z</option><option value="normalExteriorColor desc">Color: Z to A</option><option value="odometer asc">Mileage: Low to High</option><option value="odometer desc">Mileage: High to Low</option><option value="internetPrice asc">Price: Low to High</option><option value="internetPrice desc">Price: High to Low</option></select><span class="sr-only" role="status" aria-live="polite"></span></div></div>"""

patterns = [
    r'(?<!\$)\b([\d,]+)\s*(?:Veh[íi]culos?|Vehicles?|Results?|Matches?|Matching)\b(?!\s*miles?)',
    r'\b(?:Showing|Found|Displaying)\s+([\d,]+)\b'
]
temp_soup = BS(raw_source, 'html.parser')
full_html_text = temp_soup.get_text(separator=' ', strip=True)

print('Extracted text:', full_html_text)

matched = False
for p in patterns:
    m = re.search(p, full_html_text, re.IGNORECASE)
    if m:
        print('Matched BS4:', m.group(1))
        matched = True
        break

if not matched:
    print('Failed BS4!')
    
raw_patterns = [
    r'([\d,]+)(?:&nbsp;|\s|<[^>]+>)*(?:Vehicles?|Results?|Matches?|Matching|Veh[íi]culos?)',
    r'(?:Showing|Found|Displaying)(?:&nbsp;|\s|<[^>]+>)*([\d,]+)'
]
for rp in raw_patterns:
    m = re.search(rp, raw_source, re.IGNORECASE)
    if m:
        print('Matched Raw HTML:', m.group(1))
        break
