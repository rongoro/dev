import dev
import os
import unittest

test_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_data')

class DevRepoHelpersTests(unittest.TestCase):
    def test_find_dev_root(self):
        self.assertEqual(os.path.join(test_data_dir, 'test_root'),
            dev.find_dev_root(os.path.join(test_data_dir, 'test_root')))

        self.assertRaises(Exception, dev.find_dev_root, '/usr/bin')

if __name__ == '__main__':
    unittest.main()


