#!/usr/bin/env python
"""GoodCTZN dev command

Tool for managing the dev environment.

Argument parsing stuff borrowed from:
    https://gist.github.com/mivade/384c2c41c3a29c637cb6c603d4197f9f
"""
from __future__ import print_function

import shlex
import itertools
from collections import namedtuple
import hashlib
import urllib
import signal
import subprocess
import sys
import os
import pwd
import ConfigParser
import socket

from argparse import ArgumentParser
from contextlib import closing

get_docker_bin = lambda: subprocess.check_output(['which', 'docker']).strip()
get_toplevel_dir = lambda: subprocess.check_output(
    ["git", "rev-parse", "--show-toplevel"],
    stderr=subprocess.STDOUT)

working_dir = os.path.dirname(os.path.realpath(__file__))

cli = ArgumentParser()
subparsers = cli.add_subparsers(dest="subcommand")

additional_args = ['--build-arg', 'http_proxy=http://172.17.0.2:8080']
image_name_prefix = 'goodctzn-dev'
default_container_name = 'goodctzn-dev-sandbox'
default_docker_args = ['-p', '3000:3000',
                       '-p', '3001:3001',
                       '-p', '8000:8000',
                       '-p', '8080:8080',
                       '-it',
                       '-w', '/project',
                       '--mount', 'src=' + working_dir + ',target=/project,type=bind',
                       '--name', default_container_name]

download_dir = './.cache/download'
default_starting_port = 9000
default_project_mount_dir = '/project'


def find_dev_root(curdir):
    working_dir = curdir
    while True:
        test_location = os.path.join(working_dir, 'DEV_ROOT')

        if os.path.exists(test_location):
            return working_dir
        if working_dir == '/':
            raise Exception('Could not find DEV_ROOT')
        working_dir = os.path.dirname(working_dir)


def dev_root():
    return find_dev_root(os.getcwd())


def list_dev_runtimes(dev_dir):
    config = ConfigParser.SafeConfigParser()
    config.read(os.path.join(dev_dir, 'DEV_ROOT'))

    runtime_options = [op for op in config.options('dev') if op.startswith('runtime.')]

    dev_runtimes = set()
    for option in runtime_options:
        dev_runtimes.add(option.split('.')[1])

    return dev_runtimes

def get_runtime_config(dev_dir, runtime_name):
    config = ConfigParser.SafeConfigParser()
    config.read(os.path.join(dev_dir, 'DEV_ROOT'))

    runtime_options = [op for op in config.options('dev') if op.startswith('runtime.' + runtime_name)]

    opt_dict = {}
    for option in runtime_options:
        opt_dict['.'.join(option.split('.')[2:])] = config.get('dev', option)

    return opt_dict


def argument(*name_or_flags, **kwargs):
    """Convenience function to properly format arguments to pass to the
    subcommand decorator.
    """
    return (list(name_or_flags), kwargs)


def subcommand(args=[], parent=subparsers):
    """Decorator to define a new subcommand in a sanity-preserving way.
    The function will be stored in the ``func`` variable when the parser
    parses arguments so that it can be called directly like so::
        args = cli.parse_args()
        args.func(args)
    Usage example::
        @subcommand([argument("-d", help="Enable debug mode", action="store_true")])
        def subcommand(args):
            print(args)
    Then on the command line::
        $ python cli.py subcommand -d
    """
    def decorator(func):
        parser = parent.add_parser(func.__name__,
                                   help=func.__doc__.split('\n')[0],
                                   description=func.__doc__)
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
        parser.set_defaults(func=func)
        return func
    return decorator


running_processes = []

def command_signal_handler(signum, frame):
    print("HERE!")
    for proc in running_processes:
        proc.kill()

signal.signal(signal.SIGINT, command_signal_handler)

def run_command(command, replace_current_term=False, capture_output=False):
    print(' '.join(command))
    if replace_current_term:
        os.execv(command[0], command)
    else:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)

        running_processes.append(process)

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

def find_open_ports():
    for port in range(default_starting_port, default_starting_port+1000):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            res = sock.connect_ex(('localhost', port))
            if res == 0:
                yield port

def get_docker_args(container_name, pkg_dir):
    # build port args
    baseport = 9000
    portargs = []

    for n, portnum in itertools.izip(range(10), find_open_ports()):
        portargs.extend(('-p', '%(portnum)d:%(portnum)d' % {'portnum': portnum}))

    rel_pkg_dir = pkg_dir[len(dev_root())+1:]

    docker_args = portargs + [
        '-p', '3000:3000',
        '-p', '3001:3001',
        '-p', '8000:8000',
        '-p', '8080:8080',
        '-it',
        '-e', 'BUILDDIR=' + os.path.join(default_project_mount_dir, 'build', rel_pkg_dir),
        '-w', os.path.join(default_project_mount_dir, rel_pkg_dir),
        '--mount', 'src=' + dev_root() + ',target=' +  default_project_mount_dir + ',type=bind',
        '--name', container_name]

    return docker_args

def run_command_in_sandbox(command=(), additional_args=(), container_name=default_container_name, replace_current_term=False,
                           pkg_dir='.', runtime='dev'):
    new_command = list(itertools.chain([get_docker_bin(), 'run'],
                                       ['--rm'],
                                       get_docker_args(container_name=container_name,
                                                       pkg_dir=pkg_dir),
                                       additional_args,
                                       ['-'.join([image_name_prefix, runtime])],
                                       command))


    run_command(new_command, replace_current_term=replace_current_term)


DependencyInfo = namedtuple('DependencyInfo', ['url', 'sha256'])


def hashfile(filename):
    sha256_hash = hashlib.sha256()
    with open(filename, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_runtime_depends(runtime_location):
    config = ConfigParser.SafeConfigParser()
    config.read(os.path.join(runtime_location, 'DEV'))

    depends = []

    output_runtime_location = os.path.join(dev_root(), 'build', 'runtime')
    download_dir = os.path.join(output_runtime_location, '.cache/downloads')

    if (not os.path.exists(download_dir)):
        os.makedirs(download_dir)

    for dep in set(d.split('.')[0] for d in config.options('dependencies')):
        url = config.get('dependencies', dep + '.location')
        dephash = config.get('dependencies', dep + '.sha256')

        filename = os.path.basename(url)
        dest_filename = os.path.join(download_dir, filename)

        if os.path.exists(dest_filename):
            if (hashfile(dest_filename) == dephash):
                continue
            else:
                print("removing file with bad hash: " + dest_filename)
                os.remove(dest_filename)

        print("Downloading: ", url)
        urllib.urlretrieve(url, dest_filename)

        if (hashfile(dest_filename) != dephash):
            raise Exception("Dependency %s doesn't match hash." % url)


def build_runtime(runtime):

    docker_template_filename = os.path.join(dev_root(), 'runtime_configs', 'Dockerfile.' + runtime + '.template')
    docker_config_output_filename = os.path.join(dev_root(), 'build', 'runtime', 'Dockerfile.' + runtime)

    with open(docker_template_filename) as template:
        output = template.read()
        parsed_output = output.replace(
            '%%UID%%', str(pwd.getpwuid(os.getuid()).pw_uid))
        with open(docker_config_output_filename, 'w') as outfile:
            outfile.write(parsed_output)

    command = (['docker', 'build', '-t', '-'.join([image_name_prefix + runtime])]
               + ['-f', docker_config_output_filename, os.path.dirname(docker_config_output_filename)])

    return run_command(command)


@subcommand([argument('package', default=None, nargs=1, help='package to watch'),])
def build(args):
    """Build the project"""

    full_path, pkg_config = get_pkg_info(args.package[0])

    init_command = shlex.split(pkg_config['command.init'])
    run_command_in_sandbox(init_command,
                           container_name=default_container_name + 'build',
                           pkg_dir = full_path,
                           runtime=pkg_config['runtime'])

    build_command = shlex.split(pkg_config['command.build'])
    run_command_in_sandbox(build_command,
                           container_name=default_container_name + 'build',
                           pkg_dir = full_path,
                           runtime=pkg_config['runtime'])



@subcommand()
def clean(args):
    """Clean the source directory, removing build artifacts"""
    command = (['rm', '-r', os.path.join(default_project_mount_dir, 'build')])
    return run_command_in_sandbox(command)


@subcommand()
def clean_image(args):
    """Remove the build image"""
    command = ['docker', 'rmi', image_name]
    return run_command(command)


@subcommand()
def connect(args):
    """Connect to the running dev container"""

    command = ([get_docker_bin(), 'exec', '-it', container_name,
                '/bin/bash', '-l'])
    run_command(command, replace_current_term=True)


@subcommand()
def init(args):
    """Initialize the dev environment"""
    get_runtime_depends(os.path.join(dev_root(), 'runtime_configs'))

    for runtime in list_dev_runtimes(dev_root()):
        build_runtime(runtime)


def get_pkg_info(pkg_path):
    """Parse package paths

    Given a path like: path/to:somepackage (copying bazel's format)

    return the full path to the package and its configuration
    """

    parts = pkg_path.split(':')

    if len(parts) != 2:
        raise Exception('the package identifier must be of the form //path/to:pacakge or path/to:package')

    package_name = parts[1]

    if pkg_path.startswith('//'):
            full_path = os.path.join(
            dev_root(),
            parts[0][2:], # strip the first two slashes
            parts[1])
    else:
        full_path = os.path.join(
            os.getcwd(),
            parts[0],
            parts[1]
        )

    config = ConfigParser.SafeConfigParser()
    config.read(os.path.join(os.path.dirname(full_path), 'DEV'))

    pkg_config = {}
    for option in config.options(package_name):
        pkg_config[option] = config.get(package_name, option)

    return full_path, pkg_config



@subcommand([argument('package', default=None, nargs=1, help='package to watch'),])
def shell(args):
    """Open a shell in a dev container"""
    command = ('/bin/bash', '-l')

    full_path, pkg_config = get_pkg_info(args.package[0])

    run_command_in_sandbox(command, replace_current_term=True,
                           container_name=default_container_name + 'shell',
                           pkg_dir=full_path,
                           runtime=pkg_config['runtime'])


@subcommand()
def show_root(args):
    """Print the root Dev directory"""
    print(find_dev_root(os.getcwd()))


@subcommand()
def show_runtimes(args):
    """Print a list of available runtimes"""
    for runtime in list_dev_runtimes(find_dev_root(os.getcwd())):
        print(runtime)


@subcommand()
def start(args):
    """Start the dev container"""
    command = (['docker', 'run', '-d']
               + default_docker_args
               + [image_name])

    return run_command_in_sandbox(additional_args=['-d'])


@subcommand()
def stop(args):
    """Stop the dev container"""
    command = ('docker', 'rm', '-f', container_name)
    return run_command(command)


@subcommand()
def test(args):
    """Run all tests"""
    command = (['python', '-m',
                'unittest', 'discover', '-v', '-p', '*_test.py'])
    return run_command_in_sandbox(command,
                                  container_name=container_name + '-test')


@subcommand([argument('package', default=None, nargs=1, help='package to watch'),])
def watch(args):
    """Watch dev changes. (example: path/to:package)"""

    full_path, pkg_config = get_pkg_info(args.package[0])

    init_command = shlex.split(pkg_config['command.init'])
    run_command_in_sandbox(init_command,
                           container_name='-'.join([default_container_name, 'watch']),
                           pkg_dir = full_path,
                           runtime=pkg_config['runtime'])

    watch_command = shlex.split(pkg_config['command.watch'])
    run_command_in_sandbox(watch_command, replace_current_term=True,
                           container_name='-'.join([default_container_name, 'watch']),
                           pkg_dir = full_path,
                           runtime=pkg_config['runtime'])


def get_all_dev_containers():
    command = ('docker', 'ps', '--filter', 'name=%s.*' % default_container_name, '--format', '{{.ID}}')
    return run_command(command, capture_output=True)

@subcommand()
def show_running_sandboxes(args):
    """Show the running sandbox IDs"""
    for i in get_all_dev_containers():
        print(i)


@subcommand()
def killall(args):
    """Kill all the running dev containers"""

    command = ['docker', 'kill'] + get_all_dev_containers()
    run_command(command)


if __name__ == "__main__":
    args = cli.parse_args()
    if args.subcommand is None:
        cli.print_help()
    else:
        sys.exit(args.func(args))
