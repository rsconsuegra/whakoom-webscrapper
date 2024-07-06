"""Define your item pipelines here.

Don't forget to add your pipeline to the ITEM_PIPELINES setting
See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
"""

import logging
import sqlite3
from pathlib import Path
from sqlite3 import Connection, Cursor

from scrapy import Spider
from scrapy.exceptions import DropItem

from .items import Lists, PublicationsList

SPIDER_MAPS = {"lists": "list_of_publications"}


class WhakoomWebscrapperPipeline:
    """Pipeline for saving items to a SQLite database."""

    def __init__(self) -> None:
        """Initialize the SQLite database connection and cursor."""
        self.conn: Connection = sqlite3.connect(Path.cwd() / "databases" / "publications.db")
        self.cursor: Cursor = self.conn.cursor()

    def open_spider(self, spider: Spider) -> None:
        """Initialize the database connection and cursor for the given spider.

        If the spider's name is in the SPIDER_MAPS dictionary,
        it will create a new table in the database with the specified name,
        with columns 'url' and 'title'.

        Parameters
        ----------
        spider : Spider
            The spider instance that is being opened.
        """
        query = """CREATE TABLE IF NOT EXISTS {name}
                (id INTEGER NOT NULL, url TEXT NOT NULL, title TEXT)"""
        if spider.name in SPIDER_MAPS:
            logging.info("Setting DB.")
            self.cursor.execute(query.format(name=SPIDER_MAPS[spider.name]))

    def close_spider(self, spider: Spider) -> None:
        """Close the database connection for the given spider.

        Args:
            spider (Spider): The spider instance that is being closed.
        Notes:
        This method is called when the spider is finished running.
        It commits any pending changes to the database and closes the database connection.
        """
        logging.info("Closing DB for %s.", spider.name)
        self.conn.commit()
        self.conn.close()

    def process_item(self, item: type[Lists], spider: Spider) -> type[Lists] | None:
        """
        Process an item and decide whether to keep it or not.

        Args:
            item (type[Lists]): The item to be processed.
            spider (Spider): The spider instance that is being processed.

        Raises:
            DropItem: If the item type is unknown.

        Returns:
            type[Lists]: The processed item.

        Notes:
            This method is called for each item processed by the spider.
            It should return the item if it is to be saved to the database,
            or raise a DropItem exception if it should not be saved.
        """
        logging.info("Saving to DB for, %s.", spider.name)
        if isinstance(item, PublicationsList):
            self.cursor.execute(
                f"INSERT INTO {SPIDER_MAPS[spider.name]} (id, url, title) VALUES (?, ?, ?)",
                (item["id"], item["url"], item["title"]),
            )
            return item
        raise DropItem(f"Unknown item type: {type(item)}")
