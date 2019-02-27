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
import copy
import json
import os
import pwd
import re
import shlex
import signal
import socket
import string
import subprocess
import sys

from argparse import ArgumentParser
from contextlib import closing

RuntimeProviders = {}
cli = ArgumentParser()
subparsers = cli.add_subparsers(dest="subcommand")


class DevRepoException(Exception):
    pass


class Repo(object):
    @staticmethod
    def get_dev_root(curdir):
        """Find the root of the Dev repo"""

        working_dir = os.path.realpath(curdir)
        while True:
            if working_dir in ("/", ""):
                raise Exception("Could not find DEV_ROOT")

            test_location = os.path.join(working_dir, "DEV_ROOT")

            if os.path.exists(test_location):
                return working_dir
            working_dir = os.path.dirname(working_dir)


class ConfigHelpers(object):
    @staticmethod
    def parse_config(config_file):
        """Reads a standard ini config and converts it to a dev dictionary
        
        What it does is takes an
        """


class GlobalConfig(object):
    @staticmethod
    def get(dev_tree):
        dev_root = Repo.get_dev_root(dev_tree)
        with open(os.path.join(dev_root, "DEV_ROOT")) as f:
            global_config = json.load(f)
        return global_config

    @staticmethod
    def get_runtimes(dev_tree):
        config = GlobalConfig.get(dev_tree)
        return sorted(config["runtimes"].keys())

    @staticmethod
    def get_runtime_config(dev_tree, runtime_name):
        config = GlobalConfig.get(dev_tree)
        if runtime_name not in config["runtimes"]:
            raise DevRepoException(
                "Runtime %s doesn't exist in the config for dev repo %s"
                % (runtime_name, dev_tree)
            )
        else:
            return config["runtimes"][runtime_name]


class ProjectConfig(object):
    @staticmethod
    def _parse_project_path(dev_tree, project_path, require_project_name=True):
        if not dev_tree.startswith("/"):
            raise DevRepoException(
                "Dev tree path has to be an absolute path to a location inside a dev repo. Got %s instead."
                % dev_tree
            )

        if not project_path.startswith("//"):
            if ":" in project_path:
                pre_path, proj_name = project_path.split(":")
            elif not require_project_name:
                pre_path, proj_name = (project_path, None)
            else:
                raise DevRepoException(
                    "Project name required but not found in project path. Recieved: %s"
                    % project_path
                )

            full_proj_path = os.path.realpath(os.path.join(dev_tree, pre_path))

            root_path = Repo.get_dev_root(dev_tree)
            path_prefix = full_proj_path[len(root_path) :].split("/")

            new_project_path = "//%s" % (os.path.join(*path_prefix))

            if proj_name:
                new_project_path = "%s:%s" % (new_project_path, proj_name)

            dev_tree = root_path
            project_path = new_project_path

        parts = re.match(
            "^//(?P<path>[^:]*)(?P<project>:[A-Za-z0-9_-]+)?$", project_path
        )
        if not parts:
            raise DevRepoException("Bad project path: %s" % project_path)

        project_parent_dir = os.path.join(dev_tree, parts.groupdict()["path"])
        project_name = parts.groupdict()["project"]

        if require_project_name and not project_name:
            raise DevRepoException("No project name specified.")
        elif not require_project_name and (project_name is not None):
            raise DevRepoException("Project should not be specified.")

        # strip the colon from the project name
        if project_name:
            project_name = project_name[1:]

        return project_parent_dir, project_name

    @staticmethod
    def _merge_config_with_default_dict(config, default_dict):
        new_config = copy.deepcopy(default_dict)
        for key, value in config.items():
            if key not in default_dict:
                new_config[key] = value
                continue
            elif isinstance(value, dict):
                new_config[key] = ProjectConfig._merge_config_with_default_dict(
                    value, default_dict[key]
                )
            else:
                new_config[key] = value
        return new_config

    @staticmethod
    def lookup_config(dev_tree, project_path):
        project_parent_dir, project_name = ProjectConfig._parse_project_path(
            dev_tree, project_path
        )

        dev_file_path = os.path.join(project_parent_dir, "DEV")
        if not os.path.exists(dev_file_path):
            raise DevRepoException(
                "DEV file doesn't exist in given path: %s" % (dev_file_path)
            )

        with open(dev_file_path) as f:
            full_config = json.load(f)

        if project_name not in full_config:
            raise DevRepoException(
                "Project %s doesn't exist at %s" % (project_name, project_parent_dir)
            )

        global_config = GlobalConfig.get(dev_tree)

        return ProjectConfig._merge_config_with_default_dict(
            full_config[project_name], global_config["project_defaults"]
        )

    @staticmethod
    def list_projects(dev_tree_path):
        project_parent_dir, _ = ProjectConfig._parse_project_path(
            dev_tree_path, project_path="", require_project_name=False
        )

        with open(os.path.join(project_parent_dir, "DEV")) as f:
            full_config = json.load(f)

        return sorted(map(lambda x: ":%s" % x, full_config.keys()))

    @staticmethod
    def get_commands(proj_config):
        if "commands" not in proj_config:
            return {}

        return proj_config["commands"]

    @staticmethod
    def _build_tmpl_vars(dev_tree, project_path, runtime_config):
        project_parent_dir, project_name = ProjectConfig._parse_project_path(
            dev_tree, project_path
        )
        config = ProjectConfig.lookup_config(dev_tree, project_path)

        vardict = {
            "CWD": os.path.realpath(
                os.path.join(dev_tree, project_parent_dir, config["path"])
            ),
            "BUILDDIR": os.path.realpath(
                os.path.join(
                    dev_tree,
                    "build",
                    project_parent_dir[len(dev_tree) + 1 :],
                    project_name,
                )
            ),
            "PROJNAME": project_name,
            "WORKINGDIR": runtime_config.get(
                "workingdir",
                os.path.realpath(
                    os.path.join(dev_tree, project_parent_dir, config["path"])
                ),
            ),
        }
        return vardict

    @staticmethod
    def _render_value(raw_value, tmpl_vars):
        return string.Template(raw_value).substitute(tmpl_vars)

    @staticmethod
    def _render_config(val, tmpl_vars):
        if isinstance(val, basestring):
            return ProjectConfig._render_value(val, tmpl_vars)
        elif isinstance(val, dict):
            new_val = {}
            for k, v in val.iteritems():
                new_val[k] = ProjectConfig._render_config(val[k], tmpl_vars)
            return new_val
        elif isinstance(val, list):
            new_val = []
            for v in val:
                new_val.append(ProjectConfig._render_config(v, tmpl_vars))
            return new_val
        elif isinstance(val, bool):
            return val
        else:
            raise DevRepoException("Unrecognized value: %s" % val)

    @staticmethod
    def run_project_command(dev_tree, project_path, command, verbose=None):
        project_config = ProjectConfig.lookup_config(dev_tree, project_path)
        proj_commands = ProjectConfig.get_commands(project_config)

        if command not in proj_commands:
            raise DevRepoException(
                "Command %s doesn't exist for project %s" % (command, project_path)
            )

        runtime_name = project_config["runtime"]

        raw_runtime_config = GlobalConfig.get_runtime_config(dev_tree, runtime_name)
        tmpl_vars = ProjectConfig._build_tmpl_vars(
            dev_tree, project_path, raw_runtime_config
        )

        runtime_config = ProjectConfig._render_config(raw_runtime_config, tmpl_vars)
        full_command = ProjectConfig._render_value(proj_commands[command], tmpl_vars)

        if verbose != None:
            runtime_config["verbose"] = verbose

        if (
            "commands_runtime_config" in project_config
            and command in project_config["commands_runtime_config"]
        ):
            runtime_config["extra_runtime_config"] = project_config[
                "commands_runtime_config"
            ][command]

        return Runtime.run_command(dev_tree, runtime_config, full_command)


class Runtime(object):
    @staticmethod
    def get_provider(config):
        if "provider" not in config:
            raise DevRepoException("No provider specified in config:\n %s" % config)

        return RuntimeProviders[config["provider"]]

    @staticmethod
    def run_command(dev_tree, config, command):
        provider = Runtime.get_provider(config)

        if (not provider.is_ready(config)) and ("project" in config):
            ProjectConfig.run_project_command(dev_tree, config["project"], "build")

        return provider.run_command(config, command)

    @staticmethod
    def find_open_ports(start_port, count):
        ports = []
        for port in range(start_port, 65535):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            with closing(sock):
                sock.settimeout(1)
                try:
                    sock.bind(("localhost", port))
                except IOError as e:
                    if e.errno is 98:  # Errorno 98 means address already bound
                        continue
            ports.append(port)
            if len(ports) == count:
                break
        else:
            raise DevRepoException("Ran out of available ports.")

        return ports


def register_runtime_provider(name):
    def do_register(cls):
        RuntimeProviders[name] = cls
        return cls

    return do_register


@register_runtime_provider("local")
class LocalRuntimeProvider(object):
    @staticmethod
    def is_ready(config):
        return True

    @staticmethod
    def setup(location):
        return True

    @staticmethod
    def run_command(config, command):
        if isinstance(command, basestring):
            command = shlex.split(command)

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=config.get("cwd", None),
            bufsize=0,
        )

        output = []

        # This is very inefficient but necessary to have realtime verbose
        # output from the called function. This is especially noticeable when
        # printing the success dots during test runs.
        line_buf = []
        while True:
            stdout_char = process.stdout.read(1)
            if not stdout_char:
                if line_buf:
                    output.append("".join(line_buf).strip())
                break
            elif stdout_char == "\n":
                output.append("".join(line_buf).strip())
                line_buf = []
            else:
                line_buf.append(stdout_char)

            if config.get("verbose", False):
                sys.stdout.write(stdout_char)
                sys.stdout.flush()

        process.stdout.close()
        return_code = process.wait()

        if return_code:
            raise subprocess.CalledProcessError(return_code, command, output)

        return output


@register_runtime_provider("docker")
class DockerRuntimeProvider(Runtime):
    @staticmethod
    def setup(config):
        output = LocalRuntimeProvider.run_command(
            config, ["docker", "build", "-t", config["image_name"], config["cwd"]]
        )
        return output[-1].startswith("Successfully tagged " + config["image_name"])

    @staticmethod
    def is_ready(config):
        if "image_name" not in config:
            raise DevRepoException(
                "'image_name' missing from config for docker runtime provider."
            )

        return config["image_name"] in DockerRuntimeProvider.get_images(config)

    @staticmethod
    def run_command(config, command):
        if isinstance(command, basestring):
            command = shlex.split(command)

        additional_args = []

        if (
            "extra_runtime_config" in config
            and "expose_ports" in config["extra_runtime_config"]
        ):
            ports_to_expose = sorted(config["extra_runtime_config"]["expose_ports"])

            used_ports = set()

            while len(ports_to_expose) != 0:
                port = ports_to_expose[-1]
                local_port = Runtime.find_open_ports(port, 1)[0]
                if local_port in used_ports:
                    continue
                else:
                    used_ports.add(local_port)
                    ports_to_expose.pop()
                    print(
                        "Mapping local port %s to container port %s"
                        % (local_port, port)
                    )
                    additional_args.extend(["-p", "%s:%s" % (local_port, port)])

        pwinfo = pwd.getpwuid(os.getuid())

        full_command = (
            [
                "docker",
                "run",
                "-it",
                "--rm",
                "--mount",
                "src=%s,target=%s,type=bind" % (config["cwd"], config["workingdir"]),
                "-u",
                "%s:%s" % (pwinfo[2], pwinfo[3]),
                "-w",
                config["workingdir"],
                "--name",
                "dev-tree-container",
            ]
            + additional_args
            + [config["image_name"]]
            + command
        )

        def kill_handler(signum, frame):
            print("force killing container", file=sys.stderr)
            LocalRuntimeProvider.run_command(
                config, ["docker", "kill", "dev-tree-container"]
            )

        signal.signal(signal.SIGQUIT, kill_handler)

        output = LocalRuntimeProvider.run_command(config, full_command)

        return output

    @staticmethod
    def get_images(config):
        config = copy.deepcopy(config)
        config["verbose"] = False
        output = LocalRuntimeProvider.run_command(config, ["docker", "images"])
        return [l.split()[0] for l in output[1:]]

    @staticmethod
    def rm_image(config, image_name):
        output = LocalRuntimeProvider.run_command(
            config, ["docker", "rmi", "-f", image_name]
        )
        return output


###############
# CLI Section #
###############


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
        parser = parent.add_parser(
            func.__name__, help=func.__doc__.split("\n")[0], description=func.__doc__
        )
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
        parser.set_defaults(func=func)
        return func

    return decorator


@subcommand([argument("project", default=None, nargs=1, help="project path")])
def print_config(args):
    """Print the configuration for the given project."""
    root_path = os.path.realpath(os.curdir)
    project_path = args.project[0]

    config = ProjectConfig.lookup_config(root_path, project_path)

    print(json.dumps(config, sort_keys=True, indent=4, separators=(",", ": ")))


@subcommand([argument("project", default=None, nargs=1, help="project path")])
def build(args):
    """Run the build command for the given project."""
    root_path = os.path.realpath(os.curdir)
    project_path = args.project[0]

    ProjectConfig.run_project_command(root_path, project_path, "build")


@subcommand([argument("project", default=None, nargs=1, help="project path")])
def list_commands(args):
    """List commands available to project."""
    root_path = os.path.realpath(os.curdir)
    project_path = args.project[0]

    project_config = ProjectConfig.lookup_config(root_path, project_path)
    proj_commands = sorted(ProjectConfig.get_commands(project_config))

    print(" ".join(proj_commands))


@subcommand()
def list_projects(args):
    """List commands available to project."""
    path = os.path.realpath(os.curdir)

    projects = ProjectConfig.list_projects(path)

    print("\n".join(projects))


@subcommand([argument("project", default=None, nargs=1, help="project path")])
def test(args):
    """Run the test command for the given project."""
    root_path = os.path.realpath(os.curdir)
    project_path = args.project[0]

    ProjectConfig.run_project_command(root_path, project_path, "test", verbose=True)


@subcommand(
    [
        argument("project", default=None, nargs=1, help="project path"),
        argument("command", nargs=1, help="The command to run"),
    ]
)
def run(args):
    """Run the test command for the given project."""
    root_path = os.path.realpath(os.curdir)
    project_path = args.project[0]

    ProjectConfig.run_project_command(root_path, project_path, args.command[0])


@subcommand()
def findroot(args):
    """Find the root of the Dev tree"""
    print(Repo.get_dev_root(os.curdir))


if __name__ == "__main__":
    args = cli.parse_args()
    if args.subcommand is None:
        cli.print_help()
    else:
        sys.exit(args.func(args))
