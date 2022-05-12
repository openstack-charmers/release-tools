#!/usr/bin/env python3

# script to help with managing the series in a metadata.yaml file
# it provides four commands: list, add, remove and ensure
# - list the series in metadata.yaml;
# - add a series if it doesn't exist
# - remove a series if it does exist
# - ensure that the metadata contains the items on the args

import os
import sys
import collections

# from ruamel.yaml import YAML
import ruamel.yaml as YAML


Command = collections.namedtuple('Command', ['charm', 'cmd', 'params'])


def usage():
    print("usage: {} <charm> [list | add | remove | ensure] [<series, ...]"
          .format(sys.argv[0]))


def parse_args():
    if len(sys.argv) < 3:
        usage()
        sys.exit(1)
    charm = sys.argv[1]
    cmd = sys.argv[2].lower()
    if cmd not in ["list", "add", "remove", "ensure"]:
        print("Command '{}' not recognised.".format(cmd))
        usage()
        sys.exit(1)
    if cmd in ["add", "remove"]:
        if len(sys.argv) < 4:
            print("Command '{}' requires at least 1 argument".format(cmd))
            usage()
            sys.exit(1)
        param = [sys.argv[3]]
    elif cmd == "ensure":
        param = sys.argv[3:]
    else:
        param = []
    return Command(charm, cmd, param)


def run_command(cmd, yml):
    if cmd.cmd == "list":
        list_series(yml)
    elif cmd.cmd == "add":
        add_series(cmd, yml)
    elif cmd.cmd == "remove":
        remove_series(cmd, yml)
    # NOTE(ajkavanagh) - this hasn't actually been written yet.
    # elif cmd.cmd == "ensure":
    #     ensure_series_is(cmd, yml)
    else:
        print("Command?? {}".format(cmd))
        sys.exit(1)


def metadata_file(cmd):
    """Find the metadata.yaml file"""
    charm_dir = os.path.join("charms", cmd.charm)
    if not os.path.isdir(charm_dir):
        print("dir: {} doesn't exist.".format(charm_dir))
        sys.exit(1)
    metadata_in_root = os.path.join(charm_dir, 'metadata.yaml')
    if (os.path.isfile(metadata_in_root) and
            not os.path.islink(metadata_in_root)):
        return metadata_in_root
    metadata_in_src = os.path.join(charm_dir, 'src', 'metadata.yaml')
    if os.path.isfile(metadata_in_src):
        return metadata_in_src
    print("Can't find metadata!")
    sys.exit(1)


def load_yaml(cmd):
    with open(metadata_file(cmd)) as f:
        return YAML.load(f, YAML.RoundTripLoader)


def write_yaml(cmd, yml):
    with open(metadata_file(cmd), "w") as f:
        YAML.dump(yml, f, Dumper=YAML.RoundTripDumper)


def list_series(yml):
    print("Series are: {}".format(", ".join(yml['series'])))


def add_series(cmd, yml):
    series = cmd.params[0].lower()
    if series in yml['series']:
        print("Series '{}' already present; continuing".format(series))
        return
    yml['series'].append(series)
    print("Adding series '{}' to metadata".format(series))
    write_yaml(cmd, yml)


def remove_series(cmd, yml):
    series = cmd.params[0].lower()
    if series not in yml['series']:
        print("Series '{}' not present; ignoring remove".format(series))
        return
    yml['series'].remove(series)
    print("Removed series '{}' from metadata".format(series))
    write_yaml(cmd, yml)


def run():
    cmd = parse_args()
    yml = load_yaml(cmd)
    run_command(cmd, yml)


if __name__ == "__main__":
    run()
