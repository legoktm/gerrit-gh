#!/usr/bin/env python

import requests


class MediaWiki(object):
    def __init__(self, index):
        self.index = index

    def json_content(self, title):
        r = requests.get(self.index, params={
            'action': 'raw',
            'title': title,
        })
        return r.json()

