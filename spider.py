import scrapy


class LgbceSpider(scrapy.Spider):
    name = "reviews"
    custom_settings = {
        'CONCURRENT_REQUESTS': 5,  # keep the concurrent requests low
        'DOWNLOAD_DELAY': 0.25,  # throttle the crawl speed a bit
        'COOKIES_ENABLED': False,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:56.0) Gecko/20100101 Firefox/56.0',
    }
    allowed_domains = ["lgbce.org.uk"]
    start_urls = ["http://www.lgbce.org.uk/current-reviews"]

    def parse(self, response):
        for desc in response.css('div.tab-1::attr(desc)').extract():
            yield {
                'local_auth': response.url.split('/')[-1],
                'latest_stage': desc
            }

        for next_page in response.css('ul > li > a'):
            if 'current-reviews' in next_page.extract():
                yield response.follow(next_page, self.parse)
