"""Support ``python -m daspull.cli`` alongside the installed ``daspull`` script."""

from . import main

raise SystemExit(main())
