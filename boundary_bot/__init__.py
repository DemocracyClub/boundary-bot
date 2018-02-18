import os

# hack to override sqlite database filename
# see: https://help.morph.io/t/using-python-3-with-morph-scraperwiki-fork/148
if not 'SCRAPERWIKI_DATABASE_NAME' in os.environ:
    os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///data.sqlite'
