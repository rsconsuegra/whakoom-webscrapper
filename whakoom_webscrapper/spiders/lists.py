"""This module contains the main entry point for the lists to gather."""

from collections.abc import Iterator

from scrapy import Spider
from scrapy.http import Response

from whakoom_webscrapper.items import PublicationsList


class ListSpider(Spider):
    """Scrapes lists from the Whakoom website."""

    name = "lists"
    allowed_domains = ["whakoom.com"]
    start_urls = ["https://www.whakoom.com/deirdre/lists"]

    def parse(self, response: Response, **kwargs: str) -> Iterator[PublicationsList]:
        """Parse the response from the scraped URL and extracts list items.

        Args:
            response (Response): The response object returned by Scrapy's engine.

        Yields:
            list_item: An instance of the PublicationsList class containing
                      the list's id, title, and URL.

        This method first finds all <h3> tags in the response.
        Then, it loops through each <h3> tag and finds the parent element.
        It then searches for all <a> tags that come after the <h3> tag within
        the same parent element. If there are at least 2 <a> tags, it extracts
        the list title and URL, and creates a ListItem instance
        with the extracted data. The ListItem instance is then yielded.
        """
        # Find all <h3> tags
        h3_tags = response.css("h3")

        # Loop through each <h3> tag
        for h3 in h3_tags:
            # Find the parent element of the <h3> tag
            parent_div = h3.xpath("parent::node()")

            # Find all <a> tags that come after the <h3> tag within the same parent element
            following_a_tags = parent_div.xpath(".//a")

            if len(following_a_tags) > 1:  # Check if there are at least 2 <a> tags
                list_title = following_a_tags[1].xpath("string()").extract_first().strip()
                self.logger.info("Found a list")
                list_item = PublicationsList(
                    id=following_a_tags[1].attrib["href"].rsplit("_", 1)[-1],
                    title=list_title,
                    url=following_a_tags[1].attrib["href"],
                )
                yield list_item
