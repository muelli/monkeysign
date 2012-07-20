import sys, os
import unittest

sys.path.append(os.path.dirname(__file__) + '/..')

from monkeysign import Gpg, GpgTemp

class TestGpg(unittest.TestCase):
    def setUp(self):
        self.gpg = Gpg('/tmp/gpg-home')

    def test_env(self):
        self.assertEqual(os.environ['GPG_HOME'], '/tmp/gpg-home')

class TestGpgTemp(unittest.TestCase):
    def setUp(self):
        # we test using the temporary keyring because it's too dangerous otherwise
        if 'GPG_HOME' in os.environ: del os.environ['GPG_HOME']
        self.gpg = GpgTemp()

    def test_set_option(self):
        self.gpg.set_option('armor')
        self.assertIn('armor', self.gpg.options)
        self.gpg.set_option('keyserver', 'foo.example.com')
        self.assertDictContainsSubset({'keyserver': 'foo.example.com'}, self.gpg.options)

    def test_build_command(self):
        # reset options to a known setting
        options = { 'status-fd': 1, 'command-fd': 0, 'no-tty': None, 'use-agent': None }
        self.gpg.options = options
        self.assertEqual(self.gpg.build_command(['list-keys', 'foo']), ['gpg', '--command-fd', '0', '--no-tty', '--status-fd', '1', '--use-agent', '--list-keys', 'foo' ])

    def test_env(self):
        self.assertTrue(os.path.exists(os.environ['GPG_HOME']))

    def test_command(self):
        c = self.gpg.build_command([])
        c.append('--version')
        c2 = self.gpg.build_command(['version'])
        self.assertEqual(c, c2)

    def test_version(self):
        self.assertTrue(self.gpg.version())

    def test_import(self):
        self.assertTrue(self.gpg.import_data(open(os.path.dirname(__file__) + '/7B75921E.asc').read()))

    def test_export(self):
        k1 = open(os.path.dirname(__file__) + '/7B75921E.asc').read()
        self.gpg.set_option('armor')
        k2 = self.gpg.export_data('7B75921E')
        self.assertEqual(k1,k2)

    def tearDown(self):
        del self.gpg

if __name__ == '__main__':
    unittest.main()
