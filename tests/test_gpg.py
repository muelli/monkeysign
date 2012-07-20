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

    def test_env(self):
        self.assertTrue(os.path.exists(os.environ['GPG_HOME']))

    def test_command(self):
        c = self.gpg.build_command([])
        c.append('--version')
        c2 = self.gpg.build_command(['--version'])
        self.assertEqual(c, c2)

    def test_version(self):
        self.assertTrue(self.gpg.version())

    def tearDown(self):
        del self.gpg

if __name__ == '__main__':
    unittest.main()