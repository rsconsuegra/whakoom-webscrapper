import scrapy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class ShoComiSpider(scrapy.Spider):
    name = 'sho_comi'
    allowed_domains = ['whakoom.com']
    start_urls = ['https://www.whakoom.com/deirdre/lists/titulos_editados_en_espana_publicados_en_la_revista_sho-comi_116039']

    def __init__(self, *args, **kwargs):
        super(ShoComiSpider, self).__init__(*args, **kwargs)
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Ensure GUI is off
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(options=chrome_options)

    def parse(self, response):
        self.driver.get(response.url)

        while True:
            try:
                # Check if the "Load more" button is present and clickable
                load_more_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "loadmoreissues"))
                )
                load_more_button.click()
                
                # Wait for new content to load after clicking the button
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "list__item"))
                )
            except Exception as e:
                # If the button is not found or any other exception, break the loop
                print(f"Exception encountered: {e}")
                break

        # Get the final page source and parse it with Scrapy
        page_source = self.driver.page_source
        self.driver.quit()

        response = scrapy.Selector(text=page_source)
        titles = response.xpath('//span[@class="title"]/a')
        for title in titles:
            link = title.xpath('@href').get()
            title = title.xpath('text()').get()
            
            # Yield the item
            yield {
                'title': title,
                'href': link
            }
        