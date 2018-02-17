import datetime
import json
import lxml.html
import os
import pprint
import requests
import scrapy
import tempfile
from collections import OrderedDict
from commitment import GitHubCredentials
from commitment import GitHubClient as GitHubSyncClient
from polling_bot.brain import SlackClient
from polling_bot.brain import GitHubClient as GitHubIssueClient
from scrapy.crawler import CrawlerProcess

# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
if not 'SCRAPERWIKI_DATABASE_NAME' in os.environ:
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
REQUEST_HEADERS = {'Cache-Control': 'max-age=20000'}


try:
    SLACK_WEBHOOK_URL = os.environ['MORPH_BOUNDARY_BOT_SLACK_WEBHOOK_URL']
except KeyError:
    SLACK_WEBHOOK_URL = None

try:
    GITHUB_API_KEY = os.environ['MORPH_GITHUB_ISSUE_ONLY_API_KEY']
except KeyError:
    GITHUB_API_KEY = None


def is_eco(event):
    return 'electoral change' in event.lower()


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
        if is_eco(record['latest_event']):
            message = ':rotating_light: ' + message + ' :alarm_clock:'
        self.messages.append(message)

    def post_messages(self):
        client = SlackClient(SLACK_WEBHOOK_URL)
        for message in self.messages:
            client.post_message(message)


class GitHubIssueHelper:

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
        client = GitHubIssueClient(GITHUB_API_KEY)
        for issue in self.issues:
            client.raise_issue(owner, repo, issue['title'], issue['body'])


class GitHubSyncHelper:

    def get_github_credentials(self):
        return GitHubCredentials(
            repo=os.environ['MORPH_GITHUB_BOUNDARY_REPO'],
            name=os.environ['MORPH_GITHUB_USERNAME'],
            email=os.environ['MORPH_GITHUB_EMAIL'],
            api_key=os.environ['MORPH_GITHUB_API_KEY']
        )

    def sync_file_to_github(self, file_name, content):
        try:
            creds = self.get_github_credentials()
            g = GitHubSyncClient(creds)
            g.push_file(content, file_name, 'Update %s at %s' %\
                (file_name, str(datetime.datetime.now())))
        except KeyError:
            # if no credentials are defined in env vars
            # just ignore this step
            pass


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
    BOOTSTRAP_MODE = BOOTSTRAP_MODE
    SEND_NOTIFICATIONS = SEND_NOTIFICATIONS

    def __init__(self):
        scraperwiki.sql.execute("""
            CREATE TABLE IF NOT EXISTS %s (
                slug TEXT PRIMARY KEY,
                name TEXT,
                url TEXT,
                status TEXT,
                latest_event TEXT,
                shapefiles TEXT,
                eco_made INT DEFAULT 0
            );""" % self.TABLE_NAME)
        self.data = {}
        self.slack_helper = SlackHelper()
        self.github_helper = GitHubIssueHelper()

    def scrape_index(self):
        headers = REQUEST_HEADERS
        r = requests.get(BASE_URL, headers=headers)
        return r.text

    def parse_index(self, html):
        expected_headings = [self.CURRENT_LABEL, self.COMPLETED_LABEL]
        root = lxml.html.fromstring(html)

        h2_tags = root.cssselect('h2')

        found_headings = [h2.text for h2 in h2_tags]
        if expected_headings != found_headings:
            raise ScraperException(
                "Unexpected headings: Found %s, expected %s" %\
                (str(found_headings), str(expected_headings))
            )

        for h2 in h2_tags:
            text = str(h2.text)
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
                    'shapefiles': None,
                    'eco_made': 0,
                }


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
            self.data[area['slug']]['shapefiles'] = area['shapefiles']
            self.data[area['slug']]['eco_made'] = area['eco_made']

    def validate(self):
        # perform some consistency checks
        # and raise an error if unexpected things have happened
        for key, record in self.data.items():

            if record['status'] == self.COMPLETED_LABEL and record['eco_made'] == 0:
                # everything in 'Recently Completed' should be a made ECO
                raise ScraperException(
                    "Found 'completed' record which is not a made ECO:\n%s" % (str(record)))

            if self.BOOTSTRAP_MODE:
                # skip the next checks if we are initializing an empty DB
                return True

            result = scraperwiki.sql.select(
                "* FROM %s WHERE slug=?" % (self.TABLE_NAME), record['slug'])

            if len(result) == 0 and record['status'] == self.COMPLETED_LABEL:
                # we shouldn't have found a record for the first time when it is completed
                # we should find it under review and then it should move to completed
                raise ScraperException(
                    "New record found but status is '%s':\n%s" %\
                    (self.COMPLETED_LABEL, str(record))
                )

            if len(result) == 1 and record['latest_event'] is None and result[0]['latest_event'] != '':
                # the review isn't brand new and we've failed to scrape the latest review event
                raise ScraperException(
                    "Failed to populate 'latest_event' field:\n%s" % (str(record)))

            if len(result) == 1 and record['status'] == self.CURRENT_LABEL and result[0]['status'] == self.COMPLETED_LABEL:
                # reviews shouldn't move backwards from completed to current
                raise ScraperException(
                    "Record status has changed from '%s' to '%s':\n%s" %\
                    (self.COMPLETED_LABEL, self.CURRENT_LABEL, str(record))
                )

            if len(result) == 1 and record['eco_made'] == 0 and result[0]['eco_made'] == 1:
                # reviews shouldn't move backwards from made to not made
                raise ScraperException(
                    "'eco_made' field has changed from 1 to 0:\n%s" % (str(record))
                )

            if len(result) > 1:
                # society has collapsed :(
                raise ScraperException(
                    'Human sacrifice, dogs and cats living together, mass hysteria!')
        return True

    def pre_process(self):
        for key, record in self.data.items():
            if record['latest_event'] is None:
                record['latest_event'] = ''

    def make_notifications(self):
        for key, record in self.data.items():
            result = scraperwiki.sql.select(
                "* FROM %s WHERE slug=?" % (self.TABLE_NAME), record['slug'])

            if len(result) == 0:
                # we've not seen this boundary review before
                self.slack_helper.append_new_review_message(record)

            if len(result) == 1:
                # we've already got our eye on this one
                if is_eco(record['latest_event']) and\
                        result[0]['eco_made'] == 0 and\
                        record['eco_made'] == 1:
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

        if not self.SEND_NOTIFICATIONS:
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

    def dump_table_to_json(self):
        records = scraperwiki.sqlite.select(
            " * FROM %s ORDER BY slug;" % (self.TABLE_NAME))
        return json.dumps(
            [OrderedDict(sorted(rec.items())) for rec in records],
            sort_keys=True, indent=4)

    def sync_db_to_github(self):
        content = self.dump_table_to_json()
        g = GitHubSyncHelper()
        g.sync_file_to_github('lgbce.json', content)

    def scrape(self):
        self.parse_index(self.scrape_index())
        self.attach_spider_data()
        self.validate()
        self.pre_process()
        self.make_notifications()
        self.save()
        self.send_notifications()
        self.cleanup()
        self.sync_db_to_github()


if __name__ == '__main__':
    scraper = LgbceScraper()
    scraper.scrape()
