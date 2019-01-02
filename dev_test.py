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
                    "commands": {"build": "bazel build $PROJECTPATH"},
                },
            },
            dev.GlobalConfig.get(test_root),
        )

    def test_list_available_runtimes(self):
        self.assertEqual(
            ["bad_runtime", "base", "host"], dev.GlobalConfig.get_runtimes(test_root)
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
                    "project_bar_no_commands",
                    "project_bar_var_test",
                    "project_foo",
                    "project_foo_other",
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
            {"build": "echo foo"},
            dev.ProjectConfig.get_commands(
                dev.ProjectConfig.lookup_config(
                    test_root, "//world/example.com:project_foo"
                )
            ),
        )

        self.assertEqual(
            {"build": "bazel build $PROJECTPATH"},
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
                "commands": {"build": "echo foo"},
                "runtime": "host",
            },
            dev.ProjectConfig.lookup_config(
                test_root, "//world/example.com:project_foo"
            ),
        )


class LocalRuntimeTests(unittest.TestCase):
    def test_run_command(self):
        self.assertEqual(
            ["Test Success!"],
            dev.Runtime.run_command(
                {"provider": "local"}, ["/bin/echo", "Test Success!"]
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

        self.assertFalse(
            dev.LocalRuntimeProvider.setup(
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
            dev.DockerRuntimeProvider.setup(
                {
                    "location": os.path.join(
                        test_data_dir, "test_root", "runtimes", "test_runtime"
                    ),
                    "image_name": self.image_name,
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
                "location": os.path.join(test_data_dir, "test_root"),
                "image_name": self.image_name,
            },
        )

    def test_docker_run(self):
        self.assertIn(
            'NAME="Alpine Linux"',
            dev.DockerRuntimeProvider.run_command(
                {"image_name": self.image_name}, ["cat", "/etc/os-release"]
            ),
        )

        self.assertRaises(
            subprocess.CalledProcessError,
            dev.DockerRuntimeProvider.run_command,
            {"image_name": "bad"},
            command=["cat", "/etc/os-release"],
        )


class DevRuntimeTests(unittest.TestCase):
    def test_run_command(self):
        test_command = "echo 'this is a test'"

        runtime_config = {"provider": "local"}

        self.assertEqual(
            ["this is a test"], dev.Runtime.run_command(runtime_config, test_command)
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
        image_name = "dev_test_image"
        self.assertIn(
            'NAME="Alpine Linux"',
            dev.Runtime.run_command(
                {"provider":"docker",
                    "image_name": image_name,
                    "location": os.path.join(
                        test_data_dir, "test_root", "runtimes", "test_runtime"
                    ),
                },
                ["cat", "/etc/os-release"],
            ),
        )

        # cleanup
        self.assertTrue(dev.DockerRuntimeProvider.rm_image({}, image_name))

        self.assertNotIn(image_name, dev.DockerRuntimeProvider.get_images({}))


if __name__ == "__main__":
    unittest.main()

