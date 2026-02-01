"""Spider to get all the titles in a list."""

from collections.abc import Iterator
from typing import Any

from scrapy import Request, Selector, Spider
from scrapy.http import Response
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from whakoom_webscrapper.models import TitlesItem


class PublicationsSpider(Spider):
    """Spider to get all the titles in a list."""

    name = "publications"
    allowed_domains = ["whakoom.com"]

    def __init__(self, *args: Any, mode: str = "pending", **kwargs: Any) -> None:
        """Initialize the WebDriver for scraping and set processing mode.

        Args:
            *args: Variable length argument list.
            mode (str): Processing mode - 'pending' for only pending lists,
                        'all' for full rebuild. Default: 'pending'.
            **kwargs: Arbitrary keyword arguments.
        """
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.driver: webdriver.Chrome | None = None

    def _init_driver(self) -> webdriver.Chrome:
        """Initialize and return Chrome WebDriver with proper options.

        Returns:
            webdriver.Chrome: The initialized Chrome WebDriver instance.
        """
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--log-level=3")

        return webdriver.Chrome(options=chrome_options)

    def parse(self, response: Response) -> Iterator:
        """Parse response from URL.

        Args:
            response (Response): _description_

        Yields:
            Iterator: _description_
        """
        list_xpath = '//*[@id="list"]/h1/'

        user_profile = response.xpath('//*[@id="list"]/div[1]/p[2]/span[1]/strong/a/text()').get()
        list_name = response.xpath(f"{list_xpath}span/text()").get()
        list_amount = response.xpath(f"{list_xpath}small/text()").get()

        self.logger.info(f"Scraping list '{list_name}' by user '{user_profile}' with {list_amount}.")

        # Initialize driver if not already initialized
        if self.driver is None:
            self.driver = self._init_driver()
            self.logger.info("ChromeDriver initialized successfully")
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
                self.logger.info("Selenium found no more clickable elements. Stopping pagination")
                break
            except Exception as e:  # pylint: disable=W0718
                self.logger.error(
                    "Selenium encountered an Exception: %s (%s)",
                    e,
                    e.__class__.__name__,
                )
                break

        # Get the final page source and parse it with Scrapy
        page_source = self.driver.page_source
        self.driver.quit()
        self.driver = None

        response_ = Selector(text=page_source)
        titles = response_.xpath('//span[@class="title"]/a')

        for idx, title in enumerate(titles, start=1):
            title_name = title.get()
            item_url = title.attrib.get("href", "")

            yield Request(
                url=f"www.whakoom.com{item_url}", meta={"title_name": title_name, "id": idx}, callback=self.parse_title
            )

    def parse_title(self, response: Response) -> Iterator:
        """Parse subresponse.

        Args:
            response (Response): _description_

        Yields:
            Iterator: _description_
        """
        title_name = response.meta["title_name"]
        title_id = response.meta["id"]
        title_url = response.xpath('//*[@id="content"]/div/div/p[1]/a').attrib.get("href", "")

        yield TitlesItem(title_id=title_id, title=title_name, title_url=title_url, scrape_status="pending")
