"""Dataclass models for database entities."""

from dataclasses import dataclass
from typing import Any


@dataclass(kw_only=True)
class ListModel:
    """Model for lists table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleModel:
    """Model for titles table."""

    title_id: int
    title: str
    url: str
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
            self.url,
            self.scrape_status,
            self.scraped_at,
        )

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class VolumeModel:
    """Model for volumes table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class ListTitleModel:
    """Model for lists_titles junction table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleMetadataModel:  # pylint: disable=too-many-instance-attributes
    """Model for title_metadata table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleEnrichedModel:  # pylint: disable=too-many-instance-attributes
    """Model for title_enriched table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class ScrapingLogModel:
    """Model for scraping_log table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class MigrationModel:
    """Model for migrations table."""

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

    def __getitem__(self, attr: str) -> Any:
        """Get attribute by name for compatibility.

        Args:
            attr: Attribute name.

        Returns:
            Attribute value.
        """
        return getattr(self, attr)
