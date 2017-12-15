import unittest
import scraperwiki
from scraper import LgbceScraper, ScraperException
from data_provider import base_data


class NotificationTests(unittest.TestCase):

    def setUp(self):
        scraperwiki.sqlite.execute("DROP TABLE IF EXISTS lgbce_reviews;")

    def test_no_events(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.data['babergh']['latest_event'] = 'foo'
        scraper.save()
        scraper.make_notifications()
        self.assertEqual(0, len(scraper.slack_helper.messages))
        self.assertEqual(0, len(scraper.github_helper.issues))

    def test_new_record(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.data['babergh']['latest_event'] = 'foo'
        scraper.make_notifications()
        self.assertEqual(1, len(scraper.slack_helper.messages))
        assert 'New boundary review found' in scraper.slack_helper.messages[0]
        self.assertEqual(0, len(scraper.github_helper.issues))

    def test_new_event(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.data['babergh']['latest_event'] = 'foo'
        scraper.save()
        scraper.data['babergh']['latest_event'] = 'bar'
        scraper.make_notifications()
        self.assertEqual(1, len(scraper.slack_helper.messages))
        assert "boundary review status updated to 'bar'" in scraper.slack_helper.messages[0]
        self.assertEqual(0, len(scraper.github_helper.issues))

    def test_status_changed(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.data['babergh']['latest_event'] = 'foo'
        scraper.save()
        scraper.data['babergh']['status'] = 'Recently Completed'
        scraper.make_notifications()
        self.assertEqual(1, len(scraper.slack_helper.messages))
        assert 'Completed boundary review' in scraper.slack_helper.messages[0]
        self.assertEqual(1, len(scraper.github_helper.issues))
        assert 'Completed boundary review' in scraper.github_helper.issues[0]['title']
        assert 'Completed boundary review' in scraper.github_helper.issues[0]['body']
