import json
import lxml.html
import os
import pprint
import scrapy
import tempfile
from polling_bot.brain import SlackClient, GitHubClient
from scrapy.crawler import CrawlerProcess
from sqlalchemy.exc import OperationalError

# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///data.sqlite'
import scraperwiki


"""
Set BOOTSTRAP_MODE to True to initialize an empty DB

If we are starting with an empty database we want to
- ensure we don't send any notifications and
- disable some consistency checks
"""
BOOTSTRAP_MODE = False
SEND_NOTIFICATIONS = not(BOOTSTRAP_MODE)

BASE_URL = "http://www.lgbce.org.uk/current-reviews"


try:
    SLACK_WEBHOOK_URL = os.environ['MORPH_BOUNDARY_BOT_SLACK_WEBHOOK_URL']
except KeyError:
    SLACK_WEBHOOK_URL = None

try:
    GITHUB_API_KEY = os.environ['MORPH_GITHUB_ISSUE_ONLY_API_KEY']
except KeyError:
    GITHUB_API_KEY = None


class SlackHelper:

    def __init__(self):
        self.messages = []

    def append_new_review_message(self, record):
        self.messages.append(
            "New boundary review found for %s: %s" %\
            (record['name'], record['url'])
        )

    def append_completed_review_message(self, record):
        self.messages.append(
            "Completed boundary review for %s: %s" %\
            (record['name'], record['url'])
        )

    def append_event_message(self, record):
        message = "%s boundary review status updated to '%s': %s" %\
            (record['name'], record['latest_event'], record['url'])
        if 'electoral changes' in record['latest_event'].lower():
            message = ':rotating_light: ' + message + ' :alarm_clock:'
        self.messages.append(message)

    def post_messages(self):
        client = SlackClient(SLACK_WEBHOOK_URL)
        for message in self.messages:
            client.post_message(message)


class GitHubHelper:

    def __init__(self):
        self.issues = []

    def append_completed_review_issue(self, record):
        self.issues.append({
            'title': 'Completed boundary review for %s' % (record['name']),
            'body': "Completed boundary review for %s: %s" % (record['name'], record['url']),
        })

    def raise_issues(self):
        owner = 'DemocracyClub'
        repo = 'EveryElection'
        client = GitHubClient(GITHUB_API_KEY)
        for issue in self.issues:
            client.raise_issue(owner, repo, issue['title'], issue['body'])


class ScraperException(Exception):
    pass


class LgbceSpider(scrapy.Spider):
    name = "reviews"
    custom_settings = {
        'CONCURRENT_REQUESTS': 5,  # keep the concurrent requests low
        'DOWNLOAD_DELAY': 0.25,  # throttle the crawl speed a bit
        'COOKIES_ENABLED': False,
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; WOW64; rv:56.0) Gecko/20100101 Firefox/56.0',
        'FEED_FORMAT': 'json',
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

        for desc in response.css("%s::attr(desc)" % (selector)).extract():
            yield {
                'slug': response.url.split('/')[-1],
                'latest_event': desc
            }

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


class LgbceScraper:

    """
    Scraper for The Local Government Boundary Commission for England's website

    By scraping the LGBCE website we can:
    - Discover boundary reviews
    - Detect when the status of a review has been updated
    - Send Slack messages and raise GitHub issues
      based on events in the boundary review process
    """

    CURRENT_LABEL = 'Current Reviews'
    COMPLETED_LABEL = 'Recently Completed'
    TABLE_NAME = 'lgbce_reviews'

    def __init__(self):
        scraperwiki.sql.execute("""
            CREATE TABLE IF NOT EXISTS %s (
                slug TEXT PRIMARY KEY,
                name TEXT,
                url TEXT,
                status TEXT,
                latest_event TEXT
            );""" % self.TABLE_NAME)
        self.data = {}
        self.slack_helper = SlackHelper()
        self.github_helper = GitHubHelper()

    def scrape_index(self):
        return scraperwiki.scrape(BASE_URL)

    def parse_index(self, html):
        expected_headings = [self.CURRENT_LABEL, self.COMPLETED_LABEL]
        root = lxml.html.fromstring(html)

        h2_tags = root.cssselect('h2')
        for h2 in h2_tags:
            text = str(h2.text)
            if text in expected_headings:
                # iterate over boundary reviews:
                for ul in h2.getnext().iterchildren():
                    link = ul.findall('a')[0]
                    url = link.get('href')
                    slug = url.split('/')[-1]
                    self.data[slug] = {
                        'slug': slug,
                        'name': link.text,
                        'url': url,
                        'status': text,
                        'latest_event': None,
                    }
            else:
                raise ScraperException(
                    "Unexpected heading: Found '%s', expected %s" %\
                    (str(h2.text), str(expected_headings))
                )

    def attach_spider_data(self):
        wrapper = SpiderWrapper(LgbceSpider)
        review_details = wrapper.run_spider()
        for area in review_details:
            if area['slug'] not in self.data:
                raise ScraperException(
                    "Unexpected slug: Found '%s', expected %s" %\
                    (area['slug'], str([rec for rec in self.data]))
                )
            self.data[area['slug']]['latest_event'] = area['latest_event']

    def run_checks(self):
        # perform some consistency checks
        # and raise an error if unexpected things have happened
        for key, record in self.data.items():

            if record['latest_event'] is None:
                # we've failed to scrape the latest review event
                raise ScraperException(
                    "Failed to populate 'latest_event' field:\n%s" % (str(record)))

            if BOOTSTRAP_MODE:
                # skip the next checks if we are initializing an empty DB
                return

            result = scraperwiki.sql.select(
                "* FROM %s WHERE slug=?" % (self.TABLE_NAME), record['slug'])

            if len(result) == 0 and record['status'] == self.COMPLETED_LABEL:
                # we shouldn't have found a record for the first time when it is completed
                # we should find it under review and then it should move to completed
                raise ScraperException(
                    "New record found but status is '%s':\n%s" %\
                    (self.COMPLETED_LABEL, str(record))
                )

            if len(result) == 1 and record['status'] == self.CURRENT_LABEL and result[0]['status'] == self.COMPLETED_LABEL:
                # reviews shouldn't move backwards from completed to current
                raise ScraperException(
                    "Record status has changed from '%s' to '%s':\n%s" %\
                    (self.COMPLETED_LABEL, self.CURRENT_LABEL, str(record))
                )

            if len(result) > 1:
                # society has collapsed :(
                raise ScraperException(
                    'Human sacrifice, dogs and cats living together, mass hysteria!')

    def make_notifications(self):
        for key, record in self.data.items():
            result = scraperwiki.sql.select(
                "* FROM %s WHERE slug=?" % (self.TABLE_NAME), record['slug'])

            if len(result) == 0:
                # we've not seen this boundary review before
                self.slack_helper.append_new_review_message(record)

            if len(result) == 1:
                # we've already got our eye on this one
                if result[0]['status'] == self.CURRENT_LABEL and record['status'] == self.COMPLETED_LABEL:
                    self.slack_helper.append_completed_review_message(record)
                    self.github_helper.append_completed_review_issue(record)
                if result[0]['latest_event'] != record['latest_event']:
                    self.slack_helper.append_event_message(record)

    def save(self):
        for key, record in self.data.items():
            scraperwiki.sqlite.save(
                unique_keys=['slug'], data=record, table_name=self.TABLE_NAME)

    def send_notifications(self):

        # write the notifications we've generated to
        # send to the console as well for debug purposes
        pp = pprint.PrettyPrinter(indent=2)
        print('Slack messages:')
        print('----')
        pp.pprint(self.slack_helper.messages)
        print('Github issues:')
        print('----')
        pp.pprint(self.github_helper.issues)

        if not SEND_NOTIFICATIONS:
            return

        if SLACK_WEBHOOK_URL:
            self.slack_helper.post_messages()
        if GITHUB_API_KEY:
            self.github_helper.raise_issues()

    def cleanup(self):
        # remove any stale records from the DB
        if not self.data:
            return
        placeholders = '(' + ', '.join(['?' for rec in self.data]) + ')'
        result = scraperwiki.sql.execute(
            ("DELETE FROM %s WHERE slug NOT IN " + placeholders) % (self.TABLE_NAME),
            [slug for slug in self.data]
        )

    def scrape(self):
        self.parse_index(self.scrape_index())
        self.attach_spider_data()
        self.run_checks()
        self.make_notifications()
        self.save()
        self.send_notifications()
        self.cleanup()


if __name__ == '__main__':
    scraper = LgbceScraper()
    scraper.scrape()
