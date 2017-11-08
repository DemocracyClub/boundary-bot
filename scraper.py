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


def post_slack_message(record):
    message = "Completed boundary review for %s: %s" % (record['name'], record['url'])
    slack = SlackClient(SLACK_WEBHOOK_URL)
    slack.post_message(message)


def raise_github_issue(record):
    owner = 'DemocracyClub'
    repo = 'EveryElection'
    title = 'Completed boundary review for %s' % (record['name'])
    body = "Completed boundary review for %s: %s" % (record['name'], record['url'])
    github = GitHubClient(GITHUB_API_KEY)
    github.raise_issue(owner, repo, title, body)


def scrape_bce_completed():
    # Boundary Commission for England

    urls = [] # URLs we've seen this scraper run

    html = scraperwiki.scrape("http://www.lgbce.org.uk/current-reviews")
    root = lxml.html.fromstring(html)

    h2_tags = root.cssselect('h2')
    for h2 in h2_tags:
        text = str(h2.text)
        if text == 'Recently Completed':
            # iterate over completed boundary reviews:
            for ul in h2.getnext().iterchildren():
                record = {}
                record['name'] = ul.findall('a')[0].text
                record['url'] = ul.findall('a')[0].get('href')
                urls.append(record['url'])

                try:
                    exists = scraperwiki.sql.select(
                        "* FROM 'bce_completed' WHERE url=?", record['url'])
                    if len(exists) == 0:
                        print(record)
                        if SLACK_WEBHOOK_URL and SEND_NOTIFICATIONS:
                            post_slack_message(record)
                        if GITHUB_API_KEY and SEND_NOTIFICATIONS:
                            raise_github_issue(record)
                except OperationalError:
                    # The first time we run the scraper it will throw
                    # because the table doesn't exist yet
                    pass

                scraperwiki.sqlite.save(
                    unique_keys=['url'], data=record, table_name='bce_completed')
                scraperwiki.sqlite.commit_transactions()

    # remove any stale records from the DB
    if urls:
        placeholders = '(' + ', '.join(['?' for url in urls]) + ')'
        result = scraperwiki.sql.execute(
            "DELETE FROM 'bce_completed' WHERE url NOT IN " + placeholders, urls)


scrape_bce_completed()
