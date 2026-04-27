#!/usr/bin/env python3

# Update the charmcraft.yaml

import argparse
import logging
import os
from pathlib import Path
import re
import sys
import textwrap
from typing import List, Optional, Dict, Any

from ruamel.yaml import YAML


logger = logging.getLogger(__name__)


def delete_bases(args: argparse.Namespace, charmcraft: Any) -> Any:
    """Delete any bases run-on/build-on that has args.bases.

    Note that charmcraft is the file loaded by ruamel.yaml
    """
    try:
        bases = charmcraft['bases']
    except KeyError:
        logger.error("'bases' not found in charmcraft document?")
        raise
    # iterate through the bases looking for the the  any bases in args.bases in
    # the 'channel' key.
    modified_bases = []
    for base in bases:
        try:
            channel = base['channel']
            if channel not in args.bases:
                modified_bases.append(base)
        except KeyError:
            # if channel doesn't exist here, then it's a 'build-on', 'run-on'
            try:
                build_ons = base['build-on']
                run_ons = base['run-on']
            except KeyError:
                logger.error("Couldn't decode the base: neither short form "
                             " nor long form?")
                logger.error(base)
                raise
            # now iterate through the build-on, and remove skip any channels in
            # args.bases
            try:
                modified_build_ons = [b for b in build_ons
                                      if b['channel'] not in args.bases]
            except KeyError:
                logger.error("Malformed bases?")
                logger.error(build_ons)
                raise
            # if nothing left in build_ons, then drop whole section.
            if not modified_build_ons:
                continue
            # now do the same for the run_ons
            try:
                modified_run_ons = [b for b in run_ons
                                    if b['channel'] not in args.bases]
            except KeyError:
                logger.error("Malformed bases?")
                logger.error(build_ons)
                raise
            if not modified_run_ons:
                continue
            modified_bases.append({'build-on': modified_build_ons,
                                   'run-on': modified_run_ons})
    charmcraft['bases'] = modified_bases
    return charmcraft


def _base_key_from_entry(entry: Any) -> str:
    """Return '<name>@<channel>' from a single build-on/run-on entry."""
    name = entry.get('name', 'ubuntu')
    channel = entry.get('channel', '')
    return f"{name}@{channel}"


# A parsed representation of one v2 'bases' entry.
# build_on_archs:  list of (base_key, arch) from build-on
# run_on_archs:    list of (base_key, arch) from run-on
_BasesEntry = Dict[str, Any]   # keys: 'build_on', 'run_on'  (list of (base, arch) tuples)


def _parse_bases(bases: Any) -> List[_BasesEntry]:
    """Parse the v2 'bases' list into a structured form.

    Each element in the returned list corresponds to one entry in 'bases' and
    contains:
        'build_on': list of (base_key, arch) tuples
        'run_on':   list of (base_key, arch) tuples

    Handles both short form (channel directly on the entry) and long form
    (build-on / run-on sub-keys).
    """
    parsed: List[_BasesEntry] = []

    for base in bases:
        if 'build-on' in base:
            build_on_entries = base['build-on']
            run_on_entries = base.get('run-on', base['build-on'])
        elif 'channel' in base:
            # short form: the entry itself acts as both build-on and run-on
            build_on_entries = [base]
            run_on_entries = [base]
        else:
            logger.warning("Unrecognised base entry, skipping: %s", base)
            continue

        build_on = [
            (_base_key_from_entry(e), arch)
            for e in build_on_entries
            for arch in e.get('architectures', [])
        ]
        run_on = [
            (_base_key_from_entry(e), arch)
            for e in run_on_entries
            for arch in e.get('architectures', [])
        ]
        parsed.append({'build_on': build_on, 'run_on': run_on})

    return parsed


def _is_cross_build(parsed: List[_BasesEntry]) -> bool:
    """Return True if any entry has different build-on and run-on architectures."""
    for entry in parsed:
        if set(entry['build_on']) != set(entry['run_on']):
            return True
    return False


def _unique_bases(parsed: List[_BasesEntry]) -> List[str]:
    """Return the unique base keys (e.g. 'ubuntu@22.04') across all entries."""
    seen: List[str] = []
    for entry in parsed:
        for base_key, _ in entry['build_on']:
            if base_key not in seen:
                seen.append(base_key)
    return seen


def cc3ify(args: argparse.Namespace, charmcraft: Any) -> Any:
    try:
        bases = charmcraft['bases']
    except KeyError:
        logger.error("'bases' not found in charmcraft document, already charmcraft3.yaml?")
        raise

    parsed = _parse_bases(bases)
    unique_bases = _unique_bases(parsed)
    multi_base = len(unique_bases) > 1
    cross_build = _is_cross_build(parsed)

    del charmcraft['bases']

    if multi_base and cross_build:
        # Multi-base cross-build shorthand: build-on arch differs from run-on archs
        # across multiple bases.  Use the run-on (base, arch) pairs as shorthand
        # platform keys – charmcraft3 resolves the actual builder automatically.
        # Platform keys use the shorthand  <name>@<channel>:<arch>
        charmcraft['platforms'] = {}
        seen_platforms: List[str] = []
        for entry in parsed:
            for base_key, arch in entry['run_on']:
                platform_name = f"{base_key}:{arch}"
                if platform_name not in seen_platforms:
                    seen_platforms.append(platform_name)
        for platform_name in sorted(seen_platforms):
            charmcraft['platforms'][platform_name] = None
        logger.info(
            "Multi-base cross-build detected (%s); generated shorthand platforms "
            "from run-on architectures.",
            ", ".join(unique_bases),
        )
    elif cross_build:
        # Standard multi-base notation: explicit build-on / build-for per platform.
        # 'build-for' must be a single-element list, so each run-on arch becomes
        # its own platform entry, all sharing the same build-on list.
        # Platform name: <distribution>-<series>-<build-for-arch>
        #   e.g. ubuntu-22.04-amd64  (recommended by charmcraft docs)
        charmcraft['platforms'] = {}
        for entry in parsed:
            build_on_tuples = entry['build_on']
            run_on_tuples = entry['run_on']
            for run_base, run_arch in run_on_tuples:
                # e.g. ubuntu@22.04 -> ubuntu-22.04
                platform_name = run_base.replace('@', '-') + '-' + run_arch
                # Each entry gets its own list copy to avoid ruamel.yaml
                # generating YAML anchors (&id001) for the shared object.
                charmcraft['platforms'][platform_name] = {
                    'build-on': [f"{b}:{a}" for b, a in build_on_tuples],
                    'build-for': [f"{run_base}:{run_arch}"],
                }
        logger.info(
            "Cross-build detected; generated standard multi-base platforms with "
            "one platform entry per build-for architecture."
        )
    elif multi_base:
        # Multi-base shorthand: no top-level 'base' / 'build-base'.
        # Platform keys use the shorthand  <name>@<channel>:<arch>
        charmcraft['platforms'] = {}
        # Collect all (base, arch) pairs from build_on, preserving order.
        seen_platforms: List[str] = []
        for entry in parsed:
            for base_key, arch in entry['build_on']:
                platform_name = f"{base_key}:{arch}"
                if platform_name not in seen_platforms:
                    seen_platforms.append(platform_name)
        for platform_name in sorted(seen_platforms):
            charmcraft['platforms'][platform_name] = None
        logger.info(
            "Multiple bases detected (%s); generated multi-base shorthand platforms.",
            ", ".join(unique_bases),
        )
    else:
        # Single-base mode: top-level 'base' and 'build-base' keys.
        if args.base:
            base_value = args.base
        elif unique_bases:
            base_value = unique_bases[0]
        else:
            logger.error("Could not determine base from 'bases' section and --base not provided.")
            raise ValueError("No base found")

        charmcraft['base'] = base_value
        charmcraft['build-base'] = base_value

        if args.platforms:
            platforms = [p.strip() for p in args.platforms.split(',')]
        elif parsed:
            # Collect all build-on archs across all entries for this single base.
            all_archs: List[str] = []
            for entry in parsed:
                for _, arch in entry['build_on']:
                    if arch not in all_archs:
                        all_archs.append(arch)
            platforms = sorted(all_archs)
        else:
            logger.error("Could not determine platforms and --platforms not provided.")
            raise ValueError("No platforms found")

        charmcraft['platforms'] = {}
        for platform in platforms:
            charmcraft['platforms'][platform] = None
        logger.info(
            "Single base '%s'; generated platforms: %s.",
            base_value,
            ", ".join(platforms),
        )

    return charmcraft

def charm_tools(args: argparse.Namespace, charmcraft: Any) -> Any:
    """Set the charm snap with a specific channel in build-snaps for reactive charms.

    Looks for parts.charm.plugin == 'reactive' and updates the build-snaps list
    so that the 'charm' entry becomes 'charm/<channel>'.
    """
    try:
        parts = charmcraft['parts']
    except KeyError:
        logger.warning("'parts' not found in charmcraft document. Skipping.")
        return charmcraft

    try:
        charm_part = parts['charm']
    except KeyError:
        logger.warning("'parts.charm' not found in charmcraft document. Skipping.")
        return charmcraft

    plugin = charm_part.get('plugin', '')
    if plugin != 'reactive':
        logger.warning(
            "'parts.charm.plugin' is '%s', expected 'reactive'. Skipping.", plugin)
        return charmcraft

    channel = args.channel
    if channel is not None:
        new_snap = f"charm/{channel}"
        build_snaps = charm_part.get('build-snaps', None)
        if build_snaps is None:
            charm_part['build-snaps'] = [new_snap]
            logger.info("Created 'build-snaps' with '%s'.", new_snap)
        else:
            # Replace any existing 'charm' or 'charm/<something>' entry, or append.
            replaced = False
            for i, snap in enumerate(build_snaps):
                snap_str = str(snap)
                if snap_str == 'charm' or snap_str.startswith('charm/'):
                    build_snaps[i] = new_snap
                    replaced = True
                    logger.info("Updated build-snaps entry to '%s'.", new_snap)
                    break

            if not replaced:
                build_snaps.append(new_snap)
                logger.info("Appended '%s' to build-snaps.", new_snap)
    else:
        logger.info("No --channel provided; leaving build-snaps unchanged.")

    # Handle --add-build-arguments
    new_args = getattr(args, 'add_build_arguments', None)
    if new_args:
        build_arguments = charm_part.get('reactive-charm-build-arguments', None)
        if build_arguments is None:
            charm_part['reactive-charm-build-arguments'] = list(new_args)
            logger.info("Created 'reactive-charm-build-arguments' with %s.", new_args)
        else:
            for arg in new_args:
                if arg not in build_arguments:
                    build_arguments.append(arg)
                    logger.info("Appended '%s' to reactive-charm-build-arguments.", arg)
                else:
                    logger.info("'%s' already in reactive-charm-build-arguments, skipping.", arg)

    return charmcraft


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Modify the charmcraft.yaml file - initially just the '
                     'bases section'),
        epilog=("Note: this script doesn't parse the yaml; it does text "
                "search and replacements to find the relevant sections. This "
                "is to try as hard as possible to maintain the existing "
                "formatting in the file and keep minimal diffs."))
    parser.add_argument(dest='filename',
                        metavar='FILE',
                        help="Required filename to change.")
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')

    subparser = parser.add_subparsers(required=True, dest='cmd')

    delete_command = subparser.add_parser(
        'delete',
        help=('Remove a set of run-on/build-on for a base.'))
    delete_command.add_argument(
        '--base', '-b',
        dest='bases',
        nargs='+',
        required=True,
        help="The base to remove; repeat for more than one base.")
    delete_command.set_defaults(func=delete_bases)

    cc3ify_command = subparser.add_parser(
        'cc3ify',
        help=('Convert a charmcraft.yaml file to a charmcraft3.yaml file.'))
    cc3ify_command.add_argument(
        '--base', '-b',
        dest='base',
        required=False,
        default=None,
        help=("The base to use (for building and running) in single-base mode. "
              "When not provided, the base is inferred from the 'bases' section. "
              "Ignored when multiple bases are detected (multi-base mode)."))
    cc3ify_command.add_argument(
        '--platforms', '-p',
        dest='platforms',
        required=False,
        default=None,
        help=("Comma-separated list of platforms to use in single-base mode. "
              "When not provided, the architectures are inferred from the 'bases' "
              "section. Ignored when multiple bases are detected (multi-base mode)."))
    cc3ify_command.set_defaults(func=cc3ify)

    charm_tools_command = subparser.add_parser(
        'charm-tools',
        help=('Set the charm snap channel in build-snaps for reactive charms.'))
    charm_tools_command.add_argument(
        '--channel', '-c',
        dest='channel',
        required=False,
        default=None,
        help="The snap channel to use for the charm snap (e.g. '3.x/stable'). "
             "When not provided, the build-snaps section is left unchanged.")
    charm_tools_command.add_argument(
        '--add-build-arguments',
        dest='add_build_arguments',
        required=False,
        default=None,
        type=lambda s: [a.strip() for a in s.split(',')],
        help=("Comma-separated list of arguments to add to "
              "'parts.charm.reactive-charm-build-arguments' (reactive plugin only). "
              "Example: '--add-build-arguments=-v,--use-lock-file-branches'"))
    charm_tools_command.set_defaults(func=charm_tools)

    return parser.parse_args(argv)


# update the charmcraft.yaml file (passed on the line as arg1) and ensure that
# it has the bases added.
def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    try:
        with open(args.filename) as f:
            charmcraft = yaml.load(f)
    except FileNotFoundError:
        logger.error(f"Couldn't open {args.filename}")
        return
    except Exception as e:
        logger.error(f"Couldn't open {args.filename}: reason: {e}")
        return

    # Call the function associated with the sub-command.
    try:
        modified_charmcraft = args.func(args, charmcraft)
    except Exception:
        logger.error("Error occured; leaving without modifying %s",
                     args.filename)
        sys.exit(1)

    new_file_name = Path(args.filename).with_suffix('.new')
    yaml.dump(modified_charmcraft, new_file_name)
    # now overwrite the file
    os.rename(new_file_name, args.filename)


if __name__ == '__main__':
    logging.basicConfig()
    main()
