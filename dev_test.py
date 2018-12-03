import dev
import os
import unittest

test_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_data')

class DevRepoHelpersTests(unittest.TestCase):
    def test_get_dev_root(self):
        self.assertEqual(os.path.join(test_data_dir, 'test_root'),
            dev.Repo.get_dev_root(os.path.join(test_data_dir, 'test_root')))

    def test_get_dev_root_not_exist(self):
        self.assertRaises(Exception, dev.Repo.get_dev_root, '/usr/bin')

    def test_get_dev_config(self):
        self.assertTrue(dev.Repo.get_dev_config(
            os.path.join(test_data_dir, 'test_root', 'world', 'example.com', 'project_foo')
        ))

    def test_get_dev_config_not_exist(self):
        self.assertRaises(Exception, dev.Repo.get_dev_config, 
                          os.path.join(test_data_dir, 'test_root', 'world', 'unconfigured.com', 'project_unconifigured'))

class DevShellHelpersTests(unittest.TestCase):
    def test_run_command(self):
        self.assertEqual(['Test Success!'],
        dev.Commands.run_command(['/bin/echo', 'Test Success!'], capture_output=True))


if __name__ == '__main__':
    unittest.main()


