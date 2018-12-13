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
                    "local": {"type": "local", "cwd": "$CWD"},
                    "base": {"type": "docker", "project": "//runtimes:test_runtime"},
                    "bad_runtime": {
                        "type": "docker",
                        "project": "//runtimes:does_not_exist",
                    },
                },
                "project_defaults": {
                    "runtime": "base",
                    "commands": {"build": "bazel build $PROJECTPATH"},
                },
            },
            dev.GlobalConfig.get(test_root),
        )

    def test_list_available_runtimes(self):
        self.assertEqual(
            ["bad_runtime", "base", "local"], dev.GlobalConfig.get_runtimes(test_root)
        )

    def test_get_project_list(self):
        self.assertEqual(
            sorted(
                [
                    "project_bar",
                    "project_bar_no_commands",
                    "project_bar_var_test",
                    "project_foo",
                    "project_foo_other",
                ]
            ),
            dev.ProjectConfig.list_projects(test_root, "//world/example.com"),
        )

    def test_get_project_commands(self):
        self.assertEqual(
            {"build": "echo foo"},
            dev.ProjectConfig.get_commands(
                test_root, "//world/example.com:project_foo"
            ),
        )

        self.assertEqual(
            {"build": "bazel build $PROJECTPATH"},
            dev.ProjectConfig.get_commands(
                test_root, "//world/example.com:project_bar_no_commands"
            ),
        )

    def test_get_project_config(self):
        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.get,
            test_root,
            "bad_path/foo_project:bad",
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.get,
            test_root,
            "//bad_project_path_with_no_colon",
        )

        self.assertRaises(
            dev.DevRepoException,
            dev.ProjectConfig.get,
            test_root,
            "//world/example.com:project_not_exist",
        )

        self.assertEqual(
            {
                "path": "project_foo",
                "commands": {"build": "echo foo"},
                "runtime": "base",
            },
            dev.ProjectConfig.get(test_root, "//world/example.com:project_foo"),
        )


class LocalRuntimeTests(unittest.TestCase):
    def test_run_command(self):
        self.assertEqual(
            ["Test Success!"],
            dev.Runtime.run_command(
                ["/bin/echo", "Test Success!"], capture_output=True
            ),
        )

    def test_get_ports(self):
        self.assertEqual([30002, 30003, 30004], dev.Runtime.find_open_ports(30002, 3))

        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0)
            free_port = 30002
            sock.bind(("localhost", free_port))
            self.assertEqual([30003, 30004], dev.Runtime.find_open_ports(30002, 2))

    def test_local_runtime_setup(self):
        self.assertTrue(
            dev.Runtime.setup(
                location=os.path.join(test_data_dir, "local_runtime_example")
            )
        )

        self.assertFalse(
            dev.Runtime.setup(
                location=os.path.join(test_data_dir, "local_runtime_example_bad")
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
            dev.DockerRuntime.setup(
                location=os.path.join(
                    test_data_dir, "test_root", "runtimes", "test_runtime"
                ),
                name=self.image_name,
            )
        )

    def tearDown(self):
        self.assertTrue(dev.DockerRuntime.rm_image(self.image_name))

        self.assertNotIn(self.image_name, dev.DockerRuntime.get_images())

    def test_docker_setup(self):
        self.assertIn(self.image_name, dev.DockerRuntime.get_images())

        # bad path
        self.assertRaises(
            subprocess.CalledProcessError,
            dev.DockerRuntime.setup,
            location=os.path.join(test_data_dir, "test_root"),
            name=self.image_name,
        )

    def test_docker_run(self):
        self.assertIn(
            'NAME="Alpine Linux"',
            dev.DockerRuntime.run_command(
                self.image_name, ["cat", "/etc/os-release"], capture_output=True
            ),
        )

        self.assertRaises(
            subprocess.CalledProcessError,
            dev.DockerRuntime.run_command,
            name="bad",
            command=["cat", "/etc/os-release"],
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()

