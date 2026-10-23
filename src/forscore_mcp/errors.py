"""Exception hierarchy. Every message is written to be shown to an end user as-is."""


class ForScoreError(Exception):
    """Base class for all errors raised by forscore-mcp."""


class LibraryNotFoundError(ForScoreError):
    """The forScore library file does not exist or cannot be read."""


class SchemaError(ForScoreError):
    """The library database does not have the structure this tool understands."""


class AppRunningError(ForScoreError):
    """forScore is running, so writing to its library is unsafe."""


class DirectWritesDisabledError(ForScoreError):
    """A direct database write was requested while direct writes are off."""


class ChangesetError(ForScoreError):
    """A changeset is malformed or refers to something that does not exist."""


class NotFoundError(ForScoreError):
    """A score, value or backup could not be found."""
