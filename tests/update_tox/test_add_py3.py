#!/usr/bin/env python3
"""Tests for the add-py3 subcommand of update-tox.py."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

# update-tox.py has no extension issues but we load it the same way as the
# other test modules in this repo for consistency.
_REPO_ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location(
    "update_tox",
    _REPO_ROOT / "update-tox.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

add_py3 = _mod.add_py3
build_parser = _mod.build_parser
_version_to_section = _mod._version_to_section

FIXTURE_DIR = Path(__file__).parent

TOX_PY310_ONLY = FIXTURE_DIR / "tox_py310_only.ini"


class TestVersionToSection(unittest.TestCase):

    def test_standard(self):
        self.assertEqual(_version_to_section("3.10"), "py310")

    def test_py312(self):
        self.assertEqual(_version_to_section("3.12"), "py312")

    def test_py38(self):
        self.assertEqual(_version_to_section("3.8"), "py38")


class TestAddPy3(unittest.TestCase):

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _copy_fixture(self, fixture: Path) -> Path:
        dest = self.tmpdir / fixture.name
        shutil.copy(fixture, dest)
        return dest

    def _make_args(self, version, template, tox_ini):
        parser = build_parser()
        return parser.parse_args(
            ["add-py3", "--version", version, "--template", template,
             "--tox-ini", str(tox_ini)]
        )

    def test_adds_new_section(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        rc = add_py3(args)
        self.assertEqual(rc, 0)
        content = tox_ini.read_text()
        self.assertIn("[testenv:py312]", content)

    def test_new_section_has_correct_basepython(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        content = tox_ini.read_text()
        # Extract the py312 block
        import re
        match = re.search(
            r"\[testenv:py312\][^\[]*", content, re.DOTALL
        )
        self.assertIsNotNone(match)
        block = match.group(0)
        self.assertIn("basepython = python3.12", block)

    def test_new_section_has_correct_requirements_file(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        content = tox_ini.read_text()
        import re
        match = re.search(
            r"\[testenv:py312\][^\[]*", content, re.DOTALL
        )
        self.assertIsNotNone(match)
        block = match.group(0)
        self.assertIn("test-requirements-py312.txt", block)
        # Ensure the old requirements file is NOT in the new block
        self.assertNotIn("test-requirements-py310.txt", block)

    def test_new_section_inserted_after_template(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        content = tox_ini.read_text()
        pos_310 = content.index("[testenv:py310]")
        pos_312 = content.index("[testenv:py312]")
        self.assertGreater(pos_312, pos_310)

    def test_template_section_still_present(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        content = tox_ini.read_text()
        self.assertIn("[testenv:py310]", content)

    def test_returns_error_when_template_not_found(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.11", tox_ini)
        rc = add_py3(args)
        self.assertNotEqual(rc, 0)

    def test_returns_error_when_tox_ini_missing(self):
        tox_ini = self.tmpdir / "nonexistent.ini"
        args = self._make_args("3.12", "3.10", tox_ini)
        rc = add_py3(args)
        self.assertNotEqual(rc, 0)

    def test_skips_if_section_already_exists(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        original_content = tox_ini.read_text()
        # Run again — should not duplicate
        rc = add_py3(args)
        self.assertEqual(rc, 0)
        self.assertEqual(tox_ini.read_text(), original_content)

    def test_constraints_url_preserved(self):
        tox_ini = self._copy_fixture(TOX_PY310_ONLY)
        args = self._make_args("3.12", "3.10", tox_ini)
        add_py3(args)
        content = tox_ini.read_text()
        import re
        match = re.search(r"\[testenv:py312\][^\[]*", content, re.DOTALL)
        block = match.group(0)
        self.assertIn("TEST_CONSTRAINTS_FILE", block)
        self.assertIn("constraints-2024.1.txt", block)

    def test_parser_subcommand(self):
        """Ensure the CLI parser routes add-py3 correctly."""
        parser = build_parser()
        args = parser.parse_args(
            ["add-py3", "--version", "3.12", "--template", "3.10"]
        )
        self.assertEqual(args.version, "3.12")
        self.assertEqual(args.template, "3.10")
        self.assertEqual(args.func, add_py3)


if __name__ == "__main__":
    unittest.main()
