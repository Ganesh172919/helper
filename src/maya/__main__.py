"""Allow `python -m maya` to launch the same locally installed application."""

from .main import main

raise SystemExit(main())
