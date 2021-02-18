import os
import subprocess
import logging
import time
import argparse
import datetime

# from git import Repo
from googleapiclient.http import MediaIoBaseDownload
from traitlets import Integer, default
from traitlets.config import Configurable

import git
import os.path
import io
from nbgitpuller.plugins.Folder.nbgitpuller.pull import execute_cmd

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from functools import partial


class GooglePuller(Configurable):

    @default('depth')
    def _depth_default(self):
        """This is a workaround for setting the same default directly in the
        definition of the traitlet above. Without it, the test fails because a
        change in the environment variable has no impact. I think this is a
        consequence of the tests not starting with a totally clean environment
        where the GooglePuller class hadn't been loaded already."""
        return int(os.environ.get('NBGITPULLER_DEPTH', 1))

    def __init__(self, git_url, branch_name, repo_dir, file_id, student, service, **kwargs):
        #assert git_url and branch_name

        # URLs of git
        self.git_url = git_url
        self.branch_name = branch_name
        self.repo_dir = repo_dir

        self.temp_repo = None
        self.service = service
        # unique identifier of student after authentication
        self.student = str(student)

        self.file_id = str(file_id)
        self.file_path = ""
        newargs = {k: v for k, v in kwargs.items() if v is not None}
        #super(GooglePuller, self).__init__(**newargs)

    async def fetch(self):
        """
        fetches the file from the file name given and downloads it to directory
        """

        file_id = self.file_id
        request = self.service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print("Download %d%%." % int(status.progress() * 100))

    async def createRepo(self):
        """
        Creates a new, hidden remote git repo to push google drive folder into
        """
        repo_dir = os.path.join(self.repo_dir, self.student)
        file_path = os.path.join(repo_dir, self.file_id)
        self.file_path = file_path

        r = git.Repo.init(repo_dir)
        # This function just creates an empty file ...
        open(file_path, 'wb').close()
        r.index.add([file_path])
        r.index.commit("initial commit")

    async def checkIfRepoExists(self):
        """
        Checks to see if the hidden repo already exists
        """

        repo_dir = os.path.join(self.repo_dir, self.student)
        repo = git.Repo(repo_dir)

        if not repo.exists():
            await self.createRepo()
        else:
            await self.pushHidden()

        # empty_repo = git.Repo.init(os.path.join(self.repo_dir, self.student))
        # origin = empty_repo.create_remote('origin', repo.remotes.origin.url)
        # assert origin.exists()

    async def pushHidden(self):
        """
        pushes google drive file to hidden repo
        """

        open(self.file_path, 'wb').close()
        r.index.add([self.file_path])
        r.index.commit("hidden commit")

    def pull(self):
        """
        Pull selected repo from a remote git repository,
        while preserving user changes
        """
        if not os.path.exists(self.repo_dir):
            yield from self.initialize_repo()
        else:
            yield from self.update()

    def initialize_repo(self):
        """
        Clones repository
        """
        logging.info('Repo {} doesn\'t exist. Cloning...'.format(self.repo_dir))
        clone_args = ['git', 'clone']
        if self.depth and self.depth > 0:
            clone_args.extend(['--depth', str(self.depth)])
        clone_args.extend(['--branch', self.branch_name])
        clone_args.extend([self.git_url, self.repo_dir])
        yield from execute_cmd(clone_args)
        logging.info('Repo {} initialized'.format(self.repo_dir))

    def reset_deleted_files(self):
        """
        Runs the equivalent of git checkout -- <file> for each file that was
        deleted. This allows us to delete a file, hit an interact link, then get a
        clean version of the file again.
        """

        yield from self.ensure_lock()
        deleted_files = subprocess.check_output([
            'git', 'ls-files', '--deleted', '-z'
        ], cwd=self.repo_dir).decode().strip().split('\0')

        for filename in deleted_files:
            if filename:  # Filter out empty lines
                yield from execute_cmd(['git', 'checkout', 'origin/{}'.format(self.branch_name), '--', filename],
                                       cwd=self.repo_dir)

    def repo_is_dirty(self):
        """
        Return true if repo is dirty
        """
        try:
            subprocess.check_call(['git', 'diff-files', '--quiet'], cwd=self.repo_dir)
            # Return code is 0
            return False
        except subprocess.CalledProcessError:
            return True

    def update_remotes(self):
        """
        Do a git fetch so our remotes are up to date
        """
        yield from execute_cmd(['git', 'fetch'], cwd=self.repo_dir)

    def find_upstream_changed(self, kind):
        """
        Return list of files that have been changed upstream belonging to a particular kind of change
        """
        output = subprocess.check_output([
            'git', 'log', '..origin/{}'.format(self.branch_name),
            '--oneline', '--name-status'
        ], cwd=self.repo_dir).decode()
        files = []
        for line in output.split('\n'):
            if line.startswith(kind):
                files.append(os.path.join(self.repo_dir, line.split('\t', 1)[1]))

        return files

    def ensure_lock(self):
        """
        Make sure we have the .git/lock required to do modifications on the repo

        This must be called before any git commands that modify state. This isn't guaranteed
        to be atomic, due to the nature of using files for locking. But it's the best we
        can do right now.
        """
        try:
            lockpath = os.path.join(self.repo_dir, '.git', 'index.lock')
            mtime = os.path.getmtime(lockpath)
            # A lock file does exist
            # If it's older than 10 minutes, we just assume it is stale and take over
            # If not, we fail with an explicit error.
            if time.time() - mtime > 600:
                yield "Stale .git/index.lock found, attempting to remove"
                os.remove(lockpath)
                yield "Stale .git/index.lock removed"
            else:
                raise Exception('Recent .git/index.lock found, operation can not proceed. Try again in a few minutes.')
        except FileNotFoundError:
            # No lock is held by other processes, we are free to go
            return

    def rename_local_untracked(self):
        """
        Rename local untracked files that would require pulls
        """
        # Find what files have been added!
        new_upstream_files = self.find_upstream_changed('A')
        for f in new_upstream_files:
            if os.path.exists(f):
                # If there's a file extension, put the timestamp before that
                ts = datetime.datetime.now().strftime('__%Y%m%d%H%M%S')
                path_head, path_tail = os.path.split(f)
                path_tail = ts.join(os.path.splitext(path_tail))
                new_file_name = os.path.join(path_head, path_tail)
                os.rename(f, new_file_name)
                yield 'Renamed {} to {} to avoid conflict with upstream'.format(f, new_file_name)

    def update(self):
        """
        Do the pulling if necessary
        """
        # Fetch remotes, so we know we're dealing with latest remote
        yield from self.update_remotes()

        # Rename local untracked files that might be overwritten by pull
        yield from self.rename_local_untracked()

        # Reset local files that have been deleted. We don't actually expect users to
        # delete something that's present upstream and expect to keep it. This prevents
        # unnecessary conflicts, and also allows users to click the link again to get
        # a fresh copy of a file they might have screwed up.
        yield from self.reset_deleted_files()

        # If there are local changes, make a commit so we can do merges when pulling
        # We also allow empty commits. On NFS (at least), sometimes repo_is_dirty returns a false
        # positive, returning True even when there are no local changes (git diff-files seems to return
        # bogus output?). While ideally that would not happen, allowing empty commits keeps us
        # resilient to that issue.
        # We explicitly set user info of the commits we are making, to keep that separate from
        # whatever author info is set in system / repo config by the user. We pass '-c' to git
        # itself (rather than to 'git commit') to temporarily set config variables. This is
        # better than passing --author, since git treats author separately from committer.
        if self.repo_is_dirty():
            yield from self.ensure_lock()
            yield from execute_cmd([
                'git',
                '-c', 'user.email=nbgitpuller@nbgitpuller.link',
                '-c', 'user.name=nbgitpuller',
                'commit',
                '-am', 'Automatic commit by nbgitpuller',
                '--allow-empty'
            ], cwd=self.repo_dir)

        # Merge master into local!
        yield from self.ensure_lock()
        yield from execute_cmd([
            'git',
            '-c', 'user.email=nbgitpuller@nbgitpuller.link',
            '-c', 'user.name=nbgitpuller',
            'merge',
            '-Xours', 'origin/{}'.format(self.branch_name)
        ], cwd=self.repo_dir)

