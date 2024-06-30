"""This module contains the main entry point for the lists to gather."""

from scrapy import Spider

from whakoom_webscrapper.items import PublicationsList


class ListSpider(Spider):
    name = "lists"
    allowed_domains = ["whakoom.com"]
    start_urls = ["https://www.whakoom.com/deirdre/lists"]

    def parse(self, response):
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
                    id = following_a_tags[1].attrib["href"].rsplit('_', 1)[-1],
                    title=list_title,
                    url=following_a_tags[1].attrib["href"],
                )
                yield list_item
