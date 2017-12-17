import os
import unittest
from scraper import LgbceScraper, ScraperException
from data_provider import base_data

class IndexParserTests(unittest.TestCase):

    def get_fixture(self, fixture):
        dirname = os.path.dirname(os.path.abspath(__file__))
        fixture_path = os.path.abspath(os.path.join(dirname, fixture))
        return open(fixture_path).read()

    def test_parse_valid(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/index/valid.html')
        scraper.parse_index(fixture)
        self.assertEqual(4, len(scraper.data))
        self.assertDictEqual(base_data['babergh'], scraper.data['babergh'])
        self.assertDictEqual(base_data['basingstoke-and-deane'], scraper.data['basingstoke-and-deane'])
        self.assertDictEqual(base_data['allerdale'], scraper.data['allerdale'])
        self.assertDictEqual(base_data['ashford'], scraper.data['ashford'])

    def test_parse_unexpected_heading(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/index/unexpected_heading.html')
        with self.assertRaises(ScraperException):
            scraper.parse_index(fixture)

    def test_parse_missing_heading(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/index/missing_heading.html')
        with self.assertRaises(ScraperException):
            scraper.parse_index(fixture)