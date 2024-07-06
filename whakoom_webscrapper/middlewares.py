"""Define here the models for your spider middleware.

See documentation in:
https://docs.scrapy.org/en/latest/topics/spider-middleware.html
useful for handling different item types with a single interface
"""

from typing import Self

from scrapy import Spider, signals
from scrapy.crawler import Crawler


class WhakoomWebscrapperSpiderMiddleware:
    """Class for handling the webscrapping."""

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Use by Scrapy to create spiders.

        Args:
            crawler (Crawler): The crawler instance that is creating the spider.

        Returns:
            cls: The instance of the spider middleware class.

        Raises:
            None

        This method is called by Scrapy to create your spiders.
        It is responsible for connecting the spider's signals to
        the appropriate methods in the spider middleware class.
        """
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def spider_opened(self, spider: Spider) -> None:
        """Log Spider opening."""
        spider.logger.info("Spider opened: %s", spider.name)


class WhakoomWebscrapperDownloaderMiddleware:
    """Class for scrapper.

    Not all methods need to be defined. If a method is not defined,
    scrapy acts as if the downloader middleware does not modify the
    passed objects.
    """

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        """Use by Scrapy to create your spiders."""
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def spider_opened(self, spider: Spider) -> None:
        """Log scrapper opening."""
        spider.logger.info("Spider opened: %s", spider.name)
