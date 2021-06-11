import asyncio
import functools


# This dict is safe to be shared since the key is a tuple of all arguments including
# including the reference to self.
_in_progress = {}


def remember_progress(fn):
    """
    This decorator memoizes coroutines by wrapping them in futures and storing
    the result in a dictionary keyed to their name and arguments. The dict entry is cleared
    as soon as the future completes because at that point the content is in the database
    and would be retrieved from there anyway on successive calls.

    The idea here is that if multiple calls for the same (or overlapping) snapshots come in
    concurrently, we don't do the same work twice. And more importantly, we don't violate
    uniqueness constraints in the database by inserting the same results multiple times.

    See also: https://en.wikipedia.org/wiki/Cache_stampede
    """
    @functools.wraps(fn)
    async def wrapper(*args):
        ident = (fn.__name__, *args)

        async def _initial():
            _in_progress[ident] = asyncio.ensure_future(fn(*args))
            try:
                return await _in_progress[ident]
            finally:
                del _in_progress[ident]
        return await (_in_progress.get(ident) or _initial())
    return wrapper
