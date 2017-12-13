import os
import unittest
from scraper import LgbceScraper, ScraperException

class IndexParserTests(unittest.TestCase):

    def get_fixture(self, fixture):
        dirname = os.path.dirname(os.path.abspath(__file__))
        fixture_path = os.path.abspath(os.path.join(dirname, fixture))
        return open(fixture_path).read()

    def test_parse_valid(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/valid.html')
        scraper.parse_index(fixture)
        self.assertEqual(4, len(scraper.data))
        self.assertDictEqual({
            'slug': 'babergh',
            'name': 'Babergh',
            'url': 'http://www.lgbce.org.uk/current-reviews/eastern/suffolk/babergh',
            'status': 'Current Reviews',
            'latest_event': None,
        }, scraper.data['babergh'])
        self.assertDictEqual({
            'slug': 'basingstoke-and-deane',
            'name': 'Basingstoke and Deane',
            'url': 'http://www.lgbce.org.uk/current-reviews/south-east/hampshire/basingstoke-and-deane',
            'status': 'Current Reviews',
            'latest_event': None,
        }, scraper.data['basingstoke-and-deane'])
        self.assertDictEqual({
            'slug': 'allerdale',
            'name': 'Allerdale',
            'url': 'http://www.lgbce.org.uk/current-reviews/north-west/cumbria/allerdale',
            'status': 'Recently Completed',
            'latest_event': None,
        }, scraper.data['allerdale'])
        self.assertDictEqual({
            'slug': 'ashford',
            'name': 'Ashford',
            'url': 'http://www.lgbce.org.uk/current-reviews/south-east/kent/ashford',
            'status': 'Recently Completed',
            'latest_event': None,
        }, scraper.data['ashford'])

    def test_parse_unexpected_heading(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/unexpected_heading.html')
        with self.assertRaises(ScraperException):
            scraper.parse_index(fixture)

    def test_parse_missing_heading(self):
        scraper = LgbceScraper()
        fixture = self.get_fixture('fixtures/missing_heading.html')
        with self.assertRaises(ScraperException):
            scraper.parse_index(fixture)
