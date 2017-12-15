import unittest
import scraperwiki
from scraper import LgbceScraper, ScraperException
from data_provider import base_data


class ValidationTests(unittest.TestCase):

    def setUp(self):
        scraperwiki.sqlite.execute("DROP TABLE IF EXISTS lgbce_reviews;")

    def test_valid(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.data['babergh']['latest_event'] = 'foo'
        self.assertTrue(scraper.validate())

    def test_null_event(self):
        # latest_event = None
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        with self.assertRaises(ScraperException):
            scraper.validate()

    def test_new_completed(self):
        # status = 'Recently Completed' and record not in DB
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'foo'
        with self.assertRaises(ScraperException):
            scraper.validate()

        # this check should be skipped in bootstrap mode
        scraper.BOOTSTRAP_MODE = True
        self.assertTrue(scraper.validate())

    def test_backwards_move(self):
        # old status is 'Recently Completed', new status is 'Current Reviews'
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'foo'
        scraper.save()
        scraper.data['allerdale']['status'] = scraper.CURRENT_LABEL
        with self.assertRaises(ScraperException):
            scraper.validate()

        # this check should be skipped in bootstrap mode
        scraper.BOOTSTRAP_MODE = True
        self.assertTrue(scraper.validate())
