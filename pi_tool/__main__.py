from __future__ import annotations

import multiprocessing
import sys


def main() -> int:
    multiprocessing.freeze_support()
    from pi_tool.app.main_window import run_app

    return run_app(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
