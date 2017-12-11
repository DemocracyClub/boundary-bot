import lxml.html
import os
from polling_bot.brain import SlackClient, GitHubClient
from sqlalchemy.exc import OperationalError

# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///data.sqlite'
import scraperwiki


SEND_NOTIFICATIONS = True

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


class LgbceScraper:

    BASE_URL = "http://www.lgbce.org.uk/current-reviews"
    CURRENT_LABEL = 'Current Reviews'
    COMPLETED_LABEL = 'Recently Completed'

    def __init__(self):
        scraperwiki.sql.execute("""
            CREATE TABLE IF NOT EXISTS lgbce_reviews (
                slug TEXT PRIMARY KEY,
                name TEXT,
                url TEXT,
                status TEXT,
                latest_status TEXT
            );""")
        self.data = {}
        self.slack_messages = []
        self.github_issues = []

    def scrape_index(self):
        html = scraperwiki.scrape(self.BASE_URL)
        root = lxml.html.fromstring(html)

        h2_tags = root.cssselect('h2')
        for h2 in h2_tags:
            text = str(h2.text)
            if text in [self.CURRENT_LABEL, self.COMPLETED_LABEL]:
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

            if len(result) > 1:
                raise Exception('Human sacrifice, dogs and cats living together, mass hysteria!')


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
        self.make_notifications()
        self.save()
        self.send_notifications()
        self.cleanup()


scraper = LgbceScraper()
scraper.scrape()
