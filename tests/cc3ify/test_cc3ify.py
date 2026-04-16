#!/usr/bin/env python3
"""Tests for the cc3ify subcommand of _update-charmcraft.py."""

import argparse
import importlib.util
import sys
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

_is_cross_build = _mod._is_cross_build
_parse_bases = _mod._parse_bases
_unique_bases = _mod._unique_bases
cc3ify = _mod.cc3ify

yaml = YAML(typ="rt")
yaml.preserve_quotes = True


def _load(text: str):
    return yaml.load(StringIO(textwrap.dedent(text)))


def _dump(data) -> str:
    out = StringIO()
    yaml.dump(data, out)
    return out.getvalue()


def _make_args(base=None, platforms=None):
    ns = argparse.Namespace()
    ns.base = base
    ns.platforms = platforms
    return ns


FIXTURE_DIR = Path(__file__).parent


class TestParseBases(unittest.TestCase):
    """Unit tests for _parse_bases / helpers."""

    def test_long_form_build_on_equals_run_on(self):
        """Short-circuit: identical build-on and run-on."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
        """)
        parsed = _parse_bases(doc['bases'])
        self.assertEqual(parsed[0]['build_on'], [('ubuntu@22.04', 'amd64')])
        self.assertEqual(parsed[0]['run_on'], [('ubuntu@22.04', 'amd64')])

    def test_cross_build_detected(self):
        """build-on amd64 / run-on [amd64, arm64] must trigger cross_build."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64, arm64]
        """)
        parsed = _parse_bases(doc['bases'])
        self.assertTrue(_is_cross_build(parsed))

    def test_multiple_unique_bases(self):
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
              - build-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
        """)
        parsed = _parse_bases(doc['bases'])
        self.assertEqual(_unique_bases(parsed), ['ubuntu@22.04', 'ubuntu@24.04'])
        self.assertFalse(_is_cross_build(parsed))


class TestCc3ifyCrossBuild(unittest.TestCase):
    """cc3ify cross-build mode: build-on != run-on architectures."""

    def _run(self, input_yaml: str) -> dict:
        doc = _load(input_yaml)
        return cc3ify(_make_args(), doc)

    def test_build_for_is_single_element(self):
        """Each platform entry must have exactly one build-for item."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64, s390x, ppc64el, arm64]
        """)
        result = cc3ify(_make_args(), doc)
        for name, entry in result['platforms'].items():
            self.assertEqual(
                len(entry['build-for']), 1,
                f"platform '{name}' has {len(entry['build-for'])} build-for items; expected 1",
            )

    def test_cross_build_multi_base_platform_names(self):
        """Multi-base cross-build uses shorthand platform key format."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64, arm64]
              - build-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64, arm64]
        """)
        result = cc3ify(_make_args(), doc)
        expected_names = {
            'ubuntu@22.04:amd64', 'ubuntu@22.04:arm64',
            'ubuntu@24.04:amd64', 'ubuntu@24.04:arm64',
        }
        self.assertEqual(set(result['platforms'].keys()), expected_names)

    def test_cross_build_build_on_shared(self):
        """All per-arch platforms for the same base share the same build-on value."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64, s390x]
        """)
        result = cc3ify(_make_args(), doc)
        self.assertEqual(
            result['platforms']['ubuntu-22.04-amd64']['build-on'],
            ['ubuntu@22.04:amd64'],
        )
        self.assertEqual(
            result['platforms']['ubuntu-22.04-s390x']['build-on'],
            ['ubuntu@22.04:amd64'],
        )

    def test_cross_build_no_top_level_base_keys(self):
        """cross-build (multi-base) must NOT set top-level base/build-base."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64, arm64]
              - build-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64, arm64]
        """)
        result = cc3ify(_make_args(), doc)
        self.assertNotIn('base', result)
        self.assertNotIn('build-base', result)

    def test_cross_build_fixture_matches_expected(self):
        """End-to-end: fixture file produces the expected YAML output."""
        input_path = FIXTURE_DIR / 'cross_build.yaml'
        expected_path = FIXTURE_DIR / 'cross_build_expected.yaml'

        with open(input_path) as f:
            doc = yaml.load(f)
        with open(expected_path) as f:
            expected = yaml.load(f)

        result = cc3ify(_make_args(), doc)

        self.assertEqual(
            _dump(result['platforms']),
            _dump(expected['platforms']),
        )


class TestCc3ifyMultiBaseShorthand(unittest.TestCase):
    """cc3ify multi-base shorthand: build-on == run-on, multiple bases."""

    def test_shorthand_platform_keys(self):
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
              - build-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
        """)
        result = cc3ify(_make_args(), doc)
        self.assertIn('ubuntu@22.04:amd64', result['platforms'])
        self.assertIn('ubuntu@24.04:amd64', result['platforms'])
        self.assertNotIn('base', result)
        self.assertNotIn('build-base', result)

    def test_shorthand_null_values(self):
        """Shorthand platform entries must have null (None) values."""
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
              - build-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "24.04"
                    architectures: [amd64]
        """)
        result = cc3ify(_make_args(), doc)
        for v in result['platforms'].values():
            self.assertIsNone(v)


class TestCc3ifyMultiBaseCrossBuild(unittest.TestCase):
    """cc3ify multi-base cross-build shorthand.

    Scenario: multiple bases, each with build-on amd64 but run-on containing
    additional architectures (s390x, ppc64el, arm64).  Expected output uses the
    shorthand ``ubuntu@<channel>:<arch>:`` format derived from run-on, sorted.
    """

    _INPUT = """
        bases:
          - build-on:
              - name: ubuntu
                channel: "22.04"
                architectures:
                  - amd64
            run-on:
              - name: ubuntu
                channel: "22.04"
                architectures: [amd64, s390x, ppc64el, arm64]
          - build-on:
              - name: ubuntu
                channel: '24.04'
                architectures:
                  - amd64
            run-on:
              - name: ubuntu
                channel: '24.04'
                architectures:
                  - amd64
                  - s390x
                  - ppc64el
                  - arm64
    """

    def _run(self):
        doc = _load(self._INPUT)
        return cc3ify(_make_args(), doc)

    def test_shorthand_platform_keys(self):
        """All run-on (base, arch) combos appear as shorthand platform keys."""
        result = self._run()
        expected_keys = {
            'ubuntu@22.04:amd64', 'ubuntu@22.04:s390x',
            'ubuntu@22.04:ppc64el', 'ubuntu@22.04:arm64',
            'ubuntu@24.04:amd64', 'ubuntu@24.04:s390x',
            'ubuntu@24.04:ppc64el', 'ubuntu@24.04:arm64',
        }
        self.assertEqual(set(result['platforms'].keys()), expected_keys)

    def test_shorthand_null_values(self):
        """Shorthand platform entries must have null (None) values."""
        result = self._run()
        for name, value in result['platforms'].items():
            self.assertIsNone(value, f"platform '{name}' should be null")

    def test_no_top_level_base_keys(self):
        """Must NOT set top-level base/build-base keys."""
        result = self._run()
        self.assertNotIn('base', result)
        self.assertNotIn('build-base', result)

    def test_no_explicit_build_on_build_for(self):
        """Must NOT generate explicit build-on/build-for per platform entry."""
        result = self._run()
        for name, value in result['platforms'].items():
            self.assertIsNone(value, f"platform '{name}' must be null, not a mapping")

    def test_platforms_sorted(self):
        """Platform keys must be in sorted order."""
        result = self._run()
        keys = list(result['platforms'].keys())
        self.assertEqual(keys, sorted(keys))

    def test_fixture_matches_expected(self):
        """End-to-end: fixture file produces the expected YAML output."""
        input_path = FIXTURE_DIR / 'multi_base_cross_build.yaml'
        expected_path = FIXTURE_DIR / 'multi_base_cross_build_expected.yaml'

        with open(input_path) as f:
            doc = yaml.load(f)
        with open(expected_path) as f:
            expected = yaml.load(f)

        result = cc3ify(_make_args(), doc)

        self.assertEqual(
            _dump(result['platforms']),
            _dump(expected['platforms']),
        )


class TestCc3ifySingleBase(unittest.TestCase):
    """cc3ify single-base mode: one base, build-on == run-on."""

    def test_single_base_keys_present(self):
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
        """)
        result = cc3ify(_make_args(), doc)
        self.assertEqual(result['base'], 'ubuntu@22.04')
        self.assertEqual(result['build-base'], 'ubuntu@22.04')
        self.assertIn('amd64', result['platforms'])

    def test_single_base_override_via_args(self):
        doc = _load("""
            bases:
              - build-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
                run-on:
                  - name: ubuntu
                    channel: "22.04"
                    architectures: [amd64]
        """)
        result = cc3ify(_make_args(base='ubuntu@24.04', platforms='amd64,arm64'), doc)
        self.assertEqual(result['base'], 'ubuntu@24.04')
        self.assertIn('arm64', result['platforms'])

    def test_no_bases_key_raises(self):
        doc = _load("""
            type: charm
            platforms:
              amd64:
        """)
        with self.assertRaises(KeyError):
            cc3ify(_make_args(), doc)


if __name__ == '__main__':
    unittest.main()
