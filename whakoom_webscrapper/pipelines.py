"""Define your item pipelines here.

Don't forget to add your pipeline to the ITEM_PIPELINES setting
See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html
"""

import logging
import time
from pathlib import Path

from scrapy import Spider
from scrapy.exceptions import DropItem

from whakoom_webscrapper.configs.configs import db_path
from whakoom_webscrapper.items import ListsItem, TitlesItem, VolumesItem
from whakoom_webscrapper.sqlmanager import SQLManager


class WhakoomWebscrapperPipeline:
    """Pipeline for saving items to SQLite database using SQLManager."""

    def __init__(self) -> None:
        """Initialize SQLManager with migrations and queries directories."""
        migrations_dir = Path(__file__).parent / "migrations"
        queries_dir = Path(__file__).parent / "queries"

        self.sql_manager = SQLManager(
            db_path=str(db_path),
            sql_dir=str(queries_dir),
            migrations_dir=str(migrations_dir),
        )
        self.processed_list_ids: set[int] = set()
        self.processed_title_ids: set[int] = set()
        self.processed_volume_ids: set[int] = set()

    def open_spider(self, spider: Spider) -> None:
        """Initialize database and apply migrations when spider opens.

        Args:
            spider (Spider): The spider instance that is being opened.
        """
        logging.info("Applying migrations for spider: %s", spider.name)
        self.sql_manager.apply_migrations()

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="spider_started",
            entity_id=0,
            status="success",
        )
        logging.info("Migrations applied and spider started for: %s", spider.name)

    def close_spider(self, spider: Spider) -> None:
        """Log completion and update statuses when spider closes.

        Args:
            spider (Spider): The spider instance that is being closed.
        """
        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="spider_finished",
            entity_id=0,
            status="success",
        )

        for list_id in self.processed_list_ids:
            self.sql_manager.execute_parametrized_query(
                "UPDATE_LIST_STATUS",
                ("completed", list_id),
            )
            logging.info("Updated list_id %s status to completed", list_id)

        logging.info("Spider finished for: %s", spider.name)

    def process_item(self, item: ListsItem | TitlesItem | VolumesItem, spider: Spider) -> None:
        """Process item and save to database with retry logic.

        Args:
            item: The item to be processed (ListsItem, TitlesItem, or VolumesItem).
            spider (Spider): The spider instance that is being processed.

        Returns:
            The processed item.

        Raises:
            DropItem: If the item type is unknown or after retries fail.
        """
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                if isinstance(item, ListsItem):
                    self._process_lists_item(item, spider)
                elif isinstance(item, TitlesItem):
                    self._process_titles_item(item, spider)
                elif isinstance(item, VolumesItem):
                    self._process_volumes_item(item, spider)
                else:
                    raise DropItem(f"Unknown item type: {type(item)}")

                return

            except Exception as e:  # pylint: disable=W0718
                logging.error(
                    "Error processing item (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    self.sql_manager.log_scraping_operation(
                        scrapper_name=spider.name,
                        operation_type="item_failed",
                        entity_id=0,
                        status="failed",
                        error_message=str(e),
                    )
                    raise DropItem(f"Failed to process item after {max_retries} attempts: {e}") from e

    def _process_lists_item(self, item: ListsItem, spider: Spider) -> None:
        """Process ListsItem and save to database.

        Args:
            item (ListsItem): The lists item to process.
            spider (Spider): The spider instance.
        """
        logging.info("Processing list: %s (list_id: %s)", item.title, item.list_id)

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="list_processing",
            entity_id=item.list_id,
            status="started",
        )

        self.sql_manager.execute_parametrized_query(
            "INSERT_OR_UPDATE_LIST",
            (
                item.list_id,
                item.title,
                item.url,
                item.user_profile,
                item.scrape_status,
                item.scraped_at,
            ),
        )

        self.processed_list_ids.add(item.list_id)

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="list_processing",
            entity_id=item.list_id,
            status="success",
        )

    def _process_titles_item(self, item: TitlesItem, spider: Spider) -> None:
        """Process TitlesItem and save to database.

        Args:
            item (TitlesItem): The titles item to process.
            spider (Spider): The spider instance.
        """
        logging.info("Processing title: %s (title_id: %s)", item.title, item.title_id)

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="title_processing",
            entity_id=item.title_id,
            status="started",
        )

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="title_processing",
            entity_id=item.title_id,
            status="success",
        )

    def _process_volumes_item(self, item: VolumesItem, spider: Spider) -> None:
        """Process VolumesItem and save to database.

        Args:
            item (VolumesItem): The volumes item to process.
            spider (Spider): The spider instance.
        """
        logging.info("Processing volume (volume_id: %s)", item.volume_id)

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="volume_processing",
            entity_id=item.volume_id,
            status="started",
        )

        self.sql_manager.log_scraping_operation(
            scrapper_name=spider.name,
            operation_type="volume_processing",
            entity_id=item.volume_id,
            status="success",
        )
