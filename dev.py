#!/usr/bin/env python
"""Dev repository tool

The goal of this tool is to support a unified development environment for an 
organization. 

Development notes:

As much as possible this system is designed to work with python 2.7 and be a 
single file that can just be copied or symlinked into place and not require 
any installation.
"""
from __future__ import print_function

import ConfigParser
import subprocess
import os


class Repo(object):
    @staticmethod
    def get_dev_root(curdir):
        """Find the root of the Dev repo"""

        working_dir = curdir
        while True:
            test_location = os.path.join(working_dir, 'DEV_ROOT')

            if os.path.exists(test_location):
                return working_dir
            if working_dir == '/':
                raise Exception('Could not find DEV_ROOT')
            working_dir = os.path.dirname(working_dir)

    @staticmethod
    def get_dev_config(directory):
        """Get the Dev configuration for the given package"""

        if not os.path.exists(os.path.join(os.path.dirname(directory), 'DEV')):
            raise Exception("DEV config doesn't exist for %s" % directory)

        config = ConfigParser.SafeConfigParser()
        config.read(os.path.join(os.path.dirname(directory), 'DEV'))

        return config
   

class Commands(object):
    @staticmethod
    def run_command(command, replace_current_term=False, capture_output=False):
        if replace_current_term:
            os.execv(command[0], command)
        else:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT)

            output = []
            for stdout_line in iter(process.stdout.readline, ""):
                if capture_output:
                    output.append(stdout_line.strip())
                else:
                    print(stdout_line, end='')

            process.stdout.close()
            return_code = process.wait()
            if return_code:
                raise subprocess.CalledProcessError(return_code, command)
        return output


class DockerHelpers(object):
    pass
