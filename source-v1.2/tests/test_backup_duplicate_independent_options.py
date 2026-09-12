import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fh6garage.app_options import AppOptions
from fh6garage.backup_export import load_index
from fh6garage.models import HeaderInfo, LiveryRecord
from fh6garage.v1_3_4_backup_import_refinement_patch import _safe_export_records


class IndependentDuplicateOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0

    def record(self, name, payload=b'same', kind='Livery'):
        self.counter += 1
        folder = self.root / f'{kind}_{self.counter}'
        folder.mkdir()
        (folder / 'C_livery').write_bytes(payload)
        return LiveryRecord(folder.name, folder, kind, HeaderInfo(name=name, creator='Test', car_id=1),
                            livery_path=folder / 'C_livery')

    def export(self, root, records, options):
        with patch('fh6garage.app_options.load_options', return_value=options):
            result = _safe_export_records(root, records)
        self.assertFalse(result.failed, result.failed)
        return result

    def matrix(self, same_batch):
        for allow_other in (False, True):
            for allow_same in (False, True):
                options = AppOptions(backup_allow_different_name=allow_other, backup_allow_duplicates=allow_same)
                for same_hash in (False, True):
                    for same_name in (False, True):
                        with self.subTest(batch=same_batch, other=allow_other, same=allow_same,
                                          same_hash=same_hash, same_name=same_name):
                            a = self.record('A')
                            b = self.record('A' if same_name else 'B', b'same' if same_hash else b'different')
                            root = self.root / f'backup-{self.counter}'
                            allowed = not same_hash or (allow_same if same_name else allow_other)
                            if same_batch:
                                result = self.export(root, [a, b], options)
                                self.assertEqual(len(result.exported), 1 + int(allowed))
                            else:
                                self.export(root, [a], options)
                                result = self.export(root, [b], options)
                                self.assertEqual(len(result.exported), int(allowed))
                            self.assertEqual(len(result.skipped), int(not allowed))
                            self.assertEqual(len(load_index(root)['entries']), 1 + int(allowed))
                            self.assertTrue(a.livery_path.exists())
                            self.assertTrue(b.livery_path.exists())

    def test_existing_backup_matrix(self):
        self.matrix(False)

    def test_same_batch_matrix(self):
        self.matrix(True)

    def test_exact_name_takes_priority_among_mixed_existing_names(self):
        for reverse in (False, True):
            for allow_other in (False, True):
                for allow_same in (False, True):
                    records = [self.record('A'), self.record('B')]
                    root = self.root / f'mixed-{self.counter}'
                    self.export(root, records[::-1] if reverse else records,
                                AppOptions(backup_allow_different_name=True))
                    candidate = self.record('B')
                    result = self.export(root, [candidate], AppOptions(
                        backup_allow_different_name=allow_other, backup_allow_duplicates=allow_same))
                    self.assertEqual(len(result.exported), int(allow_same))

    def test_other_name_only_does_not_repeat_new_name_within_batch(self):
        root = self.root / 'batch'
        result = self.export(root, [self.record('A'), self.record('B'), self.record('B')],
                             AppOptions(backup_allow_different_name=True))
        self.assertEqual([entry['name'] for entry in result.exported], ['A', 'B'])
        self.assertEqual(len(result.skipped), 1)

    def test_same_hash_different_kind_is_independent(self):
        result = self.export(self.root / 'kinds', [self.record('A'), self.record('A', kind='SoulBoundLivery')], AppOptions())
        self.assertEqual(len(result.exported), 2)

    def test_automatic_worker_uses_policy_without_repeating_existing_instances(self):
        from fh6garage.application_controls import _AutoBackupWorker
        for same_name in (False, True):
            for allow_other in (False, True):
                for allow_same in (False, True):
                    a, b = self.record('A'), self.record('A' if same_name else 'B')
                    root = self.root / f'auto-{self.counter}'
                    options = AppOptions(backup_allow_different_name=allow_other, backup_allow_duplicates=allow_same)
                    worker = _AutoBackupWorker(root, [a, b], None)
                    summaries, errors = [], []
                    worker.result_ready.connect(summaries.append)
                    worker.error.connect(errors.append)
                    with patch('fh6garage.app_options.load_options', return_value=options):
                        worker.run()
                        worker.run()
                    self.assertFalse(errors)
                    self.assertFalse(any(s.failed for s in summaries))
                    expected = 1 + int(allow_same if same_name else allow_other)
                    self.assertEqual([len(s.exported) for s in summaries], [expected, 0])
                    from shiboken6 import delete
                    delete(worker)
