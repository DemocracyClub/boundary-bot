import json
import os
import scrapy
import tempfile
from scrapy.crawler import CrawlerProcess
from boundary_bot.common import is_eco, BASE_URL, REQUEST_HEADERS


class LgbceSpider(scrapy.Spider):
    name = "reviews"
    custom_settings = {
        'CONCURRENT_REQUESTS': 5,  # keep the concurrent requests low
        'DOWNLOAD_DELAY': 0.25,  # throttle the crawl speed a bit
        'COOKIES_ENABLED': False,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:56.0) Gecko/20100101 Firefox/56.0',
        'FEED_FORMAT': 'json',
        'DEFAULT_REQUEST_HEADERS': REQUEST_HEADERS
    }
    allowed_domains = ["lgbce.org.uk"]
    start_urls = [BASE_URL]

    def parse(self, response):

        # the class we're looking for will be called 'tab-1'
        # ...except when it is called something else
        potential_selectors = ['div.tab-1', 'div.-tab-1', 'div.tab-2']
        selector = potential_selectors[0]
        for s in potential_selectors:
            if len(response.css(s)) > 0:
                selector = s
                break

        desc = response.css("%s::attr(desc)" % (selector)).extract()
        if len(desc) == 1:
            rec = {
                'slug': response.url.split('/')[-1],
                'latest_event': desc[0].strip(),
                'shapefiles': None,
                'eco_made': 0,
            }

            # find any links to zip files in the page
            zipfiles = response.xpath("/html/body//a[contains(@href,'.zip')]/@href").extract()
            # if we found exactly one, assume that's what we're looking for
            # the files we're looking for are not very consistently named :(

            # de-dupe the list, we don't care about order
            zipfiles = list(set(zipfiles))
            if len(zipfiles) == 1:
                rec['shapefiles'] = zipfiles[0]

            # try to work out if the ECO is 'made'
            eco_made_text = "have now successfully completed a 40 day period "
            "of parliamentary scrutiny and will come into force"
            div = response.css(selector).extract()

            if is_eco(desc[0]) and eco_made_text in div[0].lower():
                rec['eco_made'] = 1

            yield rec

        for next_page in response.css('ul > li > a'):
            if 'current-reviews' in next_page.extract():
                yield response.follow(next_page, self.parse)


class SpiderWrapper:

    # Wrapper class that allows us to run a scrapy spider
    # and return the result as a list

    def __init__(self, spider):
        self.spider = spider

    def run_spider(self):
        # Scrapy likes to dump its output to file
        # so we will write it out to a file and read it back in.
        # The 'proper' way to do this is probably to write a custom Exporter
        # but this will do for now

        tmpfile = tempfile.NamedTemporaryFile().name

        process = CrawlerProcess({
            'FEED_URI': tmpfile,
        })
        process.crawl(self.spider)
        process.start()

        results = json.load(open(tmpfile))

        os.remove(tmpfile)

        return results
