import argparse
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import datasets


class DataSelectionTests(unittest.TestCase):
    def test_inclusive_range_and_invalid_order(self):
        self.assertEqual(len(datasets.dates("2022-03-09", "2022-03-15")), 7)
        with self.assertRaises(ValueError):
            datasets.dates("2022-03-15", "2022-03-09")

    def test_relative_path_is_anchored_to_repository(self):
        self.assertEqual(datasets.resolve_path("data/raw"), datasets.ROOT / "data/raw")

    def test_missing_and_ambiguous_days_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "GAU"
            folder.mkdir()
            first = folder / "20220309_Viajes_GAU.csv.gz"
            first.touch()
            with self.assertRaisesRegex(ValueError, "2022-03-10"):
                datasets.get_files("gau", "2022-03-09", "2022-03-10", tmp)
            self.assertEqual(datasets.get_files("gau", "2022-03-09", "2022-03-09", tmp), [first])
            (folder / "20220309_Viajes_GAU_v2.csv.gz").touch()
            with self.assertRaisesRegex(ValueError, "multiple files"):
                datasets.get_files("gau", "2022-03-09", "2022-03-09", tmp)

    def download_args(self, tmp, dry_run=False):
        return argparse.Namespace(
            level="gau", start="2022-03-09", end="2022-03-09",
            url_template="https://example.invalid/{year}/{date}_Viajes_GAU.csv",
            download_dir=tmp, dry_run=dry_run,
        )

    def test_download_plan_never_calls_network_or_creates_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(datasets, "urlopen") as network, redirect_stdout(StringIO()):
                datasets.download(datasets.load_config(), self.download_args(tmp, True))
                network.assert_not_called()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_download_rejects_html_and_removes_owned_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(datasets, "urlopen", return_value=BytesIO(b"<html>error</html>")):
                with redirect_stdout(StringIO()), self.assertRaises(ValueError):
                    datasets.download(datasets.load_config(), self.download_args(tmp))
            self.assertEqual(list((Path(tmp) / "GAU").iterdir()), [])

    def test_download_accepts_csv_then_skips_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = b"fecha|zona\n20220309|01001\n"
            with patch.object(datasets, "urlopen", return_value=BytesIO(body)) as network:
                with redirect_stdout(StringIO()):
                    datasets.download(datasets.load_config(), self.download_args(tmp))
                    datasets.download(datasets.load_config(), self.download_args(tmp))
                self.assertEqual(network.call_count, 1)
            self.assertEqual((Path(tmp) / "GAU/20220309_Viajes_GAU.csv").read_bytes(), body)


if __name__ == "__main__":
    unittest.main()
