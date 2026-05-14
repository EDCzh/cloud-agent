import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))


try:
    import dbutils.pooled_db  # noqa: F401
except ModuleNotFoundError:
    dbutils_module = types.ModuleType("dbutils")
    pooled_db_module = types.ModuleType("dbutils.pooled_db")

    class MissingPooledDB:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Test should replace PooledDB before use")

    pooled_db_module.PooledDB = MissingPooledDB
    dbutils_module.pooled_db = pooled_db_module
    sys.modules["dbutils"] = dbutils_module
    sys.modules["dbutils.pooled_db"] = pooled_db_module


server = importlib.import_module("mcp_servers.cloud_platform_server")


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakePooledDB:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.connections = []
        self.closed = False
        FakePooledDB.instances.append(self)

    def connection(self):
        connection = FakeConnection()
        self.connections.append(connection)
        return connection

    def close(self):
        self.closed = True


class MySQLPoolTests(unittest.TestCase):
    def setUp(self):
        FakePooledDB.instances.clear()
        server._mysql_pool = None
        server.PooledDB = FakePooledDB

    def tearDown(self):
        server._mysql_pool = None

    def test_pool_uses_env_configuration(self):
        env = {
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_PORT": "3307",
            "MYSQL_USER": "cloud_user",
            "MYSQL_PASSWORD": "cloud_password",
            "MYSQL_DATABASE": "cloud_test",
            "MYSQL_POOL_MINCACHED": "2",
            "MYSQL_POOL_MAXCACHED": "4",
            "MYSQL_POOL_MAXCONNECTIONS": "8",
            "MYSQL_POOL_BLOCKING": "true",
            "MYSQL_POOL_PING": "1",
            "MYSQL_CHARSET": "utf8mb4",
            "MYSQL_AUTOCOMMIT": "true",
            "MYSQL_CONNECT_TIMEOUT": "3",
            "MYSQL_READ_TIMEOUT": "11",
            "MYSQL_WRITE_TIMEOUT": "12",
        }

        with patch.dict(os.environ, env, clear=False):
            connection = server.get_db_connection()

        self.assertIsInstance(connection, FakeConnection)
        self.assertEqual(len(FakePooledDB.instances), 1)
        config = FakePooledDB.instances[0].kwargs
        self.assertIs(config["creator"], server.pymysql)
        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["port"], 3307)
        self.assertEqual(config["user"], "cloud_user")
        self.assertEqual(config["password"], "cloud_password")
        self.assertEqual(config["database"], "cloud_test")
        self.assertEqual(config["mincached"], 2)
        self.assertEqual(config["maxcached"], 4)
        self.assertEqual(config["maxconnections"], 8)
        self.assertTrue(config["blocking"])
        self.assertEqual(config["ping"], 1)
        self.assertEqual(config["charset"], "utf8mb4")
        self.assertTrue(config["autocommit"])
        self.assertEqual(config["connect_timeout"], 3)
        self.assertEqual(config["read_timeout"], 11)
        self.assertEqual(config["write_timeout"], 12)

    def test_pool_is_lazy_and_reused(self):
        first = server.get_db_connection()
        second = server.get_db_connection()

        self.assertIsNot(first, second)
        self.assertEqual(len(FakePooledDB.instances), 1)
        self.assertEqual(len(FakePooledDB.instances[0].connections), 2)

    def test_close_mysql_pool_closes_and_resets_pool(self):
        pool = server.get_mysql_pool()
        server.close_mysql_pool()

        self.assertTrue(pool.closed)
        self.assertIsNone(server._mysql_pool)


if __name__ == "__main__":
    unittest.main()
