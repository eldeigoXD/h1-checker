import time
from app import get_selenium_driver
from bs4 import BeautifulSoup

def test():
    driver = get_selenium_driver()
    try:
        url = "https://www.motorcitylexusofbakersfield.com/new-inventory/index.htm?make=Lexus"
        print(f"Visiting {url}...")
        driver.get(url)
        print("Waiting 10 seconds for AJAX facets...")
        time.sleep(10)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # 1. Look for any element containing the model names
        # Let's search for "IS" or "IS 350" or "IS350"
        print("Searching for 'IS 350' in elements:")
        for el in soup.find_all(lambda tag: tag.string and 'IS 350' in tag.string):
            print(f"Found tag: <{el.name} class='{el.get('class', [])}'> {el.string[:100]}")
            
        print("\nSearching for 'RX 350' in elements:")
        for el in soup.find_all(lambda tag: tag.string and 'RX 350' in tag.string)[:5]:
            print(f"Found tag: <{el.name} class='{el.get('class', [])}'> {el.string[:100]}")
            
        # 2. Print any element with class containing 'facet' or 'filter'
        print("\nElements with class/id containing 'facet' or 'filter':")
        for el in soup.find_all(class_=True):
            cls_str = " ".join(el.get('class', []))
            if 'facet' in cls_str.lower() or 'filter' in cls_str.lower():
                print(f" - <{el.name} class='{cls_str}' id='{el.get('id', '')}'>")
                # print first few children or text
                text = el.get_text(strip=True)
                if text:
                    print(f"   Text: {text[:150]}")
                    
        # 3. Print any element with data- attributes
        print("\nElements with data- attributes containing facet or filter:")
        for el in soup.find_all(attrs=True):
            for attr, val in el.attrs.items():
                if attr.startswith('data-') and ('facet' in str(val).lower() or 'filter' in str(val).lower() or 'model' in str(val).lower()):
                    print(f" - <{el.name} {attr}='{val}'>")
                    
    finally:
        driver.quit()

if __name__ == '__main__':
    test()
