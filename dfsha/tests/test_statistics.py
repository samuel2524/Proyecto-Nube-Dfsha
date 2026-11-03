import tempfile
import unittest
from pathlib import Path
from tests.bench import summarize, validate_summary, write_csv


class Statistics(unittest.TestCase):
    def test_summary_is_reconstructible_and_p95_is_max_for_five(self):
        samples = [{'experiment': 'E', 'condition': 'x', 'operation': 'put', 'MiB': 10,
                    'seconds': n} for n in (1, 2, 3, 4, 5)]
        row = summarize(samples)[0]
        self.assertEqual(row['mean_s'], 3)
        self.assertEqual(row['p95_s'], 5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'summary.csv'
            write_csv(path, [row])
            self.assertEqual(validate_summary(path), [])
            row['p95_s'] = 2
            write_csv(path, [row])
            self.assertTrue(validate_summary(path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
