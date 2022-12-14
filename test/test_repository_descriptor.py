from colcon_distro.repository_descriptor import RepositoryDescriptor

import unittest


def _dummy():
    d = RepositoryDescriptor()
    d.name = 'foo'
    d.type = 'git'
    d.url = 'path/to/server'
    d.version = '1.2.3'
    d.packages = []
    return d


class RepositoryDescriptorTests(unittest.TestCase):
    def test_non_identity(self):
        # Equality between descriptors that aren't fully defined is undefined.
        with self.assertRaises(NotImplementedError):
            RepositoryDescriptor() == RepositoryDescriptor()

        # Hashing for deduplication or other purposes is likewise undefined.
        with self.assertRaises(NotImplementedError):
            set((RepositoryDescriptor(),))

    def test_identity(self):
        a = _dummy()
        b = _dummy()
        self.assertEqual(a, b)

        b.version = '1.2.4'
        self.assertNotEqual(a, b)

    def test_hashability(self):
        a = _dummy()
        b = _dummy()
        c = _dummy()
        c.name = "bar"
        repo_set = set((a, b, c))
        self.assertEqual(len(repo_set), 2)

    def test_dict(self):
        a = _dummy()
        a.metadata = {
            'foo': 'bar',
            'baz': 123,
        }
        self.assertEqual(a.to_dict(), {
            'type': 'git',
            'url': 'path/to/server',
            'version': '1.2.3',
            'packages': []
        })
        self.assertEqual(a.to_dict(['foo']), {
            'type': 'git',
            'url': 'path/to/server',
            'version': '1.2.3',
            'metadata': {
                'foo': 'bar',
            },
            'packages': []
        })
