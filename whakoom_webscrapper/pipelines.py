# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


# useful for handling different item types with a single interface
import sqlite3
from pathlib import Path

from scrapy import Spider
from scrapy.exceptions import DropItem

from .items import PublicationsList

SPIDER_MAPS = {"lists": "list_of_publications"}


class WhakoomWebscrapperPipeline:
    def open_spider(self, spider: Spider):
        """Initialize the database connection and cursor for the given spider.

        If the spider's name is in the SPIDER_MAPS dictionary,
        it will create a new table in the database with the specified name,
        with columns 'url' and 'title'.

        Parameters
        ----------
        spider : Spider
            The spider instance that is being opened.
        """
        self.conn = sqlite3.connect(Path.cwd() / "databases" / "publications.db")
        self.c = self.conn.cursor()
        if spider.name in SPIDER_MAPS:
            self.c.execute(
                f"CREATE TABLE IF NOT EXISTS {SPIDER_MAPS[spider.name]} (id INTEGER NOT NULL, url TEXT NOT NULL, title TEXT)"
            )

    def close_spider(self, spider):
        self.conn.commit()
        self.conn.close()

    def process_item(self, item, spider):
        if isinstance(item, PublicationsList):
            self.c.execute(
                f"INSERT INTO {SPIDER_MAPS[spider.name]} (id, url, title) VALUES (?, ?, ?)",
                (item["id"], item["url"], item["title"]),
            )
            return item
        else:
            raise DropItem("Unknown item type: %s" % type(item))
