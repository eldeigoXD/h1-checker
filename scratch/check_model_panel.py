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
        
        # 1. Print HTML of model panel
        try:
            model_panel = driver.find_element('css selector', '#model')
            print("Model Panel Outer HTML:")
            html = model_panel.get_attribute('outerHTML')
            # Only print first 1000 chars of HTML to avoid console flooding
            print(html[:2000])
        except Exception as e:
            print("Could not find model panel:", e)
            
        # 2. Try to click Model heading to expand it (in case it is collapsed)
        try:
            # Let's search for a span or button or anchor inside '#model' that can be clicked
            trigger = driver.find_element('css selector', '#model .facet-list-group-label')
            print("Clicking Model panel trigger...")
            driver.execute_script("arguments[0].click();", trigger)
            time.sleep(3)
            
            # Print model panel HTML again
            print("Model Panel Outer HTML after click:")
            model_panel = driver.find_element('css selector', '#model')
            html2 = model_panel.get_attribute('outerHTML')
            print(html2[:2000])
        except Exception as e:
            print("Could not click model panel trigger:", e)
            
        # 3. Find inputs after click
        inputs = driver.find_elements('css selector', 'input')
        print(f"Total inputs on page after click: {len(inputs)}")
        for inp in inputs:
            name = inp.get_attribute('name') or ''
            id_val = inp.get_attribute('id') or ''
            val = inp.get_attribute('value') or ''
            if 'model' in name.lower() or 'model' in id_val.lower():
                print(f"Found Input: id='{id_val}', name='{name}', val='{val}'")
                
    finally:
        driver.quit()

if __name__ == '__main__':
    test()
