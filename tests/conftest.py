"""Test-tree configuration.

The suite mirrors ``src/daspull``: ``providers/``, ``datasets/``, and
``configs/`` (one module per dataset config) sit next to ``frontends/`` for the
CLI and the Python API, with the provider-neutral primitives at this level.

Test modules therefore live one directory deeper than :mod:`helpers`, so this
file puts the test root on ``sys.path`` to keep ``from helpers import utc``
working at any depth. Pytest's default ``prepend`` import mode happens to do
the same thing as a side effect of importing this file, but stating it here
means the suite does not depend on that.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
