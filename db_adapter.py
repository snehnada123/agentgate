"""Small DB-API compatibility adapter; PostgreSQL is mandatory on Vercel."""
class Row(dict):
    def __getitem__(self,key):return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)
class Cursor:
    def __init__(self,c):self.c=c
    @property
    def rowcount(self):return self.c.rowcount
    def fetchone(self):
        r=self.c.fetchone();return Row(r) if r is not None else None
    def __iter__(self):return (Row(r) for r in self.c)
class Postgres:
    def __init__(self,url):
        import psycopg
        from psycopg.rows import dict_row
        self.db=psycopg.connect(url,autocommit=True,row_factory=dict_row,connect_timeout=10)
    def execute(self,sql,args=()):return Cursor(self.db.execute(sql.replace('BEGIN IMMEDIATE','BEGIN').replace('?','%s'),args))
    def executescript(self,sql):
        for statement in sql.split(';'):
            if statement.strip():self.db.execute(statement)
    def close(self):self.db.close()
