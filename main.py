#!/usr/bin/env python3

import hashlib
import json
import os
import pprint
import subprocess
import tempfile

import dbstore
import github
import mediawiki


class GerritGitHubSyncBot(object):
    def __init__(self, config):
        self.config = config
        self._mw = None
        self._gh = None
        self._store = None

    def process_pull_request(self, repo, info):
        cwd = os.getcwd()
        os.chdir(self.local_repo_path(repo))
        patch_url = info['patch_url']
        local_path = os.path.abspath(patch_url.split('/')[-1])
        self.debug(info['title'])
        self.debug(info['body'])
        if os.path.exists(local_path):
            self.debug('Removing %s' % local_path)
            os.unlink(local_path)
        self.shell_exec(['wget', info['patch_url']])
        with open(local_path) as f:
            content = f.read()
        md5 = hashlib.md5(content.encode()).hexdigest()
        row = self.store.select_from_url(patch_url)
        if row:
            if row['hash'] == md5:
                return
            else:
                self.update_pull_req(repo, info, local_path, changeid=row['changeid'])
        else:
            self.update_pull_req(repo, info, local_path)
        #print(info['patch_url'])
        #pprint.pprint(info, indent=4)
        self.debug(info['html_url'])
        os.chdir(cwd)
        quit()

    def save_to_tmpfile(self, msg):
        fh, path = tempfile.mkstemp('.txt', prefix='msg', text=True)
        fh.write(msg)
        fh.close()
        return path

    def update_pull_req(self, repo, info, patchfile, changeid=None):
        """
        Assumes that cwd is the repository

        :param repo: Repository name
        :type repo: str
        :param info: dict of info returned by the API
        :type info: dict
        :param patchfile: path to the patch file
        :type patchfile: str
        :param changeid: if there's already a gerrit change, the change-id of it
        """
        commits = self.shell_exec(['git', 'am', patchfile])
        # Output looks like: "Applying foo\nApplying bar\n"
        count = len(commits.strip().splitlines())
        # https://stackoverflow.com/questions/5189560/squash-my-last-x-commits-together-using-git
        self.shell_exec(['git', 'reset', '--soft', 'HEAD~%s' % count])
        # Build a commit message!
        # First see if we can grab a Bug: footer, it has to be at the bottom
        lines = info['body'].strip().splitlines()
        bug = None
        if lines[-1].startswith('Bug: '):
            bug = lines[-1]
            info['body'] = '\n'.join(lines[:-1])

        commit_msg = info['title'] + '\n'
        commit_msg += info['body']
        commit_msg += '\n'
        commit_msg += 'Closes ' + info['html_url'] + '\n'  # For GH's auto-close thingy
        if bug:
            commit_msg += bug + '\n'
        author = self.gh.get_author_string(info['user']['login'])
#        print(author)
        #cm_path = self.save_to_tmpfile(commit_msg)
        self.shell_exec(['git', 'commit', '-a', '-F', '-', '--author=%s' % author], input=commit_msg.encode())
        pass

    def run(self):
        self.init()
        for repo in self.config['repos']:
            prs = self.gh.get_pull_requests(self.config['gh.account'], repo)
            for pr in prs:
                self.process_pull_request(repo, pr)
        pass

    @property
    def mw(self):
        if self._mw is None:
            self._mw = mediawiki.MediaWiki(self.config['mw.index'])
        return self._mw

    @property
    def gh(self):
        if self._gh is None:
            self._gh = github.Github('https://api.github.com')
        return self._gh

    @property
    def store(self):
        if self._store is None:
            self._store = dbstore.DBStore('sqlite:///' + os.path.expanduser(self.config['db.location']))
        return self._store

    def init(self):
        self.init_config()
        self.init_repos()

    def debug(self, msg):
        print(msg)

    def init_config(self):
        """
        Load on-wiki config
        """
        on_wiki_config = self.mw.json_content(self.config['mw.page'])
        on_wiki_config.update(self.config)
        self.config = on_wiki_config

    def local_repo_path(self, name):
        return os.path.join(os.path.expanduser(self.config['git.repo_path']), name)

    def shell_exec(self, args, **kwargs):
        """
        Shortcut wrapper to execute a shell command

        >>> GerritGitHubSyncBot().shell_exec(['ls', '-l'])
        """
        self.debug(' '.join(args))
        return subprocess.check_output(args, **kwargs).decode()

    def init_repos(self):
        repo_path = os.path.expanduser(self.config['git.repo_path'])
        self.shell_exec(['mkdir', '-p', repo_path])
        for name in self.config['repos']:
            cwd = os.getcwd()
            self.debug(name)
            path = self.local_repo_path(name)
            self.debug(path)
            if not os.path.isdir(path):
                os.chdir(repo_path)
                clone_url = self.config['git.clone'].replace('$1', name)
                self.shell_exec(['git', 'clone', clone_url])
                os.chdir(path)
                self.shell_exec(['git', 'checkout', 'origin/master'])
                self.shell_exec(['git', 'review', '-s'])
                os.chdir(cwd)
            else:
                os.chdir(path)
                self.shell_exec(['git', 'reset', '--hard'])
                self.shell_exec(['git', 'fetch', 'origin'])
                self.shell_exec(['git', 'checkout', 'origin/master'])
                os.chdir(cwd)


if __name__ == '__main__':
    with open('config.json') as f:
        config = json.load(f)
    sync = GerritGitHubSyncBot(config)
    sync.run()
