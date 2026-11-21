import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from edge.model import ROOT
from lab.promote import validate_candidate, promote
from lab.model_gate import run_gate
from lab.make_reviewed_demo import generate
from edge.contract import parse_reading


class CandidateGateTests(unittest.TestCase):
    def test_baseline_and_identity_pass_with_no_promotion(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'copy.json'
            p.write_bytes((ROOT / 'models/forest.json').read_bytes())
            report = run_gate(p, p, seeds=(301,))
            self.assertTrue(report['approved'])
            self.assertTrue(report['same_version'])
            self.assertEqual(report['candidate']['ml']['fires'], 2)
            self.assertEqual(report['candidate']['ml']['negative_episodes'], 4)

    def test_damaged_model_does_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.json'
            data = json.loads((ROOT / 'models/forest.json').read_text())
            data['trees'][0][0] = [99, 5.0, 1, 2]
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                validate_candidate(p)

    def test_valid_but_bad_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad-quality.json'
            data = json.loads((ROOT / 'models/forest.json').read_text())
            data['trees'] = [[[0, 0, 0, 0, 1, 0]]]
            data.pop('version')
            digest = hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()[:12]
            data['version'] = 'rf-' + digest
            p.write_text(json.dumps(data))
            report = run_gate(p, ROOT / 'models/forest.json', seeds=(301,))
            self.assertFalse(report['approved'])
            self.assertIn('fewer_fire_episodes_detected', report['reasons'])

    def test_promote_saves_previous_model_for_manual_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            original=ROOT / 'models/forest.json'
            target=Path(d)/'forest.json'
            target.write_bytes(original.read_bytes())
            data=json.loads(original.read_text())
            # Construct a structurally valid different model to exercise
            # promotion backup; this is NOT a quality-gated deployment.
            data.pop('version')
            for node in data['trees'][0]:
                if len(node) == 6:
                    node[:]=[1.0,0.0,0.0,0.0,0.0,0.0]
                    break
            digest=hashlib.sha256(json.dumps(data,separators=(',',':')).encode()).hexdigest()[:12]
            data['version']='rf-'+digest
            cand=Path(d)/'candidate.json'
            cand.write_text(json.dumps(data))
            old_version=validate_candidate(target).version
            promote(cand,target)
            backup=Path(d)/f'forest.{old_version}.json'
            self.assertTrue(backup.is_file())
            self.assertEqual(backup.read_bytes(),original.read_bytes())
            self.assertEqual(target.read_bytes(),cand.read_bytes())

    def test_training_demo_data_label_kept_out_of_telemetry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'reviewed.jsonl'
            total = generate(path, seed=125, scenes=('fast_fire',))
            self.assertGreater(total, 500)
            with path.open(encoding='utf-8') as f:
                line = json.loads(next(iter(f)))
            self.assertEqual(line['group'], 'reviewed-train-SYNTHETIC-125-fast_fire')
            self.assertNotIn('class', line['message'])
            self.assertNotIn('ground_truth', line['message'])
            with path.open() as stream:
                checked = 0
                for line in stream:
                    row = json.loads(line)
                    parse_reading(row['message'])
                    checked += 1
            self.assertEqual(checked, total)
            with self.assertRaises(ValueError):
                generate(path, seed=201, scenes=('fast_fire',))


if __name__ == '__main__':
    unittest.main()
