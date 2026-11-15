import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


README_PATH = Path(__file__).resolve().parents[1] / "README.md"


class HTMLTargets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        self.targets.extend(
            value for name, value in attrs
            if name in {"href", "src"} and value is not None
        )


def extract_targets(text):
    # Inline links and images in this README do not use nested parentheses.
    targets = re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", text)
    parser = HTMLTargets()
    parser.feed(text)
    return targets + parser.targets


def local_links(targets, readme):
    links = []
    for target in targets:
        url = urlsplit(target)
        if url.scheme or url.netloc or target.startswith("//") or not url.path:
            continue
        links.append((target, (readme.parent / unquote(url.path)).resolve()))
    return links


class ReadmeLinksTest(unittest.TestCase):
    def assert_links_exist(self, text, readme):
        links = local_links(extract_targets(text), readme)
        self.assertTrue(links, "No local README links extracted")
        missing = [(target, path) for target, path in links if not path.exists()]
        self.assertFalse(
            missing,
            "Missing local README links:\n"
            + "\n".join(f"{target} -> {path}" for target, path in missing),
        )

    def test_root_readme_links_exist(self):
        self.assert_links_exist(README_PATH.read_text(encoding="utf-8"), README_PATH)

    def test_file_directory_images_and_html_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "file.txt").touch()
            (root / "folder").mkdir()
            text = (
                "[file](file.txt) [directory](folder) ![image](file.txt) "
                '<a href="file.txt">file</a> '
                "<img src='file.txt'> <a href=folder>folder</a>"
            )
            self.assertEqual(
                extract_targets(text),
                ["file.txt", "folder", "file.txt", "file.txt", "file.txt", "folder"],
            )
            self.assert_links_exist(text, root / "README.md")

    def test_nonlocal_targets_are_skipped(self):
        targets = [
            "https://example.com/file", "http://example.com", "mailto:a@example.com",
            "data:image/png;base64,abc", "//example.com/file", "#section", "",
        ]
        self.assertEqual(local_links(targets, README_PATH), [])

    def test_encoded_path_query_and_fragment(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            file = readme.parent / "a b.txt"
            file.touch()
            target = "a%20b.txt?download=1#section"
            self.assertEqual(local_links([target], readme), [(target, file.resolve())])
            self.assert_links_exist(f"[file]({target})", readme)

    def test_missing_diagnostic_preserves_original_and_resolved_path(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            target = "missing%20file.txt?download=1#section"
            with self.assertRaises(AssertionError) as caught:
                self.assert_links_exist(f"[missing]({target})", readme)
            self.assertIn(target, str(caught.exception))
            self.assertIn(str((readme.parent / "missing file.txt").resolve()), str(caught.exception))

    def test_empty_local_extraction_fails(self):
        for text in ("No links", "[external](https://example.com) [anchor](#section)"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(AssertionError, "No local README links extracted"):
                    self.assert_links_exist(text, README_PATH)

    def test_previous_example_typo_is_rejected(self):
        target = "examples/synthesize_query.py"
        self.assert_links_exist(f"[example]({target})", README_PATH)
        old_target = target.replace("synthesize", "sy" + "thesize")
        with self.assertRaises(AssertionError) as caught:
            self.assert_links_exist(f"[example]({old_target})", README_PATH)
        self.assertIn(old_target, str(caught.exception))
        self.assertIn(str((README_PATH.parent / old_target).resolve()), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
