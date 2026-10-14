import unittest
from pathlib import Path
from fh6garage.models import TuningRecord,HeaderInfo
from fh6garage.thumbnail_marks_ui import update_card

class TuningIsolationTests(unittest.TestCase):
    def test_tuning_skips_all_livery_overlay_work(self):
        class Untouched:
            def __getattr__(self,name):
                raise AssertionError('tuning touched livery UI: '+name)
        for thumbnail in (None,Path('tuning.webp')):
            record=TuningRecord('Tuning_1',Path('Tuning_1'),HeaderInfo(),thumbnail_path=thumbnail)
            update_card(Untouched(),Untouched(),record)
