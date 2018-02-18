from boundary_bot.scraper import LgbceScraper


"""
Set BOOTSTRAP_MODE to True to initialize an empty DB

If we are starting with an empty database we want to
- ensure we don't send any notifications and
- disable some consistency checks
"""
BOOTSTRAP_MODE = False
SEND_NOTIFICATIONS = not(BOOTSTRAP_MODE)


if __name__ == '__main__':
    scraper = LgbceScraper(BOOTSTRAP_MODE, SEND_NOTIFICATIONS)
    scraper.scrape()
