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
import socket

from contextlib import closing


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


class Runtime(object):

    @staticmethod
    def setup(location):
        if not (os.path.exists(os.path.join(location, 'bin'))
                and os.path.isdir(os.path.join(location, 'bin'))):
            return False
        else:
            return True

    @staticmethod
    def find_open_ports(start_port, count):
        ports = []
        for port in range(start_port, 65535):
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(1)
                res = sock.connect_ex(('localhost', port))
                if res in (0, 111):
                    ports.append(port)
                    if len(ports) == count:
                        break
        return ports


    @staticmethod
    def run_command(command, capture_output=False):
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

class DockerRuntime(Runtime):
    @staticmethod
    def setup(location, name):
        output = Runtime.run_command(['docker', 'build', '-t', name, location], capture_output=True)
        return output[-1].startswith('Successfully tagged ' + name)

    @staticmethod
    def run_command(name, command, capture_output=False):
        output = Runtime.run_command(['docker', 'run', '-it', name] + command, capture_output=capture_output)
        if capture_output == True:
            return output

    @staticmethod
    def get_images():
        output = Runtime.run_command(['docker', 'images'], capture_output=True)
        return [l.split()[0] for l in output[1:]]

    @staticmethod
    def rm_image(image_name):
        output = Runtime.run_command(['docker', 'rmi', '-f', image_name], capture_output=True)
        return output
    
class DockerHelpers(object):
    pass
