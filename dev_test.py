from __future__ import print_function

import dev
import os
import subprocess
import unittest
import socket
import json

from contextlib import closing


test_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")
test_root = os.path.join(test_data_dir, "test_root")


class DevRepoHelpersTests(unittest.TestCase):
    def test_get_dev_root(self):
        self.assertEqual(
            os.path.join(test_data_dir, "test_root"),
            dev.Repo.get_dev_root(os.path.join(test_data_dir, "test_root")),
        )

    def test_get_dev_root_not_exist(self):
        self.assertRaises(Exception, dev.Repo.get_dev_root, "/usr/bin")


class DevConfigHelpersTest(unittest.TestCase):
    maxDiff = None

    def test_merge_config_with_default_dict(self):
        self.assertEqual({}, dev.ProjectConfig._merge_config_with_default_dict({}, {}))

        self.assertEqual(
            {"foo": "bar"},
            dev.ProjectConfig._merge_config_with_default_dict({"foo": "bar"}, {}),
        )

        self.assertEqual(
            {"foo": "bar", "default": "baz"},
            dev.ProjectConfig._merge_config_with_default_dict(
                {"foo": "bar"}, {"default": "baz"}
            ),
        )

        self.assertEqual(
            {"foo": "bar", "baz": {"test": "one"}},
            dev.ProjectConfig._merge_config_with_default_dict(
                {"foo": "bar", "baz": {"test": "one"}}, {"baz": {"test": "two"}}
            ),
        )

        self.assertEqual(
            {"foo": "bar", "baz": {"test": "one", "test2": "two"}},
            dev.ProjectConfig._merge_config_with_default_dict(
                {"foo": "bar", "baz": {"test": "one"}}, {"baz": {"test2": "two"}}
            ),
        )

    def test_get_global_config(self):
        self.assertEqual(
            {
                "version": "1",
                "runtimes": {
                    "host": {"provider": "local", "cwd": "$CWD"},
                    "host-verbose": {
                        "provider": "local",
                        "cwd": "$CWD",
                        "verbose": True,
                    },
                    "base": {
                        "provider": "docker",
                        "project": "//runtimes:test_runtime",
                        "image_name": "test_runtime",
                        "container_name": "test_build_container",
                    },
                    "bad_runtime": {
                        "provider": "docker",
                        "project": "//runtimes:does_not_exist",
                    },
                },
                "project_defaults": {
                    "runtime": "host",
                    "commands": {
                        "build": "bazel build $PROJECTPATH",
                        "test": "echo TEST NOT IMPLEMENTED",
                    },
                },
            },
            dev.GlobalConfig.get(test_root),
        )

    def test_list_available_runtimes(self):
        self.assertEqual(
            ["bad_runtime", "base", "host", "host-verbose"],
            dev.GlobalConfig.get_runtimes(test_root),
        )

    def test_get_runtime_config(self):
        self.assertEqual(
            {
                "provider": "docker",
                "project": "//runtimes:test_runtime",
                "image_name": "test_runtime",
                "container_name": "test_build_container",
            },
            dev.GlobalConfig.get_runtime_config(test_root, "base"),
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.GlobalConfig.get_runtime_config,
            test_root,
            "non_existant_runtime",
        )

        # malformed project path
        self.assertRaisesRegexp(
            dev.DevRepoException,
            "Bad project path:.*",
            dev.ProjectConfig.lookup_config,
            test_root,
            "//foo::",
        )

    def test_get_project_list(self):
        self.assertEqual(
            sorted(
                [
                    "project_bar",
                    "project_bar_verbose",
                    "project_bar_no_commands",
                    "project_bar_var_test",
                    "project_bar_var_test_verbose",
                    "project_foo",
                    "project_foo_other",
                    "project_foo_other_verbose",
                    "project_foo_with_extra_command_args",
                ]
            ),
            dev.ProjectConfig.list_projects(test_root, "//world/example.com"),
        )

        self.assertRaisesRegexp(
            dev.DevRepoException,
            r"Project should not be specified\.",
            dev.ProjectConfig.list_projects,
            test_root,
            "//world/example.com:foo",
        )

    def test_get_project_commands(self):
        self.assertEqual(
            {"build": "echo foo", "test": "echo TEST NOT IMPLEMENTED"},
            dev.ProjectConfig.get_commands(
                dev.ProjectConfig.lookup_config(
                    test_root, "//world/example.com:project_foo"
                )
            ),
        )

        self.assertEqual(
            {"build": "bazel build $PROJECTPATH", "test": "echo TEST NOT IMPLEMENTED"},
            dev.ProjectConfig.get_commands(
                dev.ProjectConfig.lookup_config(
                    test_root, "//world/example.com:project_bar_no_commands"
                )
            ),
        )

        self.assertEqual({}, dev.ProjectConfig.get_commands({}))

    def test_get_project_config(self):
        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.lookup_config,
            test_root,
            "bad_path/foo_project:bad",
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.lookup_config,
            test_root,
            "//bad_project_path_with_no_colon",
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.lookup_config,
            test_root,
            "//world/example.com:project_not_exist",
        )

        self.assertEqual(
            {
                "path": "project_foo",
                "commands": {"build": "echo foo", "test": "echo TEST NOT IMPLEMENTED"},
                "runtime": "host",
            },
            dev.ProjectConfig.lookup_config(
                test_root, "//world/example.com:project_foo"
            ),
        )

    def test_render_config(self):
        self.assertEqual(
            {},
            dev.ProjectConfig._render_config(
                {},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {"foo": "bar"},
            dev.ProjectConfig._render_config(
                {"foo": "bar"},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {"foo": "bar", "baz": "test"},
            dev.ProjectConfig._render_config(
                {"foo": "bar", "baz": "test"},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {"foo": "bar", "A": {"baz": "test"}},
            dev.ProjectConfig._render_config(
                {"foo": "bar", "A": {"baz": "test"}},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {
                "foo": "bar",
                "A": {
                    "baz": os.path.realpath(
                        os.path.join(test_root, "world", "example.com", "project_foo")
                    )
                },
            },
            dev.ProjectConfig._render_config(
                {"foo": "bar", "A": {"baz": "$CWD"}},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {
                "cwd": os.path.realpath(
                    os.path.join(test_root, "world", "example.com", "project_foo")
                ),
                "provider": "local",
            },
            dev.ProjectConfig._render_config(
                {u"cwd": u"$CWD", u"provider": u"local"},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {
                "testenv": [
                    {
                        "cwd": os.path.realpath(
                            os.path.join(
                                test_root, "world", "example.com", "project_foo"
                            )
                        )
                    },
                    "string",
                ],
                "provider": "local",
            },
            dev.ProjectConfig._render_config(
                {"testenv": [{u"cwd": u"$CWD"}, "string"], u"provider": u"local"},
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertEqual(
            {
                "testenv": [
                    {
                        "cwd": os.path.realpath(
                            os.path.join(
                                test_root, "world", "example.com", "project_foo"
                            )
                        ),
                        "isTrue": True,
                    },
                    "string",
                ],
                "provider": "local",
            },
            dev.ProjectConfig._render_config(
                {
                    "testenv": [{u"cwd": u"$CWD", u"isTrue": True}, "string"],
                    u"provider": u"local",
                },
                dev.ProjectConfig._build_tmpl_vars(
                    test_root, "//world/example.com:project_foo"
                ),
            ),
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig._render_config,
            {"test": object()},
            dev.ProjectConfig._build_tmpl_vars(
                test_root, "//world/example.com:project_foo"
            ),
        )


class ProjectConfigTests(unittest.TestCase):
    def test_run_project_command_non_existant_command(self):

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.run_project_command,
            test_root,
            "//world/example.com:project_foo",
            "non_existant_command",
        )

    def test_run_project_command_setting_verbose(self):
        self.assertEqual(
            ["foo other"],
            dev.ProjectConfig.run_project_command(
                test_root,
                "//world/example.com:project_foo_other_verbose",
                "build",
                verbose=False,
            ),
        )


class LocalRuntimeTests(unittest.TestCase):
    def test_run_command(self):
        self.assertEqual(
            ["Test Success!"],
            dev.Runtime.run_command(
                test_root, {"provider": "local"}, ["/bin/echo", "Test Success!"]
            ),
        )

    def test_get_ports(self):
        self.assertEqual([30002, 30003, 30004], dev.Runtime.find_open_ports(30002, 3))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with closing(sock):
            sock.settimeout(0)
            free_port = 30002
            sock.bind(("localhost", free_port))
            self.assertEqual([30003, 30004], dev.Runtime.find_open_ports(30002, 2))

    def test_local_runtime_setup(self):
        self.assertTrue(
            dev.LocalRuntimeProvider.setup(
                location=os.path.join(test_data_dir, "local_runtime_example")
            )
        )

    def test_config_variable_replacing(self):
        self.assertEqual(
            "bar %(cwd)s %(builddir)s"
            % {
                "builddir": os.path.join(
                    test_root, "build/world/example.com/project_bar_var_test"
                ),
                "cwd": os.path.join(test_root, "world/example.com/project_bar"),
            },
            "\n".join(
                dev.ProjectConfig.run_project_command(
                    test_root, "//world/example.com:project_bar_var_test", "build"
                )
            ),
        )


class DockerRuntimeTests(unittest.TestCase):
    image_name = "dev_test_image"

    def setUp(self):
        self.assertTrue(
            dev.DockerRuntimeProvider.setup(
                {
                    "project": "//runtimes:test_runtim",
                    "image_name": self.image_name,
                    "cwd": os.path.realpath(
                        os.path.join(
                            os.path.dirname(__file__),
                            "test_data",
                            "test_root",
                            "runtimes",
                            "test_runtime",
                        )
                    ),
                    "workingdir": "/project",
                }
            )
        )

    def tearDown(self):
        self.assertTrue(dev.DockerRuntimeProvider.rm_image({}, self.image_name))

        self.assertNotIn(self.image_name, dev.DockerRuntimeProvider.get_images({}))

    def test_docker_image_is_ready(self):
        self.assertRaises(dev.DevRepoException, dev.DockerRuntimeProvider.is_ready, {})

        self.assertTrue(
            dev.DockerRuntimeProvider.is_ready({"image_name": self.image_name})
        )
        self.assertFalse(
            dev.DockerRuntimeProvider.is_ready({"image_name": "non_existant_image"})
        )

    def test_docker_setup(self):
        self.assertIn(self.image_name, dev.DockerRuntimeProvider.get_images({}))

        # bad path
        self.assertRaises(
            subprocess.CalledProcessError,
            dev.DockerRuntimeProvider.setup,
            {
                "provider": "docker",
                "project": "//runtimes:bad_runtime",
                "image_name": self.image_name,
                "cwd": os.path.realpath(
                    os.path.join(
                        os.path.dirname(__file__), "test_data", "test_root", "runtimes"
                    )
                ),
                "workingdir": "/project",
            },
        )

    def test_docker_run(self):
        self.assertIn(
            'NAME="Alpine Linux"',
            dev.DockerRuntimeProvider.run_command(
                {
                    "provider": "docker",
                    "project": "//runtimes:test_runtime",
                    "image_name": self.image_name,
                    "cwd": os.path.realpath(
                        os.path.join(
                            os.path.dirname(__file__),
                            "test_data",
                            "test_root",
                            "runtimes",
                            "test_runtime",
                        )
                    ),
                    "workingdir": "/project",
                },
                ["cat", "/etc/os-release"],
            ),
        )

        self.assertRaises(
            subprocess.CalledProcessError,
            dev.DockerRuntimeProvider.run_command,
            {
                "provider": "docker",
                "project": "//runtimes:test_runtime",
                "image_name": "bad",
                "cwd": os.path.realpath(
                    os.path.join(
                        os.path.dirname(__file__),
                        "test_data",
                        "test_root",
                        "runtimes",
                        "test_runtime",
                    )
                ),
                "workingdir": "/project",
            },
            command=["cat", "/etc/os-release"],
        )


class DevRuntimeTests(unittest.TestCase):
    def test_run_command(self):
        test_command = "echo 'this is a test'"

        runtime_config = {"provider": "local"}

        self.assertEqual(
            ["this is a test"],
            dev.Runtime.run_command(test_root, runtime_config, test_command),
        )

    def test_provider_lookup(self):
        self.assertRaises(dev.DevRepoException, dev.Runtime.get_provider, {})

        self.assertEqual(
            dev.LocalRuntimeProvider, dev.Runtime.get_provider({"provider": "local"})
        )

        self.assertEqual(
            dev.DockerRuntimeProvider, dev.Runtime.get_provider({"provider": "docker"})
        )

    def test_run_command_when_docker_image_not_setup(self):
        image_name = "test_runtime"
        self.assertIn(
            'NAME="Alpine Linux"',
            dev.Runtime.run_command(
                test_root,
                {
                    "provider": "docker",
                    "project": "//runtimes:test_runtime",
                    "image_name": image_name,
                    "cwd": os.path.realpath(
                        os.path.join(
                            os.path.dirname(__file__), "test_data", "test_root"
                        )
                    ),
                    "workingdir": "/project",
                },
                ["cat", "/etc/os-release"],
            ),
        )

        # cleanup
        self.assertTrue(dev.DockerRuntimeProvider.rm_image({}, image_name))

        self.assertNotIn(image_name, dev.DockerRuntimeProvider.get_images({}))


class DevCLITests(unittest.TestCase):
    def dev_cmd(self, args):
        dev_cmd = os.path.join(os.path.realpath(os.curdir), "dev.py")

        try:
            return subprocess.check_output([dev_cmd] + args, cwd=test_root)
        except subprocess.CalledProcessError as x:
            print(x.output)
            raise x

    def test_print_config(self):
        self.assertEqual(
            """{
    "commands": {
        "build": "docker build -t test_runtime .",
        "test": "echo TEST NOT IMPLEMENTED"
    },
    "path": "test_runtime",
    "runtime": "host"
}
""",
            self.dev_cmd(["print_config", "//runtimes:test_runtime"]),
        )

    def test_build_command(self):
        self.assertEqual(
            "foo other\n",
            self.dev_cmd(["build", "//world/example.com:project_foo_other_verbose"]),
        )

        self.assertEqual(
            "bar %s %s\n"
            % (
                os.path.realpath(
                    os.path.join(test_root, "world", "example.com", "project_bar")
                ),
                os.path.realpath(
                    os.path.join(
                        test_root,
                        "build",
                        "world",
                        "example.com",
                        "project_bar_var_test_verbose",
                    )
                ),
            ),
            self.dev_cmd(["build", "//world/example.com:project_bar_var_test_verbose"]),
        )

    def test_test_command(self):
        self.assertEqual(
            "TEST NOT IMPLEMENTED\n",
            self.dev_cmd(["test", "//world/example.com:project_bar_verbose"]),
        )


if __name__ == "__main__":
    unittest.main()

