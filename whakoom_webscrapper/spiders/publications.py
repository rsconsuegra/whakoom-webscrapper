"""Spider to get all the titles in a list."""

from collections.abc import Iterator
from typing import Any
from logging import WARNING

from scrapy import Request, Selector, Spider
from scrapy.http import Response
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.remote_connection import LOGGER

from pathlib import Path

from whakoom_webscrapper.models import TitlesItem, TitlesListItem
from whakoom_webscrapper.sqlmanager import SQLManager

from urllib3.connectionpool import log as urllibLogger

# This removes unwanted logs from Selenium process.
LOGGER.setLevel(WARNING)
urllibLogger.setLevel(WARNING)


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

        db_path = Path(__file__).parent.parent.parent / "databases" / "publications.db"
        queries_dir = Path(__file__).parent.parent / "queries"
        migrations_dir = Path(__file__).parent.parent / "migrations"

        self.sql_manager = SQLManager(
            db_path=str(db_path),
            sql_dir=str(queries_dir),
            migrations_dir=str(migrations_dir),
        )

        self.processed_list_ids: set[int] = set()

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

    def _get_lists_to_process(self) -> list[dict[str, Any]]:
        """Get lists from database based on mode.

        Returns:
            list: List of dictionaries with list data.
        """
        if self.mode == "pending":
            results = self.sql_manager.execute_parametrized_query(
                "GET_LISTS_FOR_PROCESSING", ("pending",)
            )
        else:
            results = self.sql_manager.execute_parametrized_query("GET_ALL_LISTS", ())

        column_names = [
            "id",
            "list_id",
            "title",
            "url",
            "user_profile",
            "scrape_status",
            "scraped_at",
        ]
        return [dict(zip(column_names, row)) for row in results]

    def start_requests(self) -> Iterator[Request]:
        """Generate requests for lists from database.

        Yields:
            Iterator: Requests to list pages.
        """
        lists_to_process = self._get_lists_to_process()

        for list_data in lists_to_process:
            list_id = list_data["list_id"]
            url = list_data["url"]

            if not url.startswith(("http://", "https://")):
                if url.startswith("/"):
                    url = f"https://www.whakoom.com{url}"
                else:
                    url = f"https://{url}"

            yield Request(
                url=url,
                meta={
                    "list_id": list_id,
                    "list_url": url,
                    "db_id": list_data["id"],
                },
                callback=self.parse_list,
                errback=self.errback_list,
            )

    def parse_list(self, response: Response) -> Iterator:
        """Parse list page and extract volume links.

        Args:
            response (Response): The response object.

        Yields:
            Iterator: Requests to volume pages.
        """
        list_xpath = '//*[@id="list"]/h1/'

        user_profile = response.xpath(
            '//*[@id="list"]/div[1]/p[2]/span[1]/strong/a/text()'
        ).get()
        list_name = response.xpath(f"{list_xpath}span/text()").get()
        list_amount = response.xpath(f"{list_xpath}small/text()").get()

        self.logger.info(
            f"Scraping list '{list_name}' by user '{user_profile}' with {list_amount}."
        )

        db_list_id = response.meta["db_id"]
        whakoom_list_id = response.meta["list_id"]

        self.sql_manager.update_single_field(
            "lists", "id", db_list_id, "scrape_status", "in_progress"
        )

        if self.driver is None:
            self.driver = self._init_driver()
            self.logger.info(
                "ChromeDriver initialized successfully. Loading url. %s", response.url
            )
        self.driver.get(response.url)

        while True:
            try:
                load_more_button = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "loadmoreissues"))
                )
                load_more_button.click()

                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "list__item"))
                )
            except TimeoutException:
                self.logger.info(
                    "Selenium found no more clickable elements. Stopping pagination"
                )
                break
            except Exception as e:
                self.logger.error(
                    "Selenium encountered an Exception: %s (%s)",
                    e,
                    e.__class__.__name__,
                )
                break

        page_source = self.driver.page_source
        self.driver.quit()
        self.driver = None

        response_ = Selector(text=page_source)
        titles = response_.xpath('//span[@class="title"]/a')

        for idx, title in enumerate(titles, start=1):
            volume_name = title.xpath("text()").get()
            volume_url = title.attrib.get("href", "")

            yield Request(
                url=f"https://www.whakoom.com{volume_url}",
                meta={
                    "volume_url": volume_url,
                    "volume_name": volume_name,
                    "list_id": whakoom_list_id,
                    "db_list_id": db_list_id,
                    "position": idx,
                },
                callback=self.parse_volume_page,
                errback=self.errback_volume_page,
            )

    def _is_single_volume_redirect(self, request: str, response: Response) -> bool:
        """Check if request was redirected from /comics/ to /ediciones/.

        Args:
            request: The original request string.
            response: The response object.

        Returns:
            True if redirected from /comics/ to /ediciones/, False otherwise.
        """
        if request == response.url:
            return False

        request_path = (
            request.split("whakoom.com")[-1]
            if "whakoom.com" in request
            else request
        )
        response_path = (
            response.url.split("whakoom.com")[-1]
            if "whakoom.com" in response.url
            else response.url
        )

        return request_path.startswith("/comics/") and response_path.startswith(
            "/ediciones/"
        )

    def parse_volume_page(self, response: Response) -> Iterator:
        """Parse volume page to extract title information.

        Args:
            response (Response): The response object.

        Yields:
            Iterator: Items for titles and list-title relationships.
        """
        request = response.meta["redirect_urls"][0] if response.meta.get("redirect_urls") else ""

        volume_name = response.meta["volume_name"]
        whakoom_list_id = response.meta["list_id"]
        db_list_id = response.meta["db_list_id"]
        position = response.meta["position"]

        is_single_volume = self._is_single_volume_redirect(request, response)

        if is_single_volume:
            self.logger.info(
                "Detected single volume redirect from %s to %s",
                request,
                response.url,
            )
            title_id = self._extract_title_id_from_url(response.url)
            title_url = response.url
        else:
            title_url = response.xpath('//*[@id="content"]/div/div/p[1]/a').attrib.get(
                "href", ""
            )
            title_id = self._extract_title_id_from_url(title_url)

        try:
            yield TitlesItem(
                title_id=title_id,
                url=title_url if is_single_volume else f"https://www.whakoom.com{title_url}",
                title=volume_name,
                scrape_status="pending",
                is_single_volume=is_single_volume,
            )

            yield TitlesListItem(
                list_id=db_list_id, title_id=title_id, position=position
            )

            self.logger.info(
                f"Processed title: {volume_name} (title_id={title_id}, is_single_volume={is_single_volume})"
            )

            self.processed_list_ids.add(db_list_id)

        except ValueError as e:
            self.logger.error("Failed to extract IDs for URLs %s: %s", title_url, e)
            self.sql_manager.update_single_field(
                "lists", "id", db_list_id, "scrape_status", "failed"
            )
            self.sql_manager.log_scraping_operation(
                scrapper_name=self.name,
                operation_type="title_processing",
                entity_id=whakoom_list_id,
                status="failed",
                error_message=str(e),
            )

    def _extract_title_id_from_url(self, url: str) -> int:
        """Extract numeric title_id from Title URL.

        Example:
        https://www.whakoom.com/ediciones/673392/rosen_blood → 673392

        Args:
            url: The Title URL.

        Returns:
            The numeric title ID.
        """
        parts = url.rstrip("/").split("/")
        if "ediciones" in parts:
            idx = parts.index("ediciones")
            if idx + 1 < len(parts):
                return int(parts[idx + 1])
        raise ValueError(f"Cannot extract title_id from URL: {url}")

    def errback_list(self, failure: Any) -> None:
        """Handle list request failures.

        Args:
            failure: The failure object.
        """
        list_id = failure.request.meta["list_id"]

        self.logger.error("Request failed for list_id %s: %s", list_id, failure)

        self.sql_manager.update_single_field(
            "lists", "list_id", list_id, "scrape_status", "failed"
        )

        self.sql_manager.log_scraping_operation(
            scrapper_name=self.name,
            operation_type="list_processing",
            entity_id=list_id,
            status="failed",
            error_message=str(failure),
        )

    def errback_volume_page(self, failure: Any) -> None:
        """Handle title page request failures.

        Args:
            failure: The failure object.
        """
        volume_url = failure.request.meta["volume_url"]

        self.logger.error("Request failed for title URL: %s", volume_url)

        self.sql_manager.log_scraping_operation(
            scrapper_name=self.name,
            operation_type="title_processing",
            entity_id=0,
            status="failed",
            error_message=str(failure),
        )

    def close_spider(self, spider: Spider) -> None:
        """Update list statuses to 'completed' and cleanup resources."""
        for db_list_id in self.processed_list_ids:
            self.sql_manager.update_single_field(
                "lists", "id", db_list_id, "scrape_status", "completed"
            )

        if self.driver is not None:
            self.driver.quit()
            self.driver = None

        self.sql_manager.log_scraping_operation(
            scrapper_name=self.name,
            operation_type="spider_finished",
            entity_id=0,
            status="success",
        )
