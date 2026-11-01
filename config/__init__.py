# MySQL driver: Django uses `mysqlclient` (in requirements.txt).
# If mysqlclient can't be installed on your machine, run `pip install pymysql`
# and this fallback makes Django use PyMySQL instead.
try:
    import MySQLdb  # noqa: F401  (mysqlclient)
except ImportError:
    try:
        import pymysql

        pymysql.version_info = (2, 2, 1, "final", 0)  # satisfy Django's minimum-version check
        pymysql.install_as_MySQLdb()
    except ImportError:
        pass
