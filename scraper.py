import json
import lxml.html
import os
import scrapy
import tempfile
from polling_bot.brain import SlackClient, GitHubClient
from scrapy.crawler import CrawlerProcess
from sqlalchemy.exc import OperationalError

# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///data.sqlite'
import scraperwiki


SEND_NOTIFICATIONS = True
RUN_CHECKS = True
BASE_URL = "http://www.lgbce.org.uk/current-reviews"


try:
    SLACK_WEBHOOK_URL = os.environ['MORPH_BOUNDARY_BOT_SLACK_WEBHOOK_URL']
except KeyError:
    SLACK_WEBHOOK_URL = None

try:
    GITHUB_API_KEY = os.environ['MORPH_GITHUB_ISSUE_ONLY_API_KEY']
except KeyError:
    GITHUB_API_KEY = None


def post_slack_message(message):
    slack = SlackClient(SLACK_WEBHOOK_URL)
    slack.post_message(message)


def raise_github_issue(title, body):
    owner = 'DemocracyClub'
    repo = 'EveryElection'
    github = GitHubClient(GITHUB_API_KEY)
    github.raise_issue(owner, repo, title, body)


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

    CURRENT_LABEL = 'Current Reviews'
    COMPLETED_LABEL = 'Recently Completed'

    def __init__(self):
        scraperwiki.sql.execute("""
            CREATE TABLE IF NOT EXISTS lgbce_reviews (
                slug TEXT PRIMARY KEY,
                name TEXT,
                url TEXT,
                status TEXT,
                latest_event TEXT
            );""")
        self.data = {}
        self.slack_messages = []
        self.github_issues = []

    def scrape_index(self):
        expected_headings = [self.CURRENT_LABEL, self.COMPLETED_LABEL]
        html = scraperwiki.scrape(BASE_URL)
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
                    'Found a heading other than %s' % (str(expected_headings)))

    def attach_spider_data(self):
        wrapper = SpiderWrapper(LgbceSpider)
        review_details = wrapper.run_spider()
        for area in review_details:
            self.data[area['slug']]['latest_event'] = area['latest_event']

    def run_checks(self):
        # perform some consistency checks
        # and raise an error if unexpected things have happened
        for key, record in self.data.items():
            result = scraperwiki.sql.select(
                "* FROM 'lgbce_reviews' WHERE slug=?", record['slug'])

            if record['latest_event'] is None:
                # we've failed to scrape the latest review event
                raise ScraperException(
                    "Failed to populate 'latest_event' field:\n%s" % (str(record)))

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
                "* FROM 'lgbce_reviews' WHERE slug=?", record['slug'])

            if len(result) == 0:
                # we've not seen this boundary review before
                self.slack_messages.append(
                    "New boundary review found for %s: %s" % (record['name'], record['url']))

            if len(result) == 1:
                # we've already got our eye on this one
                if result[0]['status'] == self.CURRENT_LABEL and record['status'] == self.COMPLETED_LABEL:
                    self.slack_messages.append(
                        "Completed boundary review for %s: %s" % (record['name'], record['url']))
                    self.github_issues.append({
                        'title': 'Completed boundary review for %s' % (record['name']),
                        'body': "Completed boundary review for %s: %s" % (record['name'], record['url']),
                    })
                if result[0]['latest_event'] != record['latest_event']:
                    message = "%s boundary review status updated to '%s': %s" %\
                        (record['name'], record['latest_event'], record['url'])
                    if 'electoral changes' in record['latest_event'].lower():
                        message = ':rotating_light: ' + message + ' :alarm_clock:'
                    self.slack_messages.append(message)

    def save(self):
        for key, record in self.data.items():
            scraperwiki.sqlite.save(
                unique_keys=['slug'], data=record, table_name='lgbce_reviews')

    def send_notifications(self):
        if not SEND_NOTIFICATIONS:
            return
        if SLACK_WEBHOOK_URL:
            for message in self.slack_messages:
                post_slack_message(message)
        if GITHUB_API_KEY:
            for issue in self.github_issues:
                raise_github_issue(issue['title'], issue['body'])

    def cleanup(self):
        # remove any stale records from the DB
        if not self.data:
            return
        placeholders = '(' + ', '.join(['?' for rec in self.data]) + ')'
        result = scraperwiki.sql.execute(
            "DELETE FROM 'lgbce_reviews' WHERE slug NOT IN " + placeholders,
            [slug for slug in self.data]
        )

    def scrape(self):
        self.scrape_index()
        self.attach_spider_data()
        if RUN_CHECKS:
            self.run_checks()
        self.make_notifications()
        self.save()
        self.send_notifications()
        self.cleanup()


if __name__ == '__main__':
    scraper = LgbceScraper()
    scraper.scrape()
