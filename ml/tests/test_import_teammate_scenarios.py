import csv
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from ml.import_teammate_scenarios import convert, DAY_ZERO_MS


def raw(node, seconds):
    return {
        "id": node, "ts": DAY_ZERO_MS + seconds * 1000,
        "tx": DAY_ZERO_MS + seconds * 1000, "seq": 1 + seconds // 10,
        "kind": "periodic", "v": 1, "boot_id": "1234abcd",
        "values": {"PM2.5": 12, "PM10": 20, "temperature": 25, "humidity": 45},
    }


def make_zip(filename, seed, scenario="fuego_lento"):
    truth = {
        "escenario": scenario, "seed": seed, "nodos": [496],
        "alarma_esperada": scenario.startswith("fuego"),
        "nodos_detalle": {"496": {"humo_empieza_s": 20, "llega_fuego_s": 40}}
        if scenario.startswith("fuego") else {},
    }
    with ZipFile(filename, "w") as z:
        z.writestr(scenario + ".jsonl", "\n".join(
            json.dumps(raw(496, seconds)) for seconds in (0, 10, 20, 30, 40, 50)) + "\n")
        z.writestr(scenario + "_verdad.json", json.dumps(truth))


class ImportTests(unittest.TestCase):
    def test_external_labels_do_not_leak_into_readings(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            make_zip(folder / "source.zip", 42)
            report = convert(folder / "source.zip", folder / "out")
            self.assertEqual(report["label_1"], 4)
            self.assertEqual(report["label_0"], 2)
            with (folder / "out" / "truth.csv").open(newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([int(row["label"]) for row in rows], [0, 0, 1, 1, 1, 1])
            self.assertEqual(rows[0]["split"], "pending")
            self.assertEqual(rows[-1]["exposure_state"], "fire_front")
            msg = json.loads((folder / "out" / "readings.jsonl").read_text().splitlines()[0])
            self.assertEqual(msg["measurements"]["pm10_ug_m3"], 20)
            self.assertNotIn("label", msg)
            self.assertNotIn("emitted_at", msg)

    def test_single_seed_cannot_be_both_train_and_test(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            make_zip(folder / "source.zip", 42)
            with self.assertRaisesRegex(ValueError, ">=2"):
                convert(folder / "source.zip", folder / "out", test_seeds=[42])

    def test_requires_separate_truth_file(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with ZipFile(folder / "source.zip", "w") as z:
                z.writestr("fuego_lento.jsonl", json.dumps(raw(496, 0)))
            with self.assertRaisesRegex(ValueError, "Missing truth"):
                convert(folder / "source.zip", folder / "out")


    def test_multi_seed_split_preserves_all_scenarios(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with ZipFile(folder / "seeds.zip", "w") as archive:
                for seed in (42, 7):
                    for scenario in ("fuego_lento", "polvo_tractor"):
                        truth = {
                            "escenario": scenario, "seed": seed, "nodos": [496],
                            "alarma_esperada": scenario.startswith("fuego"),
                            "nodos_detalle": {"496": {"humo_empieza_s": 20, "llega_fuego_s": 40}}
                            if scenario.startswith("fuego") else {},
                        }
                        archive.writestr(f"{seed}/{scenario}.jsonl", "\n".join(
                            json.dumps(raw(496, secs)) for secs in (0, 10, 20, 30, 40, 50)) + "\n")
                        archive.writestr(f"{seed}/{scenario}_verdad.json", json.dumps(truth))
            report = convert(folder / "seeds.zip", folder / "out", test_seeds=[7])
            self.assertEqual(report["readings_rows"], 24)
            self.assertEqual(len(report["scenarios"]), 4)
            self.assertEqual({x["split"] for x in report["scenarios"].values()}, {"train", "test"})



if __name__ == "__main__":
    unittest.main()
