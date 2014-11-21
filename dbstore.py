#!/usr/bin/env python3

from sqlalchemy import create_engine, Table, MetaData, Column, String
from sqlalchemy.sql import select


class DBStore:
    def __init__(self, location, echo=False):
        self.engine = create_engine(location, echo=echo)
        metadata = MetaData()
        self.pull_requests = Table(
            'pull_requests', metadata,
            # Full url to the pull request .patch file
            Column('url', String, primary_key=True),
            # Change id for the gerrit change
            Column('changeid', String, nullable=False),
            # GitHub repo name
            Column('repo', String, nullable=False),
            # md5 of the .patch for the pull request to see if anything has changed.
            Column('hash', String, nullable=False)
        )
        metadata.create_all(self.engine)

    def insert(self, url, changeid, repo, hash_):
        ins = self.pull_requests.insert()
        conn = self.engine.connect()
        conn.execute(ins, url=url, changeid=changeid, repo=repo, hash=hash_)

    def select_from_url(self, url):
        s = select([self.pull_requests]).where(self.pull_requests.c.url == url)
        result = self.engine.connect().execute(s)
        row = result.fetchone()
        result.close()
        return row

if __name__ == '__main__':
    store = DBStore('sqlite:///:memory:', echo=True)
    print(store.select_from_url('foobaz'))
