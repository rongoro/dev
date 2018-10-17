import dev
import unittest
import os
import threading
import SocketServer
import SimpleHTTPServer
import tempfile
import shutil

test_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_data')

class ThreadedHTTPServer(object):
    handler = SimpleHTTPServer.SimpleHTTPRequestHandler

    def __init__(self, host, port):
        self.server = SocketServer.TCPServer((host, port), self.handler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True

    def start(self):
        self.server_thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class DevEnvTests(unittest.TestCase):
    TESTFILE_CONTENTS = 'this is a test'
    TESTFILE_HASH = '2e99758548972a8e8822ad47fa1017ff72f06f3ff6a016851f45c398732bc50c'

    def test_hashfile(self):
        temp = tempfile.NamedTemporaryFile()
        temp.write(self.TESTFILE_CONTENTS)
        temp.flush()
        self.assertEqual(self.TESTFILE_HASH,
                         dev.hashfile(temp.name))


    def A_test_get_runtime_depends(self):
        temp = tempfile.NamedTemporaryFile(dir=os.curdir)
        temp.write(self.TESTFILE_CONTENTS)
        temp.flush()

        tempdir = tempfile.mkdtemp()

        server = ThreadedHTTPServer('localhost', 8000)
        server.start()

        dev.get_dependencies(
            [dev.DependencyInfo('http://localhost:8000/'+os.path.basename(temp.name),
                                self.TESTFILE_HASH)],
            tempdir)

        self.assertRaises(Exception,
                          dev.get_runtime_depends,
                          [dev.DependencyInfo('http://localhost:8000/'+os.path.basename(temp.name),
                                              "xxx")],
                          tempdir
                          )

        server.stop()
        shutil.rmtree(tempdir)


    def test_find_root(self):
        expected_value = test_data_dir

        self.assertEqual(expected_value, dev.find_dev_root(test_data_dir))
        self.assertRaises(Exception, dev.find_dev_root, '/usr/local/bin')
        self.assertEqual(expected_value, dev.find_dev_root(os.path.join(test_data_dir, 'example_world/package/bar')))


    def test_list_runtimes(self):
        expected_value = set(('bar', 'foo'))

        self.assertEqual(expected_value, dev.list_dev_runtimes(dev.find_dev_root(test_data_dir)))


    def test_get_runtime_config(self):
        expected_value = {'type':'docker',
                          'template': 'templates/path.to.bar.templates'}

        self.assertEqual(expected_value, dev.get_runtime_config(test_data_dir, 'bar'))


if __name__ == '__main__':
    unittest.main()
