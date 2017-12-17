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
        scraper.BOOTSTRAP_MODE = False
        self.assertTrue(scraper.validate())

    def test_null_event(self):
        # latest_event = None
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        scraper.BOOTSTRAP_MODE = False
        with self.assertRaises(ScraperException) as e:
            scraper.validate()
        assert "Failed to populate 'latest_event' field" in str(e.exception)

    def test_completed_not_made(self):
        # status = 'Recently Completed' and ECO not made
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'The Allerdale Electoral Change order'
        scraper.data['allerdale']['eco_made'] = 0

        scraper.BOOTSTRAP_MODE = False
        with self.assertRaises(ScraperException) as e:
            scraper.validate()
        assert "Found 'completed' record which is not a made ECO" in str(e.exception)

    def test_new_completed(self):
        # status = 'Recently Completed' and record not in DB
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'The Allerdale Electoral Change order'
        scraper.data['allerdale']['eco_made'] = 1

        scraper.BOOTSTRAP_MODE = False
        with self.assertRaises(ScraperException) as e:
            scraper.validate()
        assert "New record found but status is 'Recently Completed'" in str(e.exception)

        # this check should be skipped in bootstrap mode
        scraper.BOOTSTRAP_MODE = True
        self.assertTrue(scraper.validate())

    def test_backwards_status_move(self):
        # old status is 'Recently Completed', new status is 'Current Reviews'
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'The Allerdale Electoral Change order'
        scraper.data['allerdale']['eco_made'] = 1
        scraper.save()
        scraper.data['allerdale']['status'] = scraper.CURRENT_LABEL

        scraper.BOOTSTRAP_MODE = False
        with self.assertRaises(ScraperException) as e:
            scraper.validate()
        assert "Record status has changed from 'Recently Completed' to 'Current Reviews'" in str(e.exception)

        # this check should be skipped in bootstrap mode
        scraper.BOOTSTRAP_MODE = True
        self.assertTrue(scraper.validate())

    def test_backwards_made_eco_move(self):
        # old eco_made value is 1, new value is 0
        scraper = LgbceScraper()
        scraper.data = {
            'allerdale': base_data['allerdale'].copy(),
        }
        scraper.data['allerdale']['latest_event'] = 'The Allerdale Electoral Change order'
        scraper.data['allerdale']['eco_made'] = 1
        scraper.data['allerdale']['status'] = scraper.CURRENT_LABEL
        scraper.save()
        scraper.data['allerdale']['eco_made'] = 0

        scraper.BOOTSTRAP_MODE = False
        with self.assertRaises(ScraperException) as e:
            scraper.validate()
        assert "'eco_made' field has changed from 1 to 0" in str(e.exception)

        # this check should be skipped in bootstrap mode
        scraper.BOOTSTRAP_MODE = True
        self.assertTrue(scraper.validate())
