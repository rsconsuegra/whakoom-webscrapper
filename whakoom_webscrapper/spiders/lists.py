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

        h3_tags = response.css("h3")

        for h3 in h3_tags:
            parent_div = h3.xpath("parent::node()")
            following_a_tags = parent_div.xpath(".//a")

            if len(following_a_tags) > 1:
                list_title = following_a_tags[1].xpath("string()").extract_first().strip()
                list_id = int(following_a_tags[1].attrib["href"].rsplit("_", 1)[-1])

                yield ListsItem(
                    list_id=list_id,
                    title=list_title,
                    url=following_a_tags[1].attrib["href"],
                    user_profile=user_profile,
                    scrape_status="pending",
                )
