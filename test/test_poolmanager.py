import sys

from urllib3.poolmanager import (
    PoolKey,
    key_fn_by_scheme,
    PoolManager,
)
from urllib3 import connection_from_url
from urllib3.exceptions import (
    ClosedPoolError,
    LocationValueError,
)
from urllib3.util import retry, timeout, ssl_

from dummyserver.server import (DEFAULT_CA, DEFAULT_CERTS, DEFAULT_CA_DIR)

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


class TestPoolManager(unittest.TestCase):
    def test_same_url(self):
        # Convince ourselves that normally we don't get the same object
        conn1 = connection_from_url('http://localhost:8081/foo')
        conn2 = connection_from_url('http://localhost:8081/bar')
        self.addCleanup(conn1.close)
        self.addCleanup(conn2.close)

        self.assertNotEqual(conn1, conn2)

        # Now try again using the PoolManager
        p = PoolManager(1)
        self.addCleanup(p.clear)

        conn1 = p.connection_from_url('http://localhost:8081/foo')
        conn2 = p.connection_from_url('http://localhost:8081/bar')

        self.assertEqual(conn1, conn2)

    def test_many_urls(self):
        urls = [
            "http://localhost:8081/foo",
            "http://www.google.com/mail",
            "http://localhost:8081/bar",
            "https://www.google.com/",
            "https://www.google.com/mail",
            "http://yahoo.com",
            "http://bing.com",
            "http://yahoo.com/",
        ]

        connections = set()

        p = PoolManager(10)
        self.addCleanup(p.clear)

        for url in urls:
            conn = p.connection_from_url(url)
            connections.add(conn)

        self.assertEqual(len(connections), 5)

    def test_manager_clear(self):
        p = PoolManager(5)
        self.addCleanup(p.clear)

        conn_pool = p.connection_from_url('http://google.com')
        self.assertEqual(len(p.pools), 1)

        conn = conn_pool._get_conn()

        p.clear()
        self.assertEqual(len(p.pools), 0)

        self.assertRaises(ClosedPoolError, conn_pool._get_conn)

        conn_pool._put_conn(conn)

        self.assertRaises(ClosedPoolError, conn_pool._get_conn)

        self.assertEqual(len(p.pools), 0)

    def test_nohost(self):
        p = PoolManager(5)
        self.addCleanup(p.clear)
        self.assertRaises(LocationValueError, p.connection_from_url, 'http://@')
        self.assertRaises(LocationValueError, p.connection_from_url, None)

    def test_contextmanager(self):
        with PoolManager(1) as p:
            conn_pool = p.connection_from_url('http://google.com')
            self.assertEqual(len(p.pools), 1)
            conn = conn_pool._get_conn()

        self.assertEqual(len(p.pools), 0)

        self.assertRaises(ClosedPoolError, conn_pool._get_conn)

        conn_pool._put_conn(conn)

        self.assertRaises(ClosedPoolError, conn_pool._get_conn)

        self.assertEqual(len(p.pools), 0)

    def test_http_pool_key_fields(self):
        """Assert the HTTPPoolKey fields are honored when selecting a pool."""
        connection_pool_kw = {
            'timeout': timeout.Timeout(3.14),
            'retries': retry.Retry(total=6, connect=2),
            'block': True,
            'source_address': '127.0.0.1',
        }
        p = PoolManager()
        self.addCleanup(p.clear)
        conn_pools = [
            p.connection_from_url('http://example.com/'),
            p.connection_from_url('http://example.com:8000/'),
            p.connection_from_url('http://other.example.com/'),
        ]

        for key, value in connection_pool_kw.items():
            p.connection_pool_kw[key] = value
            conn_pools.append(p.connection_from_url('http://example.com/'))

        self.assertTrue(
            all(
                x is not y
                for i, x in enumerate(conn_pools)
                for j, y in enumerate(conn_pools)
                if i != j
            )
        )
        self.assertTrue(
            all(
                isinstance(key, PoolKey)
                for key in p.pools.keys())
        )

    def test_https_pool_key_fields(self):
        """Assert the HTTPSPoolKey fields are honored when selecting a pool."""
        connection_pool_kw = [
            ('timeout', timeout.Timeout(3.14)),
            ('retries', retry.Retry(total=6, connect=2)),
            ('block', True),
            ('source_address', '127.0.0.1'),
            ('key_file', DEFAULT_CERTS['keyfile']),
            ('cert_file', DEFAULT_CERTS['certfile']),
            ('cert_reqs', 'CERT_REQUIRED'),
            ('ca_certs', DEFAULT_CA),
            ('ca_cert_dir', DEFAULT_CA_DIR),
            ('ssl_version', 'SSLv23'),
            ('ssl_context', ssl_.create_urllib3_context()),
        ]
        p = PoolManager()
        self.addCleanup(p.clear)
        conn_pools = [
            p.connection_from_url('https://example.com/'),
            p.connection_from_url('https://example.com:4333/'),
            p.connection_from_url('https://other.example.com/'),
        ]
        # Asking for a connection pool with the same key should give us an
        # existing pool.
        dup_pools = []

        for key, value in connection_pool_kw:
            p.connection_pool_kw[key] = value
            conn_pools.append(p.connection_from_url('https://example.com/'))
            dup_pools.append(p.connection_from_url('https://example.com/'))

        self.assertTrue(
            all(
                x is not y
                for i, x in enumerate(conn_pools)
                for j, y in enumerate(conn_pools)
                if i != j
            )
        )
        self.assertTrue(all(pool in conn_pools for pool in dup_pools))
        self.assertTrue(
            all(
                isinstance(key, PoolKey)
                for key in p.pools.keys())
        )

    def test_default_pool_key_funcs_copy(self):
        """Assert each PoolManager gets a copy of ``pool_keys_by_scheme``."""
        p = PoolManager()
        self.addCleanup(p.clear)
        self.assertEqual(p.key_fn_by_scheme, p.key_fn_by_scheme)
        self.assertFalse(p.key_fn_by_scheme is key_fn_by_scheme)

    def test_pools_keyed_with_from_host(self):
        """Assert pools are still keyed correctly with connection_from_host."""
        ssl_kw = [
            ('key_file', DEFAULT_CERTS['keyfile']),
            ('cert_file', DEFAULT_CERTS['certfile']),
            ('cert_reqs', 'CERT_REQUIRED'),
            ('ca_certs', DEFAULT_CA),
            ('ca_cert_dir', DEFAULT_CA_DIR),
            ('ssl_version', 'SSLv23'),
            ('ssl_context', ssl_.create_urllib3_context()),
        ]
        p = PoolManager()
        self.addCleanup(p.clear)
        conns = []
        conns.append(
            p.connection_from_host('example.com', 443, scheme='https')
        )

        for k, v in ssl_kw:
            p.connection_pool_kw[k] = v
            conns.append(
                p.connection_from_host('example.com', 443, scheme='https')
            )

        self.assertTrue(
            all(
                x is not y
                for i, x in enumerate(conns)
                for j, y in enumerate(conns)
                if i != j
            )
        )

    def test_https_connection_from_url_case_insensitive(self):
        """Assert scheme case is ignored when pooling HTTPS connections."""
        p = PoolManager()
        self.addCleanup(p.clear)
        pool = p.connection_from_url('https://example.com/')
        other_pool = p.connection_from_url('HTTPS://EXAMPLE.COM/')

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_https_connection_from_host_case_insensitive(self):
        """Assert scheme case is ignored when getting the https key class."""
        p = PoolManager()
        self.addCleanup(p.clear)
        pool = p.connection_from_host('example.com', scheme='https')
        other_pool = p.connection_from_host('EXAMPLE.COM', scheme='HTTPS')

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_https_connection_from_context_case_insensitive(self):
        """Assert scheme case is ignored when getting the https key class."""
        p = PoolManager()
        self.addCleanup(p.clear)
        context = {'scheme': 'https', 'host': 'example.com', 'port': '443'}
        other_context = {'scheme': 'HTTPS', 'host': 'EXAMPLE.COM', 'port': '443'}
        pool = p.connection_from_context(context)
        other_pool = p.connection_from_context(other_context)

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_http_connection_from_url_case_insensitive(self):
        """Assert scheme case is ignored when pooling HTTP connections."""
        p = PoolManager()
        pool = p.connection_from_url('http://example.com/')
        other_pool = p.connection_from_url('HTTP://EXAMPLE.COM/')

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_http_connection_from_host_case_insensitive(self):
        """Assert scheme case is ignored when getting the https key class."""
        p = PoolManager()
        self.addCleanup(p.clear)
        pool = p.connection_from_host('example.com', scheme='http')
        other_pool = p.connection_from_host('EXAMPLE.COM', scheme='HTTP')

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_http_connection_from_context_case_insensitive(self):
        """Assert scheme case is ignored when getting the https key class."""
        p = PoolManager()
        self.addCleanup(p.clear)
        context = {'scheme': 'http', 'host': 'example.com', 'port': '8080'}
        other_context = {'scheme': 'HTTP', 'host': 'EXAMPLE.COM', 'port': '8080'}
        pool = p.connection_from_context(context)
        other_pool = p.connection_from_context(other_context)

        self.assertEqual(1, len(p.pools))
        self.assertTrue(pool is other_pool)
        self.assertTrue(all(isinstance(key, PoolKey) for key in p.pools.keys()))

    def test_custom_pool_key(self):
        """Assert it is possible to define a custom key function."""
        p = PoolManager(10)
        self.addCleanup(p.clear)

        p.key_fn_by_scheme['http'] = lambda x: tuple(x['key'])
        pool1 = p.connection_from_url(
            'http://example.com', pool_kwargs={'key': 'value'})
        pool2 = p.connection_from_url(
            'http://example.com', pool_kwargs={'key': 'other'})
        pool3 = p.connection_from_url(
            'http://example.com', pool_kwargs={'key': 'value', 'x': 'y'})

        self.assertEqual(2, len(p.pools))
        self.assertTrue(pool1 is pool3)
        self.assertFalse(pool1 is pool2)

    def test_override_pool_kwargs_url(self):
        """Assert overriding pool kwargs works with connection_from_url."""
        p = PoolManager(block=False)
        pool_kwargs = {'retries': 100, 'block': True}

        default_pool = p.connection_from_url('http://example.com/')
        override_pool = p.connection_from_url(
            'http://example.com/', pool_kwargs=pool_kwargs)

        self.assertEqual(retry.Retry.DEFAULT, default_pool.retries)
        self.assertFalse(default_pool.block)

        self.assertEqual(100, override_pool.retries)
        self.assertTrue(override_pool.block)

    def test_override_pool_kwargs_host(self):
        """Assert overriding pool kwargs works with connection_from_host"""
        p = PoolManager(block=False)
        pool_kwargs = {'retries': 100, 'block': True}

        default_pool = p.connection_from_host('example.com', scheme='http')
        override_pool = p.connection_from_host('example.com', scheme='http',
                                               pool_kwargs=pool_kwargs)

        self.assertEqual(retry.Retry.DEFAULT, default_pool.retries)
        self.assertFalse(default_pool.block)

        self.assertEqual(100, override_pool.retries)
        self.assertTrue(override_pool.block)

    def test_merge_pool_kwargs(self):
        """Assert _merge_pool_kwargs works in the happy case"""
        p = PoolManager(block=False)
        merged = p._merge_pool_kwargs({'new_key': 'value'})
        self.assertEqual({'block': False, 'new_key': 'value'}, merged)

    def test_merge_pool_kwargs_none(self):
        """Assert false-y values to _merge_pool_kwargs result in defaults"""
        p = PoolManager(strict=True)
        merged = p._merge_pool_kwargs({})
        self.assertEqual(p.connection_pool_kw, merged)
        merged = p._merge_pool_kwargs(None)
        self.assertEqual(p.connection_pool_kw, merged)

    def test_merge_pool_kwargs_remove_key(self):
        """Assert keys can be removed with _merge_pool_kwargs"""
        p = PoolManager(strict=True)
        merged = p._merge_pool_kwargs({'strict': None})
        self.assertTrue('strict' not in merged)

    def test_merge_pool_kwargs_invalid_key(self):
        """Assert removing invalid keys with _merge_pool_kwargs doesn't break"""
        p = PoolManager(strict=True)
        merged = p._merge_pool_kwargs({'invalid_key': None})
        self.assertEqual(p.connection_pool_kw, merged)


if __name__ == '__main__':
    unittest.main()
