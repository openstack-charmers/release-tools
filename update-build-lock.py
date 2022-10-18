#!/usr/bin/env python3

# Update the build lock by performing an action
# the action is either delete or modify or add:
# For delete, the type and item or package need to be specified.
# For modify the type/(item|package) must be specified plus the keys to modify
# For add the type/(item|package) must be specified plus ALL the keys to set.
# the build.lock file needs to be specified.  Note that it gets re-written
# completely.

import argparse
import copy
import json
import logging
import os
from pathlib import Path
import sys
from typing import List, Dict


logger = logging.getLogger(__name__)


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Modify the build.lock file for a charm.'),
        epilog=("Note; this script doesn't look up any of the keys. Pass it "
                "the correct data in the keys."))
    parser.add_argument('--file',
                        help="Required filename to change.")
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')

    # identity the element to add, modify or delete
    parser.add_argument('--type', '-t',
                        dest='type',
                        type=str.lower,
                        required=True,
                        choices=('layer', 'python_module'),
                        help='The type of lock')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--item', '-i',
                       dest='item',
                       metavar='ITEM',
                       help=('The item, when --type=layer; pass :all:'))
    group.add_argument('--package', '-p',
                       dest='package',
                       metavar='PACKAGE',
                       help=('The python module name, when '
                             '--type=python_module'))

    subparser = parser.add_subparsers(required=True, dest='cmd')

    add_command = subparser.add_parser(
        'add',
        help=('Add a lock to the build.lock file'))
    add_command.set_defaults(func=add_lock)
    add_command.add_argument(
        '--spec', '-s',
        dest='spec',
        required=True,
        help="The json spec of the parts to add.")
    modify_command = subparser.add_parser(
        'modify',
        help=('Modify an existing lock element.'))
    modify_command.set_defaults(func=modify_lock)
    modify_command.add_argument(
        '--spec', '-s',
        dest='spec',
        required=True,
        help="The json spec of the parts to modify.")
    delete_command = subparser.add_parser(
        'delete',
        help=('Delete an existing lock element.'))
    delete_command.set_defaults(func=delete_lock)
    lock_layer_command = subparser.add_parser(
        'lock-layer',
        help=("modify the layer so that the branch is locked to the commit "
              "sha."))
    lock_layer_command.set_defaults(func=lock_layer)

    return parser.parse_args(argv)


def add_lock(args: argparse.Namespace, locks: Dict) -> Dict:
    locks = copy.deepcopy(locks)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Couldn't decode '{args.spec}'")
    # Construct the full spec including args.type and args.item or args.package
    spec['type'] = args.type
    if args.type == 'layer':
        spec['item'] = args.item
    elif args.type == 'python_module':
        spec['package'] = args.package
    else:
        raise RuntimeError(f"Don't know how to add a {args.type} type of lock")
    try:
        for s in locks['locks']:
            if s['type'] == args.type:
                if ((args.type == 'layer' and args.item == s['item']) or
                        (args.type == 'python_module' and
                         args.package == s['package'])):
                    raise RuntimeError(
                        f"Expecting to add '{json.dumps(spec)}' but it "
                        f"already exists?")
    except Exception:
        raise
    # add the spec to the locks
    locks['locks'].append(spec)
    return locks


def modify_lock(args: argparse.Namespace, locks: Dict) -> Dict:
    locks = copy.deepcopy(locks)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Couldn't decode '{args.spec}'")
    spec['type'] = args.type
    if args.type == 'layer':
        spec['item'] = args.item
    elif args.type == 'python_module':
        spec['package'] = args.package
    else:
        raise RuntimeError(
            f"Don't know how to modify a {args.type} type of lock")
    try:
        for s in locks['locks']:
            if s['type'] == args.type:
                if ((args.type == 'layer' and args.item == s['item']) or
                        (args.type == 'python_module' and
                         args.package == s['package'])):
                    s.update(spec)
                    break
        else:
            raise RuntimeError(f"Couldn't find a lock spec to modify?")
    except Exception:
        raise
    return locks


def delete_lock(args: argparse.Namespace, locks: Dict) -> Dict:
    locks = copy.deepcopy(locks)
    if args.type not in ('layer', 'python_module'):
        raise RuntimeError(
            f"Don't know how to modify a {args.type} type of lock")

    new_locks = []
    found = False
    try:
        for s in locks['locks']:
            if s['type'] == args.type:
                if ((args.type == 'layer' and args.item == s['item']) or
                        (args.type == 'python_module' and
                         args.package == s['package'])):
                    found = True
                    continue
            new_locks.append(s)
    except Exception:
        raise
    if not(found):
        raise RuntimeError("Couldn't find the item to remove!")
    locks['locks'] = new_locks
    return locks


def lock_layer(args: argparse.Namespace, locks: Dict) -> Dict:
    """Lock the layers so that the branch is locked to the commit SHA."""
    locks = copy.deepcopy(locks)
    if args.type != 'layer':
        raise RuntimeError(
            f"Won't lock branches to commits for {args.type} type of lock")
    try:
        for s in locks['locks']:
            if s['type'] == 'layer':
                s['branch'] = s['commit']
    except Exception:
        raise
    return locks


# update the charmcraft.yaml file (passed on the line as arg1) and ensure that
# it has the bases added.
def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))

    # find the build.lock file.
    try:
        with Path(args.file).open() as f:
            locks = json.load(f)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Couldn't decode the lock file: {args.file}: {e}")
    except IOError as e:
        raise RuntimeError(f"Problem reading the lock file: {args.file}: {e}")
    except Exception as e:
        raise RuntimeError(
            f"Some other problem reading the lock file: {args.file}: {e}")


    # Call the function associated with the sub-command.
    modified_locks = args.func(args, locks)

    # write the modified_locks back IFF it was updated.
    if modified_locks is not None:
        new_file = Path(args.file).resolve().parent / "build.lock.new"
        with new_file.open("w") as f:
            json.dump(modified_locks, f, indent=2)
        # now overwrite the file
        os.rename(new_file, args.file)
        logger.info("Finished.")
    else:
        logger.info("Nothing done.")


if __name__ == '__main__':
    logging.basicConfig()
    try:
        main()
    except RuntimeError as e:
        logger.error("Problem with arguments or file: %s", str(e))
