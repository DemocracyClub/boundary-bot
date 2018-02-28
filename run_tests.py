#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import unittest


if __name__ == '__main__':
    os.environ['SCRAPERWIKI_DATABASE_NAME'] = 'sqlite:///:memory:'
    dirname = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    tests = loader.discover(os.path.abspath(os.path.join(dirname, 'tests')))
    runner = unittest.runner.TextTestRunner()
    result = runner.run(tests)
    sys.exit(not result.wasSuccessful())
