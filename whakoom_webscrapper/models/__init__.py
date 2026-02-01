"""Define here your models for your scraped items and database entities.

This module provides unified data structures that work with both Scrapy (Items)
and SQLManager (database Models). Each class includes:
- Dataclass fields for structure
- __getitem__() for Scrapy compatibility
- table_name for SQLManager
- to_tuple() for SQL parameter generation

See documentation:
https://docs.scrapy.org/en/latest/topics/items.html
"""

from dataclasses import dataclass


@dataclass(kw_only=True)
class ListsItem:
    """Represents a scraped list with metadata.

    Attributes:
        list_id (int): The WhaKoom internal list ID.
        title (str): The title of list.
        url (str): The URL of the list.
        user_profile (str): The user profile that owns list.
        scrape_status (str): The scraping status (pending, in_progress, completed, failed).
        scraped_at (str | None): Timestamp when list was scraped.
    """

    list_id: int
    title: str
    url: str
    user_profile: str
    scrape_status: str = "pending"
    scraped_at: str | None = None

    table_name: str = "lists"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.list_id,
            self.title,
            self.url,
            self.user_profile,
            self.scrape_status,
            self.scraped_at,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitlesItem:
    """Represents a scraped title/collection.

    Attributes:
        title_id (int): The WhaKoom internal title ID.
        title (str): The title of manga.
        scrape_status (str): The scraping status (pending, in_progress, completed, failed).
        scraped_at (str | None): Timestamp when title was scraped.
        title_url (str | None): The full URL from anchor tag.
    """

    title_id: int
    title: str
    title_url: str
    scrape_status: str = "pending"
    scraped_at: str | None = None

    table_name: str = "titles"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.title_id,
            self.title,
            self.scrape_status,
            self.scraped_at,
            self.title_url,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class VolumesItem:  # pylint: disable=too-many-instance-attributes
    """Represents a scraped volume.

    Attributes:
        volume_id (int): The WhaKoom internal volume ID.
        title_id (int): The internal ID of the parent title.
        volume_number (int | None): The volume number.
        title (str | None): The title of volume.
        url (str | None): The URL of the volume page.
        isbn (str | None): The ISBN of volume.
        publisher (str | None): The publisher of volume.
        year (int | None): The publication year.
    """

    volume_id: int
    title_id: int
    volume_number: int | None = None
    title: str | None = None
    url: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    year: int | None = None

    table_name: str = "volumes"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.volume_id,
            self.title_id,
            self.volume_number,
            self.title,
            self.url,
            self.isbn,
            self.publisher,
            self.year,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleMetadataItem:  # pylint: disable=too-many-instance-attributes
    """Represents metadata for a title.

    Attributes:
        title_id (int): The internal ID of the parent title.
        author (str | None): The author of title.
        publisher (str | None): The publisher of title.
        demographic (str | None): The demographic (shonen, shojo, etc.).
        genre (str | None): The genre.
        themes (str | None): The themes.
        original_title (str | None): The original title.
        description (str | None): The description.
        start_year (int | None): The start year.
        end_year (int | None): The end year.
        status (str | None): The status (ongoing, completed, etc.).
    """

    title_id: int
    author: str | None = None
    publisher: str | None = None
    demographic: str | None = None
    genre: str | None = None
    themes: str | None = None
    original_title: str | None = None
    description: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    status: str | None = None

    table_name: str = "title_metadata"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.title_id,
            self.author,
            self.publisher,
            self.demographic,
            self.genre,
            self.themes,
            self.original_title,
            self.description,
            self.start_year,
            self.end_year,
            self.status,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleEnrichedItem:  # pylint: disable=too-many-instance-attributes
    """Represents enriched data for a title.

    Attributes:
        title_id (int): The internal ID of the parent title.
        cover_url (str | None): The URL of the cover image.
        cover_image_path (str | None): The local path to the cover image.
        rating (float | None): The rating score.
        rating_count (int | None): The number of ratings.
        popularity_rank (int | None): The popularity ranking.
        myanimelist_url (str | None): The MyAnimeList URL.
        mangaupdates_url (str | None): The MangaUpdates URL.
        anilist_url (str | None): The AniList URL.
        additional_data (str | None): Additional JSON data.
    """

    title_id: int
    cover_url: str | None = None
    cover_image_path: str | None = None
    rating: float | None = None
    rating_count: int | None = None
    popularity_rank: int | None = None
    myanimelist_url: str | None = None
    mangaupdates_url: str | None = None
    anilist_url: str | None = None
    additional_data: str | None = None

    table_name: str = "title_enriched"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.title_id,
            self.cover_url,
            self.cover_image_path,
            self.rating,
            self.rating_count,
            self.popularity_rank,
            self.myanimelist_url,
            self.mangaupdates_url,
            self.anilist_url,
            self.additional_data,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitlesListItem:
    """Represents a title within a list (many-to-many relationship).

    Attributes:
        list_id (int): The internal ID of list.
        title_id (int): The internal ID of title.
        position (int | None): The position within list.
    """

    list_id: int
    title_id: int
    position: int | None = None

    table_name: str = "lists_titles"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.list_id,
            self.title_id,
            self.position,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class ScrapingLogItem:
    """Represents a scraping operation log entry.

    Attributes:
        scrapper_name (str): The name of the scraper/spider.
        operation_type (str): The type of operation (e.g., 'list', 'title', 'volume').
        entity_id (int): The ID of the entity being processed.
        status (str): The status of the operation ('started', 'success', 'failed').
        error_message (str | None): Error message if the operation failed.
        duration_ms (int | None): The duration of the operation in milliseconds.
    """

    scrapper_name: str
    operation_type: str
    entity_id: int
    status: str
    error_message: str | None = None
    duration_ms: int | None = None

    table_name: str = "scraping_log"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.scrapper_name,
            self.operation_type,
            self.entity_id,
            self.status,
            self.error_message,
            self.duration_ms,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class MigrationItem:
    """Represents a migration record.

    Attributes:
        version (str): The migration version number.
        name (str): The migration name.
    """

    version: str
    name: str

    table_name: str = "migrations"

    def to_tuple(self) -> tuple:
        """Convert model to tuple for parameterized queries.

        Returns:
            tuple: Model values as tuple.
        """
        return (
            self.version,
            self.name,
        )

    def __getitem__(self, attr: str) -> str:
        """Get value of specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of specified attribute.
        """
        return getattr(self, attr)


__all__ = [
    "ListsItem",
    "TitlesItem",
    "VolumesItem",
    "TitleMetadataItem",
    "TitleEnrichedItem",
    "TitlesListItem",
    "ScrapingLogItem",
    "MigrationItem",
]
