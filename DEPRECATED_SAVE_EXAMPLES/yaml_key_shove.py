#!/usr/bin/env python3
#
# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import logging
import optparse
import os
import sys
import yaml


USAGE = """Usage: %prog [options]

yaml_key_shove.py
==============================================================================
A generic tool to add or replace one or more top-level keys in a yaml file
with data from another yaml file.

If no keys are specified, ALL KEYS will be shoved from the --from-file into
the --to-file.

If the --to-file doesn't exist, it will be created.

Usage examples:
* Replace key1 and key2 in my.yaml with data from other.yaml, with debug
  output, and yes, confirm to overwrite my.yaml.

  %prog -yv -f other.yaml -t my.yaml -k "key1,key2"


* Replace two specific keys in tests.yaml with data from those named keys
  in zaza-required.yaml.

  %prog -yv -f zaza-required.yaml -t tests.yaml -k "gate_bundles,smoke_bundles"
"""


def read_yaml(the_file):
    """Returns yaml data from provided file name

    :param the_file: yaml file name to read
    :returns: dictionary of yaml data from file
    """
    if not os.path.exists(the_file):
        raise ValueError('File not found: {}'.format(the_file))
    with open(the_file) as yaml_file:
        logging.debug('Reading file: {}'.format(the_file))
        data = yaml.safe_load(yaml_file.read())
    return data


def write_yaml(data, the_file):
    """Save yaml data dictionary to a yaml file

    :param the_file: yaml file name to write
    :returns: dictionary of yaml data to write to file
    """
    logging.debug('Writing file: {}'.format(the_file))
    with open(the_file, 'w') as yaml_file:
        yaml_file.write(yaml.dump(data, default_flow_style=False))


def main():
    """Define and handle command line parameters
    """
    # Define command line options
    parser = optparse.OptionParser(USAGE)
    parser.add_option("-d", "-v", "--debug",
                      help="Enable debug logging",
                      dest="debug", action="store_true", default=False)
    parser.add_option('-y', '--yes-overwrite',
                      help='Overwrite the output file if it exists',
                      dest='overwrite', action='store_true', default=False)
    parser.add_option("-f", "--from-file",
                      help="YAML file from which to read one or more keys",
                      action="store", type="string", dest="from_file")
    parser.add_option("-t", "--to-file",
                      help="YAML file into which to shove the key data",
                      action="store", type="string", dest="to_file")
    parser.add_option("-k", "--keys",
                      help="Comma-separated list of keys",
                      action="store", type="string", dest="keys_string")

    params = parser.parse_args()
    (opts, args) = params

    # Handle parameters, inform user
    if opts.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.info('Logging level set to DEBUG!')
        logging.debug('parse opts: \n{}'.format(
            yaml.dump(vars(opts), default_flow_style=False)))
        logging.debug('arg count: {}'.format(len(args)))
        logging.debug('parse args: {}'.format(args))
    else:
        logging.basicConfig(level=logging.INFO)

    # Validate
    if not opts.from_file or not opts.to_file:
        parser.print_help()
        sys.exit(1)

    if os.path.isfile(opts.to_file) and opts.overwrite:
        logging.warning('Output file exists and will be '
                        'overwritten: {}'.format(opts.to_file))
    elif os.path.isfile(opts.to_file) and not opts.overwrite:
        logging.warning('Output file exists and will NOT '
                        'be overwritten: {}'.format(opts.to_file))
        raise ValueError('Output file exists, overwrite option not set.')

    if not os.path.isfile(opts.from_file):
        raise ValueError('Input file not found.')


    # Shove a key into a file
    from_dict = read_yaml(opts.from_file)

    if os.path.isfile(opts.to_file):
        to_dict = read_yaml(opts.to_file)
    else:
        to_dict = {}

    if opts.keys_string:
        keys_list = opts.keys_string.split(',')
    else:
        logging.warning('No keys specified, shoving ALL top-level keys!')
        keys_list = from_dict.keys()

    for _k in keys_list:
        to_dict[_k] = from_dict.get(_k)
        logging.debug("Setting {} key value as {}".format(_k, to_dict[_k]))

    write_yaml(to_dict, opts.to_file)


if __name__ == '__main__':
    main()
