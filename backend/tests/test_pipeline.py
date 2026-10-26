import unittest
from types import SimpleNamespace

from app.models import Document
from app.parsing.models import Metadata
from app.services.pipeline import _apply_metadata


class MetadataClippingTest(unittest.TestCase):
    def test_values_longer_than_the_column_are_clipped(self):
        """Postgres refuses a value longer than its column; a symbol or an issuer read from a badly formed header can be."""
        document = Document(extra={})
        meta = Metadata(title="t" * 900, doc_type="d" * 200, number="1", symbol="s" * 300, issuing_agency="i" * 600, signer="g" * 500)
        _apply_metadata(document, SimpleNamespace(metadata=meta, warnings=[]))
        self.assertEqual(len(document.title), 500)
        self.assertEqual(len(document.document_type), 80)
        self.assertEqual(len(document.symbol), 80)
        self.assertEqual(len(document.issuer), 255)
        self.assertEqual(len(document.signer), 200)


if __name__ == "__main__":
    unittest.main()
