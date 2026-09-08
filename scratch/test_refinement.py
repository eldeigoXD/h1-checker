import time
from app import get_selenium_driver

def test():
    driver = get_selenium_driver()
    try:
        url = "https://www.motorcitylexusofbakersfield.com/new-inventory/index.htm?make=Lexus"
        print(f"Visiting {url}...")
        driver.get(url)
        print("Waiting 10 seconds for AJAX facets...")
        time.sleep(10)
        
        # Print page source snippet
        print("Page Title:", driver.title)
        
        # Check inputs
        inputs = driver.find_elements('css selector', 'input[name="model"], input[name="model_facet"], [data-facet-name="model"] input')
        print(f"Found {len(inputs)} inputs with default selector.")
        for inp in inputs[:10]:
            print(" - val:", inp.get_attribute('value'), "name:", inp.get_attribute('name'), "type:", inp.get_attribute('type'))
            
        # Check all checkboxes/inputs on the page to see if there are other model fields
        all_inputs = driver.find_elements('css selector', 'input')
        print(f"Found {len(all_inputs)} total inputs on page.")
        model_inputs = []
        for inp in all_inputs:
            name = inp.get_attribute('name') or ''
            id_val = inp.get_attribute('id') or ''
            val = inp.get_attribute('value') or ''
            facet = inp.get_attribute('data-facet-name') or ''
            field = inp.get_attribute('data-field') or ''
            if 'model' in name.lower() or 'model' in id_val.lower() or 'model' in facet.lower() or 'model' in field.lower():
                model_inputs.append(inp)
                print(f" - Candidate: id='{id_val}', name='{name}', val='{val}', facet='{facet}', field='{field}'")
                
    finally:
        driver.quit()

if __name__ == '__main__':
    test()
