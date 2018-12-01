#!/usr/bin/env python

from __future__ import print_function

import os

### start Dev repo helpers

def find_dev_root(curdir):
    working_dir = curdir
    while True:
        test_location = os.path.join(working_dir, 'DEV_ROOT')

        if os.path.exists(test_location):
            return working_dir
        if working_dir == '/':
            raise Exception('Could not find DEV_ROOT')
        working_dir = os.path.dirname(working_dir)

### end Dev repo helpers

