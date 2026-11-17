from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from demo import run_demo


def main():
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    with TemporaryDirectory(prefix='river-verification-') as directory:
        run_demo(str(Path(directory) / 'demo.sqlite3'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
