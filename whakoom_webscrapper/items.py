# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html


from dataclasses import dataclass


@dataclass(kw_only=True)
class Lists:
    url: str
    title: str
    
    def __getitem__(self, item):
        return getattr(self, item)

@dataclass(kw_only=True)
class PublicationsList(Lists):
    id: int

@dataclass
class TitlesList:
    url: str
    title: str
    
    def __getitem__(self, item):
        return getattr(self, item)