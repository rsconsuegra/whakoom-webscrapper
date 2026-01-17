"""Scrapper to get all the titles in a list."""

from collections.abc import Iterator
from logging import WARNING
from typing import Any

from scrapy import Selector, Spider
from scrapy.http import Response
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.remote_connection import LOGGER
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from urllib3.connectionpool import log as urllibLogger

# This removes unwanted logs from Selenium process.
LOGGER.setLevel(WARNING)
urllibLogger.setLevel(WARNING)


class PublicationsSpider(Spider):
    """Spider to get all the titles in a list."""

    name = "publications"
    allowed_domains = ["whakoom.com"]
    url_root = "https://www.whakoom.com/deirdre/lists/"
    start_urls = [f"{url_root}titulos_editados_en_espana_publicados_en_la_revista_sho-comi_116039"]

    def __init__(self, *args: Any):
        """Initialize the WebDriver for scraping."""
        super().__init__(*args)
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Ensure GUI is off
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--log-level=3")

        self.driver = webdriver.Chrome(options=chrome_options)

    def parse(self, response: Response) -> Iterator[dict[str, str]]:
        """
        Parse the webpage content after loading it with Selenium.

        Args:
            response (scrapy.http.Response): The initial response object from Scrapy.

        Returns:
            Iterable: An iterable of dictionaries containing
            the title and link (href) of each publication.

        Raises:
            Exception: If an exception is encountered while
            loading the page or clicking the "Load more" button.

        The method first navigates to the URL of the initial response object
        using Selenium's WebDriver.
        It then enters a loop that continuously tries to locate and click
        the "Load more" button, waiting for 10 seconds between each attempt.
        If the button is not found or any other exception occurs, the loop is broken.

        After the loop, the final page source is obtained using Selenium's `page_source` attribute,
        and the WebDriver is closed.

        The parsed page content is then loaded into a `scrapy.Selector` object,
        which is used to extract the titles and links of each publication.

        The extracted data is yielded as an iterable of dictionaries,
        with each dictionary containing the title and href of a publication.
        """
        self.driver.get(response.url)

        while True:
            try:
                # Check if the "Load more" button is present and clickable
                load_more_button = WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.ID, "loadmoreissues")))
                load_more_button.click()

                # Wait for new content to load after clicking the button
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "list__item")))
            except TimeoutException:
                # If the button is not found
                print("Seleniun found no more clickable elements. Had to stop")
                break
            except Exception as e:  # pylint: disable=W0718
                print(f"Seleniun encountered an Exception: {e}")
                print(f"Exception type: {e.__class__.__name__}")
                break

        # Get the final page source and parse it with Scrapy
        page_source = self.driver.page_source
        self.driver.quit()

        response_ = Selector(text=page_source)
        titles = response_.xpath('//span[@class="title"]/a')
        for title in titles:
            link = title.xpath("@href").get()
            title = title.xpath("text()").get()

            # Yield the item
            yield {"title": title, "href": link}
