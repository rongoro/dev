import dev
import os
import subprocess
import unittest
import socket

from contextlib import closing


test_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_data")


class DevRepoHelpersTests(unittest.TestCase):
    def test_get_dev_root(self):
        self.assertEqual(
            os.path.join(test_data_dir, "test_root"),
            dev.Repo.get_dev_root(os.path.join(test_data_dir, "test_root")),
        )

    def test_get_dev_root_not_exist(self):
        self.assertRaises(Exception, dev.Repo.get_dev_root, "/usr/bin")

    def test_get_dev_config(self):
        self.assertTrue(
            dev.Repo.get_dev_config(
                os.path.join(
                    test_data_dir, "test_root", "world", "example.com", "project_foo"
                )
            )
        )

    def test_get_dev_config_not_exist(self):
        self.assertRaises(
            Exception,
            dev.Repo.get_dev_config,
            os.path.join(
                test_data_dir,
                "test_root",
                "world",
                "unconfigured.com",
                "project_unconifigured",
            ),
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
            res = sock.bind(("localhost", free_port))
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

