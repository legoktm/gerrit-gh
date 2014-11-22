#!/usr/bin/env python3

import hashlib
import json
import os
import pprint
import subprocess
import tempfile

import github

import dbstore


class GerritGitHubSyncBot(object):
    def __init__(self, config):
        self.config = config
        self._mw = None
        self._gh = None
        self._store = None

    def process_pull_request(self, repo, pr):
        """
        :type pr: github.PullRequest.PullRequest
        """
        cwd = os.getcwd()
        os.chdir(self.local_repo_path(repo))
        patch_url = pr.patch_url
        local_path = os.path.abspath(patch_url.split('/')[-1])
        self.debug(pr.title)
        self.debug(pr.body)
        if os.path.exists(local_path):
            self.debug('Removing %s' % local_path)
            os.unlink(local_path)
        self.shell_exec(['wget', pr.patch_url])
        with open(local_path) as f:
            content = f.read()
        md5 = hashlib.md5(content.encode()).hexdigest()
        row = self.store.select_from_url(patch_url)
        if row:
            if row['hash'] == md5:
                return
            else:
                self.update_pull_req(repo, pr, local_path, md5, changeid=row['changeid'])
        else:
            self.update_pull_req(repo, pr, local_path, md5)
        #print(info['patch_url'])
        #pprint.pprint(info, indent=4)
        self.debug(pr.html_url)
        os.chdir(cwd)
        quit()

    def update_pull_req(self, repo, pr, patchfile, md5, changeid=None):
        """
        Assumes that cwd is the repository

        :param repo: Repository name
        :type repo: str
        :param pr: dict of info returned by the API
        :type pr: github.PullRequest.PullRequest
        :param patchfile: path to the patch file
        :type patchfile: str
        :param md5: md5 hash of the patch file
        :param changeid: if there's already a gerrit change, the change-id of it
        """
        commits = self.shell_exec(['git', 'am', patchfile])
        # Output looks like: "Applying foo\nApplying bar\n"
        count = len(commits.strip().splitlines())
        # https://stackoverflow.com/questions/5189560/squash-my-last-x-commits-together-using-git
        self.shell_exec(['git', 'reset', '--soft', 'HEAD~%s' % count])
        # Build a commit message!
        # First see if we can grab a Bug: footer, it has to be at the bottom
        body = pr.body
        lines = body.strip().splitlines()
        bug = None
        if lines[-1].startswith('Bug: '):
            bug = lines[-1]
            body = '\n'.join(lines[:-1])

        commit_msg = pr.title + '\n'
        commit_msg += body
        commit_msg += '\n'
        commit_msg += 'Closes ' + pr.html_url + '\n'  # For GH's auto-close thingy
        if bug:
            commit_msg += bug + '\n'

        if changeid:
            commit_msg += 'Change-Id: ' + changeid + '\n'
        author = '{name} <{email}>'.format(name=pr.user.name, email=pr.user.email)
        self.shell_exec(['git', 'commit', '-a', '-F', '-', '--author=%s' % author], input=commit_msg.encode())
        # Write down the change-id if we created a new one...
        if not changeid:
            msg = self.shell_exec(['git', 'log', '-1'])
            changeid = msg.splitlines()[-1].strip().split(':', 1)[1]
            self.store.insert(pr.patch_url, changeid, repo, md5)

        self.shell_exec(['git', 'push', 'gerrit', 'HEAD:refs/for/master'])  # TODO: Don't hardcode master
        comment = 'This pull request has been imported into Gerrit, our code review system.' \
                  ' Discussion and review will take place at https://gerrit.wikimedia.org/r/#q,%s,n,z' % changeid
        pr.create_issue_comment(comment)

    def run(self):
        self.init()
        for repo in self.config['repos']:
            gh_repo = self.gh.get_repo('%s/%s' % (self.config['gh.account'], repo))
            for pr in gh_repo.get_pulls(state='open'):
                self.process_pull_request(repo, pr)
        pass

    @property
    def gh(self):
        if self._gh is None:
            self._gh = github.Github(
                self.config['gh.username'],
                self.config['gh.password']
            )
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
        Load password
        """
        if 'gh.password_file' in self.config:
            with open(os.path.expanduser(self.config['gh.password_file'])) as f:
                self.config['gh.password'] = f.read().strip()

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
                self.shell_exec(['git', 'review', '-s'], input=self.config['gerrit.username'].encode())
                os.chdir(cwd)
            else:
                os.chdir(path)
                self.shell_exec(['git', 'reset', '--hard'])
                self.shell_exec(['git', 'fetch', 'origin'])
                self.shell_exec(['git', 'checkout', 'origin/master'])
                os.chdir(cwd)


with open('config.json') as f:
    config = json.load(f)
sync = GerritGitHubSyncBot(config)

if __name__ == '__main__':
    sync.run()
