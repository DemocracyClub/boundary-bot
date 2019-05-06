# boundary-bot

[![Build Status](https://travis-ci.org/DemocracyClub/boundary-bot.svg?branch=master)](https://travis-ci.org/DemocracyClub/boundary-bot)
[![Coverage Status](https://coveralls.io/repos/github/DemocracyClub/boundary-bot/badge.svg?branch=master)](https://coveralls.io/github/DemocracyClub/boundary-bot?branch=master)

## About

Tooling for the [Every Election](https://elections.democracyclub.org.uk/) project. A small scraper app to:

* Scrape information on current and recent boundary reviews from [LGBCE](http://www.lgbce.org.uk/)
* Store it in a SQLite database
* Commit the data to a [GitHub repo](https://github.com/DemocracyClub/boundary-data)
* Raise slack notifications about status changes
* Raise GitHub issues about completed reviews on the [Every Election](https://github.com/DemocracyClub/EveryElection) repo

It can optionally be run on [morph.io](https://morph.io/)

## Setup

`pip install -r requirements.txt`

## Configuration

Configuration is performed using env vars.

* To commit the scraped data to a GitHub repo, set the following env vars:

    ```sh
    MORPH_GITHUB_BOUNDARY_REPO = "DemocracyClub/boundary-data"
    MORPH_GITHUB_USERNAME = "polling-bot-4000"
    MORPH_GITHUB_EMAIL = "user@example.com"
    MORPH_GITHUB_API_KEY = "abc123"
    ```

    `MORPH_GITHUB_API_KEY` will need push access to the repo.

* To raise slack notifications about status changes, set:

    ```sh
    MORPH_BOUNDARY_BOT_SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/foo/bar/baz"
    ```

* To raise GitHub issues about completed reviews on the [Every Election](https://github.com/DemocracyClub/EveryElection) repo, set:

    ```sh
    MORPH_GITHUB_ISSUE_ONLY_API_KEY = "abc123"
    ```

    `MORPH_GITHUB_ISSUE_ONLY_API_KEY` does not need any special permissions.

## Running

When running for the first time, set `BOOTSTRAP_MODE = True` in `scraper.py`

For all future runs, set `BOOTSTRAP_MODE = False`

`python scraper.py`
