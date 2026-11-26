"""Entry of `python -m code_factory.runs.adapters.runner`."""

import sys

from code_factory.runs.adapters.runner.wrapper import main

sys.exit(main(sys.argv[1:]))
