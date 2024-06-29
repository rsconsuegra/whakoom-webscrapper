""" Define here the models for your scraped items

See documentation in:
https://docs.scrapy.org/en/latest/topics/items.html"""


from dataclasses import dataclass


@dataclass(kw_only=True)
class Lists:
    """
    Define a dataclass for a list of items with a URL and a title.

    Attributes:
        url (str): The URL of the list.
        title (str): The title of the list.
    """
    url: str
    title: str

    def __getitem__(self, item):
        """
        Get the value of the specified attribute.

        Args:
            item (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, item)


@dataclass(kw_only=True)
class PublicationsList(Lists):
    """
    Define a subclass of the Lists dataclass, specifically for publications lists.

    Attributes:
        id (int): A unique identifier for the publications list.

    Inherits from:
        Lists: A dataclass for a list of items with a URL and a title.
    """
    id: int


@dataclass
class TitlesList:
    """
    Define a TitlesList class for a list of items with a URL and a title.

    Attributes:
        url (str): The URL of the list.
        title (str): The title of the list.

    Methods:
        __getitem__(self, item):
            Get the value of the specified attribute.

    Args:
        item (str): The attribute name.

    Returns:
        The value of the specified attribute.
    """
    url: str
    title: str

    def __getitem__(self, item):
        """
        Get the value of the specified attribute.

        Args:
            item (str): The attribute name.

        Returns:
            The value of the specified attribute.
        """
        return getattr(self, item)
