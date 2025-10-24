from __future__ import annotations

import sys

from cli.index import main as cli_main


def main(argv: list[str] | None = None) -> None:
    cli_main(["query", *(argv or sys.argv[1:])])


if __name__ == "__main__":
    main()
