"""Mismatched display evidence must never reach approval writes or metadata calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from review_advance import continuation
from review_protocol import validate_round
from review_receipts import Receipts
from translation_review import sha, version_digest
import test_review_protocol


class DisplayGuardTest(unittest.TestCase):
    def test_mismatch_stops_before_approval_and_provider(self):
        for field in ('original', 'translation', 'backtranslation', 'independent_translation',
                      'differences', 'backtranslation_provider', 'independent_provider'):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = test_review_protocol.ReviewProtocolTest(); fixture.setUp()
                current, receipt = fixture.round, fixture.receipt
                current['language'] = receipt['language'] = 'en'
                version = {'version': 1, 'source': {'original_exact': 'Sample original'},
                           'target_language': 'en', 'translation': 'Sample translation',
                           'translation_sha256': sha('Sample translation'),
                           'blind_backtranslation': 'Sample backtranslation',
                           'independent_translation': 'Independent translation',
                           'independent_review': 'Reviewed differences'}
                item = current['items'][0]
                item['content'] = {'translation_version': version, 'original': 'Sample original',
                                   'translation': version['translation'],
                                   'backtranslation': version['blind_backtranslation'],
                                   'independent_translation': version['independent_translation'],
                                   'differences': version['independent_review'],
                                   'backtranslation_provider': 'test fixture',
                                   'independent_provider': 'test fixture'}
                item['content'][field] = '' if field.endswith('provider') else 'Mismatched display'
                receipt['content_sha256'] = validate_round(current)
                receipt['items'][0]['content_sha256'] = version_digest(item)
                root = Path(tmp); path = root / 'round.json'
                path.write_text(json.dumps(current), encoding='utf-8')
                provider = Mock(side_effect=AssertionError('must not call provider'))
                store = Receipts(root / 'store')
                try:
                    accepted = store.receive(current, receipt, entry='local_html', page='<html>fixture</html>')
                    handler = continuation(path, root / 'next', model='test', provider=provider, allow_model=True)
                    with self.assertRaises(RuntimeError):
                        store.process(accepted['id'], handler)
                    self.assertEqual(store.status(accepted['id'])['state'], 'failed')
                    provider.assert_not_called()
                    self.assertFalse(list((root / 'next').rglob('translation-approval.json')))
                    self.assertFalse(list((root / 'next').rglob('metadata-candidate.json')))
                    self.assertTrue(list((root / 'store/review-signals').glob('*.json')))
                finally:
                    store.close()


if __name__ == '__main__':
    unittest.main()
