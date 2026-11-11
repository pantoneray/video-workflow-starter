import json
import importlib.util
import tempfile
import unittest
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from project_setup import initialize, check
from source_search import search


class ProjectEntryTests(unittest.TestCase):
    def test_markdown_headings_do_not_swallow_adjacent_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = "慈悲从倾听开始。\n先听完，再回应。"
            (root / "book.md").write_text(
                "# 第一章\n" + original + "\n## 第二章\n慈悲也需要行动。\n", encoding="utf-8")
            themes = {"themes": [{"id": "daily", "enabled": True,
                "source_scope": ["life_corpus"], "keywords": ["慈悲"]}]}
            result = search({"paths": {"life_corpus": str(root)}}, themes, "daily")
            self.assertEqual([x["original_exact"] for x in result["results"]],
                             [original, "慈悲也需要行动。"])
            self.assertEqual([x["locator"] for x in result["results"]], ["line 2", "line 5"])
            self.assertEqual([x["section"] for x in result["results"]], ["第一章", "第二章"])

    def test_relative_config_paths_work_from_another_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"; project.mkdir()
            corpus = project / "corpus"; corpus.mkdir()
            (corpus / "book.md").write_text("# 第一章\n\n慈悲可以从日常倾听开始。\n", encoding="utf-8")
            config = project / "video-config.json"
            config.write_text(json.dumps({"paths": {"life_corpus": "corpus", "output": "runs"}}))
            (project / "runs").mkdir()
            themes = project / "topics.json"
            themes.write_text(json.dumps({"themes": [{"id": "daily", "enabled": True,
                "depth": "生活应用", "source_scope": ["life_corpus"], "keywords": ["慈悲"]}]}))
            other = root / "other"; other.mkdir()
            scripts = Path(__file__).resolve().parents[1] / "scripts"
            checked = subprocess.run([sys.executable, str(scripts / "project_setup.py"), "check",
                                      "--config", str(config)], cwd=other, check=True,
                                     text=True, capture_output=True)
            report = json.loads(checked.stdout)
            self.assertEqual(report["life_corpus"]["status"], "ready")
            self.assertEqual(report["output"]["status"], "ready")
            init = initialize(config, project)
            self.assertIn(str(corpus), (project / "VIDEO-WORKFLOW-MEMORY.md").read_text())
            self.assertEqual(init["paths"]["life_corpus"]["status"], "ready")
            output = other / "candidates.json"
            subprocess.run([sys.executable, str(scripts / "source_search.py"), "--config", str(config),
                            "--themes", str(themes), "--theme-id", "daily", "--out", str(output)],
                           cwd=other, check=True, text=True, capture_output=True)
            candidate = json.loads(output.read_text())["results"][0]
            self.assertEqual(candidate["file"], str((corpus / "book.md").resolve()))

    def test_initialize_and_missing_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
            config = root / "private.json"
            config.write_text(json.dumps({"paths": {"life_corpus": str(root / "offline-disk"), "output": str(project)}}))
            result = initialize(config, project)
            self.assertEqual(result["paths"]["life_corpus"]["status"], "unavailable")
            self.assertIn("# Existing", (project / "AGENTS.md").read_text())
            self.assertIn("VIDEO-WORKFLOW-MEMORY.md", (project / "AGENTS.md").read_text())
            self.assertNotIn("secret", (project / "VIDEO-WORKFLOW-MEMORY.md").read_text())
            with (project / "VIDEO-WORKFLOW-MEMORY.md").open("a") as item:
                item.write("\n保留我的备注\n")
            initialize(config, project, sync=True)
            self.assertIn("保留我的备注", (project / "VIDEO-WORKFLOW-MEMORY.md").read_text())
            with self.assertRaises(FileExistsError):
                initialize(config, project)

    def test_search_exact_provenance_and_custom_theme(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            corpus = root / "corpus"
            corpus.mkdir()
            (corpus / "book.md").write_text("# 第一章\n\n这里谈日常相处。\n\n慈悲可以从日常相处开始。先听对方说完，再回应。\n\n这需要先了解背景。\n", encoding="utf-8")
            (corpus / "other.docx").write_bytes(b"not supported")
            (corpus / "bad.txt").write_bytes(b"\xff\xfe\xff")
            themes = {"themes": [{"id": "custom", "enabled": True, "depth": "生活应用", "source_scope": ["life_corpus"], "keywords": ["慈悲"], "exclude_keywords": []}]}
            result = search({"paths": {"life_corpus": str(corpus)}}, themes, "custom")
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["results"][0]["original_exact"], "慈悲可以从日常相处开始。先听对方说完，再回应。")
            self.assertEqual(result["results"][0]["locator"], "line 5")
            self.assertIn("这里谈日常相处", result["results"][0]["context_before"])
            self.assertIn("这需要先了解背景", result["results"][0]["context_after"])
            self.assertEqual(result["results"][0]["approval"], "pending_human_review")
            self.assertEqual(result["files_skipped"], 2)
            self.assertEqual({item["warning"] for item in result["warnings"]},
                             {"unsupported_format", "text_encoding_unreadable; convert to UTF-8 before searching"})
            themes["themes"][0]["enabled"] = False
            with self.assertRaises(ValueError):
                search({"paths": {"life_corpus": str(corpus)}}, themes, "custom")
            themes["themes"][0]["enabled"] = True
            with self.assertRaises(ValueError):
                search({"paths": {}}, themes, "custom")

    def test_duplicate_provenance_and_chapter_boundary_are_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus = Path(temp)
            (corpus / "a.md").write_text("# 第一章\n\n慈悲要从倾听开始，并且不能省略对方的具体处境。\n\n# 第二章\n\n别的内容。\n", encoding="utf-8")
            (corpus / "b.md").write_text("# 再版\n\n慈悲要从倾听开始，并且不能省略对方的具体处境。\n", encoding="utf-8")
            themes = {"themes": [{"id": "custom", "enabled": True, "depth": "生活应用",
                                   "source_scope": ["life_corpus"], "keywords": ["慈悲"]}]}
            result = search({"paths": {"life_corpus": [str(corpus / "a.md"), str(corpus / "b.md")]}}, themes, "custom")
            self.assertEqual(len(result["results"]), 1)
            self.assertEqual(result["duplicates_skipped"], 1)
            self.assertEqual(result["warnings"][0]["warning"], "duplicate_text")
            self.assertIn("a.md", result["warnings"][0]["same_text_as"]["file"])
            self.assertIn("跨章节", " ".join(result["results"][0]["review_flags"]))
            self.assertEqual(result["results"][0]["context_after_locator"], "line 7")

    def test_candidate_risks_prompt_context_review_without_auto_approval(self):
        with tempfile.TemporaryDirectory() as temp:
            book = Path(temp) / "teaching.md"
            book.write_text("# 第一章\n\n因此这里的慈悲要结合前面所说的条件来看：\n\n# 第二章\n\n别的内容。\n", encoding="utf-8")
            themes = {"themes": [{"id": "deep-custom", "enabled": True, "depth": "深入法义",
                                   "source_scope": ["deep_corpus"], "keywords": ["慈悲"]}]}
            result = search({"paths": {"deep_corpus": str(book)}}, themes, "deep-custom")
            candidate = result["results"][0]
            codes = {item["code"] for item in candidate["risk_checks"]}
            self.assertTrue({"leading_reference", "missing_previous_context", "unfinished_ending",
                             "section_boundary", "specialist_review", "keyword_only_theme_match"} <= codes)
            self.assertEqual(candidate["approval"], "pending_human_review")
            self.assertEqual(candidate["original_exact"], "因此这里的慈悲要结合前面所说的条件来看：")

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "PDF 可选依赖未安装")
    def test_scanned_pdf_warns_ocr_needed(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / "scanned.pdf"
            writer = PdfWriter(); writer.add_blank_page(width=200, height=200)
            with pdf.open("wb") as out: writer.write(out)
            themes = {"themes": [{"id": "pdf", "enabled": True, "depth": "生活应用",
                                   "source_scope": ["life_corpus"], "keywords": ["慈悲"]}]}
            result = search({"paths": {"life_corpus": str(pdf)}}, themes, "pdf")
            self.assertFalse(result["results"])
            self.assertIn("OCR", result["warnings"][0]["warning"])


if __name__ == "__main__":
    unittest.main()
