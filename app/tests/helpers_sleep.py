"""A ``time.sleep`` stand-in for one test's own thread.

Patching ``<module>.time.sleep`` replaces ``time.sleep`` for the whole process. A
background thread still running from an earlier test (a hub module's monitor or
worker loop) then calls the stand-in too: a no-op makes that thread spin and starve
the test, and a counting stand-in counts its calls. Either way a test could run for
ever (seen when the loose app/test_*.py files moved into app/tests and the run order
changed). With ``own_thread_sleep(fake)`` only the thread that patched it gets
``fake``; every other thread sleeps for real.
"""

import threading
import time


def own_thread_sleep(fake):
    """``fake`` for the calling thread, the real ``time.sleep`` for any other."""
    real = time.sleep
    owner = threading.get_ident()

    def sleep(seconds):
        if threading.get_ident() == owner:
            return fake(seconds)
        return real(seconds)

    return sleep
