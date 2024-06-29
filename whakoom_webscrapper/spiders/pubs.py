import scrapy
from scrapy_splash import SplashRequest


class PubSpider(scrapy.Spider):
    name = "pubs"
    start_urls = [
        "https://www.whakoom.com/deirdre/lists/titulos_editados_en_espana_publicados_en_la_revista_sho-comi_116039",
    ]

    def start_requests(self):
        for url in self.start_urls:
            yield SplashRequest(url, callback=self.parse, endpoint="render.html")

    def parse(self, response):
        # Your parsing logic here
        title_spans_with_link = response.xpath('//span[@class="title"]/a')
        # Extract href link and text content of these <a> tags
        for item in title_spans_with_link:
            link = item.xpath("@href").get()
            title = item.xpath("text()").get()

            # Yield the item
            yield {"title": title, "href": link}
        # Check if the "Mostrar más cómics..." button is present

        # Execute JavaScript to click the button
        script = """
        function main(splash)
            splash:wait(0.5)
            splash:runjs("document.querySelector('#loadmoreissues').click();")
            splash:wait(15)
            return splash:html()
        end
        """
        yield SplashRequest(
            response.url,
            callback=self.parse,
            endpoint="execute",
            args={"lua_source": script},
        )
