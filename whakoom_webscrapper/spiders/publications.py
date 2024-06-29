import scrapy


class PublicationsSpider(scrapy.Spider):
    name = "publications"
    allowed_domains = ["whakoom.com"]
    start_urls = [
        "https://www.whakoom.com/deirdre/lists/titulos_editados_en_espana_publicados_en_la_revista_sho-comi_116039"
    ]

    def parse(self, response):
        # Select all spans with class 'title' that contain an <a> tag
        title_spans_with_link = response.xpath('//span[@class="title"]/a')
        # Extract href link and text content of these <a> tags
        for item in title_spans_with_link:
            link = item.xpath("@href").get()
            title = item.xpath("text()").get()

            # Yield the item
            yield {"title": title, "href": link}
