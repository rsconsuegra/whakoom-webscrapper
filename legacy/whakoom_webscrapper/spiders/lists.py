"""This module contains the main entry point for the lists to gather."""

from collections.abc import Iterator
from urllib.parse import urlparse

from scrapy import Spider
from scrapy.http import Response

from whakoom_webscrapper.models import ListsItem


class ListSpider(Spider):
    """Scrapes lists from the Whakoom website."""

    name = "lists"
    allowed_domains = ["whakoom.com"]
    start_urls = ["https://www.whakoom.com/deirdre/lists"]

    def parse(self, response: Response) -> Iterator[ListsItem]:
        """Parse the response from the scraped URL and extracts list items.

        Args:
            response (Response): The response object returned by Scrapy's engine.

        Yields:
            ListsItem: An instance of ListsItem containing the list's id, title, and URL.

        This method first finds all <h3> tags in the response.
        Then, it loops through each <h3> tag and finds the parent element.
        It then searches for all <a> tags that come after the <h3> tag within
        the same parent element. If there are at least 2 <a> tags, it extracts
        the list title and URL, and creates a ListsItem instance
        with the extracted data. The ListsItem instance is then yielded.
        """
        parsed_url = urlparse(response.url)
        user_profile = parsed_url.path.split("/")[1] if parsed_url.path else ""
        self.logger.info("Scraping lists for user profile: %s", user_profile)

        h3_tags = response.xpath('//*[@id="pp-lists"]/div/*/h3/a')

        for h3 in h3_tags:
            list_title = str(h3.xpath("string()").get())
            list_url = h3.attrib["href"]
            list_id = int(list_url.rsplit("_", 1)[-1])

            yield ListsItem(
                list_id=list_id,
                title=list_title,
                url=list_url,
                user_profile=user_profile,
                scrape_status="pending",
            )
