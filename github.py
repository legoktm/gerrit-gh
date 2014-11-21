#!/usr/bin/env python

import functools
import requests


class Github(object):
    def __init__(self, url):
        self.url = url

    def request(self, endpoint):
        url = self.url + endpoint
        r = requests.get(url)
        return r.json()

    def get_pull_requests(self, owner, repo):
        data = self.request('/repos/{owner}/{repo}/pulls'.format(owner=owner, repo=repo))
        return data

    @functools.lru_cache(maxsize=128)
    def get_author_string(self, username):
        data = self.request('/users/{user}'.format(user=username))
        return '{name} <{email}>'.format(**data)
