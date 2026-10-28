class StaleVersionError(Exception):
    """The client edited an older version of the row than the one now stored."""


def require_version(entity, expected: "int | None") -> None:
    """Compare under the Trip lock, so the check and the write see the same row."""
    if expected is not None and entity.version != expected:
        raise StaleVersionError()
