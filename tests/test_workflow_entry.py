import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workflow_entry", ROOT / "workflow.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class WorkflowEntryTests(unittest.TestCase):
    def test_optional_stage_uses_installed_environment(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            installed = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            installed.parent.mkdir(parents=True)
            installed.write_bytes(b"stub")
            with patch.object(entry, "ROOT", root), patch.object(entry, "environment_name", return_value=".venv"):
                self.assertEqual(entry.interpreter("youtube"), str(installed))
                self.assertEqual(entry.interpreter("publication-review"), str(installed))
                self.assertEqual(entry.interpreter("slice"), sys.executable)
                with self.assertRaises(FileNotFoundError):
                    entry.interpreter("align")


if __name__ == "__main__":
    unittest.main()
