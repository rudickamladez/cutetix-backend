"""Module for working with git"""
import git


class Git:
    """Class for working with git"""
    def __init__(self):
        self.repo = git.Repo(search_parent_directories=True)
        self.cmd = self.repo.git

    async def pull(self):
        """Method for `git pull`"""
        return self.cmd.pull()

    def short_hash(self):
        """Method for get short hash"""
        return self.repo.head.object.hexsha[:7]
