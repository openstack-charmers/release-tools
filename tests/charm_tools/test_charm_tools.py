#!/usr/bin/env python3
"""Tests for the charm-tools subcommand of _update-charmcraft.py."""

import argparse
import importlib.util
import textwrap
import unittest
from io import StringIO
from pathlib import Path

from ruamel.yaml import YAML

# _update-charmcraft.py has a hyphen in its name so it can't be imported with a
# normal import statement.  Load it explicitly via importlib.
_REPO_ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location(
    "_update_charmcraft",
    _REPO_ROOT / "_update-charmcraft.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

charm_tools = _mod.charm_tools

yaml = YAML(typ="rt")
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def _load(text: str):
    return yaml.load(StringIO(textwrap.dedent(text)))


def _dump(data) -> str:
    out = StringIO()
    yaml.dump(data, out)
    return out.getvalue()


def _make_args(channel: str = "3.x/stable",
               add_build_arguments=None) -> argparse.Namespace:
    ns = argparse.Namespace()
    ns.channel = channel  # may be None to test the optional-channel path
    ns.add_build_arguments = add_build_arguments
    return ns


FIXTURE_DIR = Path(__file__).parent


class TestCharmTools(unittest.TestCase):
    """Tests for the charm_tools function."""

    def test_replaces_bare_charm_snap(self):
        """'charm' in build-snaps is replaced with 'charm/<channel>'."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - charm
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        snaps = result['parts']['charm']['build-snaps']
        self.assertEqual(list(snaps), ['charm/3.x/stable'])

    def test_replaces_existing_charm_channel(self):
        """An existing 'charm/<old>' entry is updated to the new channel."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - charm/2.x/stable
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        snaps = result['parts']['charm']['build-snaps']
        self.assertEqual(list(snaps), ['charm/3.x/stable'])

    def test_appends_when_charm_not_present(self):
        """When no charm snap exists in build-snaps, one is appended."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - some-other-snap
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertIn('charm/3.x/stable', snaps)
        self.assertIn('some-other-snap', snaps)

    def test_creates_build_snaps_when_missing(self):
        """build-snaps is created when the key doesn't exist."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertEqual(snaps, ['charm/3.x/stable'])

    def test_skips_when_plugin_not_reactive(self):
        """charmcraft is returned unchanged when parts.charm.plugin is not 'reactive'."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: python
                build-snaps:
                  - charm
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        # build-snaps must be untouched
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertEqual(snaps, ['charm'])

    def test_skips_when_parts_missing(self):
        """charmcraft is returned unchanged when 'parts' key is absent."""
        doc = _load("""
            name: my-charm
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        self.assertNotIn('parts', result)

    def test_skips_when_charm_part_missing(self):
        """charmcraft is returned unchanged when 'parts.charm' key is absent."""
        doc = _load("""
            parts:
              other:
                plugin: reactive
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        self.assertNotIn('charm', result['parts'])

    def test_other_snaps_preserved(self):
        """Other entries in build-snaps are not removed."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - snap-a
                  - charm
                  - snap-b
        """)
        result = charm_tools(_make_args("3.x/stable"), doc)
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertEqual(snaps, ['snap-a', 'charm/3.x/stable', 'snap-b'])

    def test_fixture_roundtrip(self):
        """The fixture file produces the expected output YAML."""
        input_path = FIXTURE_DIR / "reactive_charm.yaml"
        expected_path = FIXTURE_DIR / "reactive_charm_expected.yaml"

        with open(input_path) as f:
            doc = yaml.load(f)

        result = charm_tools(_make_args("3.x/stable"), doc)

        out = StringIO()
        yaml.dump(result, out)
        actual = out.getvalue()

        with open(expected_path) as f:
            expected = f.read()

        self.assertEqual(actual, expected)

    def test_different_channel(self):
        """The channel argument is used verbatim."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - charm
        """)
        result = charm_tools(_make_args("latest/edge"), doc)
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertEqual(snaps, ['charm/latest/edge'])

    def test_no_channel_leaves_build_snaps_unchanged(self):
        """When --channel is not provided, build-snaps is left untouched."""
        doc = _load("""
            parts:
              charm:
                source: src/
                plugin: reactive
                build-snaps:
                  - charm/2.x/stable
        """)
        result = charm_tools(_make_args(channel=None), doc)
        snaps = list(result['parts']['charm']['build-snaps'])
        self.assertEqual(snaps, ['charm/2.x/stable'])


class TestCharmToolsAddBuildArguments(unittest.TestCase):
    """Tests for --add-build-arguments in the charm_tools function."""

    def test_appends_new_arguments(self):
        """New arguments are appended to an existing list."""
        doc = _load("""
            parts:
              charm:
                plugin: reactive
                reactive-charm-build-arguments:
                  - --binary-wheels-from-source
        """)
        result = charm_tools(
            _make_args(add_build_arguments=['-v', '--use-lock-file-branches']), doc)
        args_list = list(
            result['parts']['charm']['reactive-charm-build-arguments'])
        self.assertEqual(
            args_list,
            ['--binary-wheels-from-source', '-v', '--use-lock-file-branches'])

    def test_creates_section_when_missing(self):
        """reactive-charm-build-arguments is created when absent."""
        doc = _load("""
            parts:
              charm:
                plugin: reactive
                build-snaps:
                  - charm
        """)
        result = charm_tools(
            _make_args(add_build_arguments=['--use-lock-file-branches']), doc)
        args_list = list(
            result['parts']['charm']['reactive-charm-build-arguments'])
        self.assertEqual(args_list, ['--use-lock-file-branches'])

    def test_duplicate_arguments_not_added(self):
        """Arguments already present are not duplicated."""
        doc = _load("""
            parts:
              charm:
                plugin: reactive
                reactive-charm-build-arguments:
                  - --binary-wheels-from-source
        """)
        result = charm_tools(
            _make_args(add_build_arguments=['--binary-wheels-from-source', '-v']),
            doc)
        args_list = list(
            result['parts']['charm']['reactive-charm-build-arguments'])
        self.assertEqual(args_list, ['--binary-wheels-from-source', '-v'])

    def test_no_add_build_arguments_leaves_section_unchanged(self):
        """When --add-build-arguments is not supplied, the section is untouched."""
        doc = _load("""
            parts:
              charm:
                plugin: reactive
                reactive-charm-build-arguments:
                  - --binary-wheels-from-source
        """)
        result = charm_tools(_make_args(), doc)
        args_list = list(
            result['parts']['charm']['reactive-charm-build-arguments'])
        self.assertEqual(args_list, ['--binary-wheels-from-source'])

    def test_skipped_when_plugin_not_reactive(self):
        """Build arguments are not modified when plugin is not reactive."""
        doc = _load("""
            parts:
              charm:
                plugin: python
                reactive-charm-build-arguments:
                  - --binary-wheels-from-source
        """)
        result = charm_tools(
            _make_args(add_build_arguments=['--use-lock-file-branches']), doc)
        args_list = list(
            result['parts']['charm']['reactive-charm-build-arguments'])
        # unchanged because function returns early
        self.assertEqual(args_list, ['--binary-wheels-from-source'])


if __name__ == '__main__':
    unittest.main()
