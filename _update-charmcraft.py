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

def cc3ify(args: argparse.Namespace, charmcraft: Any) -> Any:
    try:
        _ = charmcraft['bases']
    except KeyError:
        logger.error("'bases' not found in charmcraft document, already charmcraft3.yaml?")
        raise

    # from bases -> base
    del charmcraft['bases']
    charmcraft['base'] = args.base
    charmcraft['build-base'] = args.base
    # also add platforms
    charmcraft['platforms'] = {}
    platforms = args.platforms.split(',')
    for platform in platforms:
        charmcraft['platforms'][platform] = {
            "build-on": platform,
            "build-for": platform,
        }

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
        required=True,
        help="The base to use (for building and running)")
    cc3ify_command.add_argument(
        '--platforms', '-p',
        dest='platforms',
        required=False,
        default="amd64,arm64,s390x,ppc64el",
        help="The platforms to use as a comma sep. list.")
    cc3ify_command.set_defaults(func=cc3ify)

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
