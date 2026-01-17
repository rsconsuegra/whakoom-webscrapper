"""Define here the models for your scraped items.

See documentation in:
https://docs.scrapy.org/en/latest/topics/items.html
"""

from dataclasses import dataclass


@dataclass(kw_only=True)
class ListsItem:
    """Represents a scraped list with metadata.

    Attributes:
        list_id (int): The WhaKoom internal list ID.
        title (str): The title of the list.
        url (str): The URL of the list.
        user_profile (str): The user profile that owns the list.
        scrape_status (str): The scraping status (pending, in_progress, completed, failed).
        scraped_at (str | None): Timestamp when the list was scraped.
    """

    list_id: int
    title: str
    url: str
    user_profile: str
    scrape_status: str = "pending"
    scraped_at: str | None = None

    def __getitem__(self, attr: str) -> str:
        """Get the value of the specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitlesItem:
    """Represents a scraped title/collection.

    Attributes:
        title_id (int): The WhaKoom internal title ID.
        title (str): The title of the manga.
        url (str): The URL of the title page.
        scrape_status (str): The scraping status (pending, in_progress, completed, failed).
        scraped_at (str | None): Timestamp when the title was scraped.
    """

    title_id: int
    title: str
    url: str
    scrape_status: str = "pending"
    scraped_at: str | None = None

    def __getitem__(self, attr: str) -> str:
        """Get the value of the specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, attr)


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True)
class VolumesItem:
    """Represents a scraped volume.

    Attributes:
        volume_id (int): The WhaKoom internal volume ID.
        title_id (int): The internal ID of the parent title.
        volume_number (int | None): The volume number.
        title (str | None): The title of the volume.
        url (str | None): The URL of the volume page.
        isbn (str | None): The ISBN of the volume.
        publisher (str | None): The publisher of the volume.
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

    def __getitem__(self, attr: str) -> str:
        """Get the value of the specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitleMetadataItem:
    """Represents metadata for a title.

    Attributes:
        title_id (int): The internal ID of the parent title.
        author (str | None): The author of the title.
        publisher (str | None): The publisher of the title.
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

    def __getitem__(self, attr: str) -> str:
        """Get the value of the specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, attr)


@dataclass(kw_only=True)
class TitlesListItem:
    """Represents a title within a list (many-to-many relationship).

    Attributes:
        list_id (int): The internal ID of the list.
        title_id (int): The internal ID of the title.
        position (int | None): The position within the list.
    """

    list_id: int
    title_id: int
    position: int | None = None

    def __getitem__(self, attr: str) -> str:
        """Get the value of the specified attribute.

        Args:
            attr (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, attr)
