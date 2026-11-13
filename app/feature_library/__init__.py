"""
One feature library for the research labs (PTAI-RD-001 work package 4.1; architecture
layer L2): ``base`` is the registry and its as-of rules, ``builtin`` the features it
starts with. Nothing in trading reads it.
"""

from feature_library import builtin as _builtin  # noqa: F401
from feature_library.base import (  # noqa: F401
    FEATURES,
    Feature,
    as_of_problems,
    compute,
    get,
    key,
    register,
)
