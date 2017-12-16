import unittest
from unittest import mock
from scraper import LgbceScraper, ScraperException
from data_provider import base_data


def mock_run_spider(obj):
    return [
        {
            "slug": "basingstoke-and-deane",
            "latest_event": "Consultation on warding arrangements"
        },
        {
            "slug": "babergh",
            "latest_event": "The Babergh (Electoral Changes) Order 2017"
        }
    ]


class AttachSpiderTests(unittest.TestCase):

    @mock.patch("scraper.SpiderWrapper.run_spider", mock_run_spider)
    def test_valid(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
            'basingstoke-and-deane': base_data['basingstoke-and-deane'].copy(),
        }
        scraper.attach_spider_data()
        self.assertEqual(
            "The Babergh (Electoral Changes) Order 2017",
            scraper.data['babergh']['latest_event']
        )
        self.assertEqual(
            "Consultation on warding arrangements",
            scraper.data['basingstoke-and-deane']['latest_event']
        )

    @mock.patch("scraper.SpiderWrapper.run_spider", mock_run_spider)
    def test_unexpected(self):
        scraper = LgbceScraper()
        scraper.data = {
            'babergh': base_data['babergh'].copy(),
        }
        with self.assertRaises(ScraperException):
            scraper.attach_spider_data()
