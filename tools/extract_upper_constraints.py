#!/usr/bin/env python3

import argparse
import copy
from distutils.version import LooseVersion
import logging
import os
import pathlib
import re
import subprocess
import time
import tenacity
from typing import List, Optional, Union, Dict, Tuple
import sys
import yaml


logging.basicConfig()
logger = logging.getLogger(__name__)

CUR_DIR = pathlib.Path(__file__).parent.resolve()
CHARMS_FILE = os.path.abspath(os.path.join(CUR_DIR, '..', 'charms.txt'))
assert os.path.isfile(CHARMS_FILE), "{} doesn't exist?".format(CHARMS_FILE)
REPO_LINK_OVERRIDES = os.path.abspath(
    os.path.join(CUR_DIR, '..', 'repo-link-overrides.txt'))
assert os.path.isfile(REPO_LINK_OVERRIDES), \
    "{} doesn't exist?".format(REPO_LINK_OVERRIDES)


TOX_TARGETS: Tuple[str] = ('py3', 'pep8', 'cover', 'build', 'func-target')
UBUNTU_VERSIONS: Dict[str, str] = {
    'xenial': '16.04',
    'bionic': '18.04',
    'focal': '20.04',
    'groovy': '20.10',
    'hirsute': '21.04',
    'impish': '21.10',
    'jammy': '22.04',
}
_CHARMS: Optional[List[str]] = None


def charms() -> List[str]:
    global _CHARMS
    if _CHARMS is not None:
        return _CHARMS.copy()
    with open(CHARMS_FILE) as f:
        _CHARMS = list(line.strip() for line in f.readlines())
        return _CHARMS


_REPO_OVERRIDES = None


def repo_overrides() -> Dict[str, str]:
    global _REPO_OVERRIDES
    if _REPO_OVERRIDES is not None:
        return copy.deepcopy(_REPO_OVERRIDES)
    with open(REPO_LINK_OVERRIDES) as f:
        _REPO_OVERRIDES = dict(
            line.strip().split('|') for line in f.readlines())
        return copy.deepcopy(_REPO_OVERRIDES)


def ensure_instance(name: str, ubuntu: str, always_new: bool = False) -> None:
    logger.debug("Gettting instances ...")
    instances = get_all_instances()
    for i in instances:
        if i['name'] == name:
            if not(always_new):
                return name
            logger.info("Deleting existing instance: %s", name)
            delete_instance(name, force=True)

    # create a builder
    create_instance(name, ubuntu)
    logger.debug("Created instance %s, version %s", name, ubuntu)


def get_all_instances() -> List[dict]:
    output = run_output("lxc list --format=yaml")
    return yaml.safe_load(output)


def create_instance(name: str, ubuntu: str) -> None:
    try:
        version = UBUNTU_VERSIONS[ubuntu]
    except KeyError:
        raise RuntimeError(f"ubuntu version {ubuntu} not known; bailing")

    logger.debug("Creating instance %s with ubuntu:%s (%s)", name, version,
                 ubuntu)
    run(f"lxc launch ubuntu:{version} {name}")
    wait_for_ip_address(name)
    logger.debug(" ... done creating instance %s", name)


def wait_for_ip_address(name: str) -> None:
    while True:
        try:
            logger.debug("getting instances to check for IP")
            instance = [i for i in get_all_instances() if i['name'] == name][0]
        except IndexError:
            raise ValueError(f"No instance called {name}")
        try:
            devices = instance['state']['network']
            for device, status in devices.items():
                for address in status['addresses']:
                    if address['scope'] == 'local':
                        continue
                    if address['family'] == 'inet' and address['address']:
                        logger.debug("Address is: %s", address)
                        return
        except KeyError:
            pass
        time.sleep(0.5)


def delete_instance(name: str, force: bool = False) -> None:
    logger.debug("Deleting instance: %s", name)
    forced = "-f " if force else ""
    run(f"lxc delete {forced}{name}")


@tenacity.retry(wait=tenacity.wait_fixed(2),
                stop=tenacity.stop_after_attempt(3))
def run(cmd: Union[str, List[str]]) -> None:
    try:
        logger.debug("Running check_call '%s'", cmd)
        if isinstance(cmd, str):
            cmd = cmd.split(' ')
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        logger.error("Call '%s' failed, due to '%s'", cmd, str(e))
        raise


@tenacity.retry(wait=tenacity.wait_fixed(2),
                stop=tenacity.stop_after_attempt(3))
def run_output(cmd: Union[str, List[str]],
               expected_codes: Optional[List[int]] = None) -> bytes:
    try:
        logger.debug("Running check_output '%s'", cmd)
        if isinstance(cmd, str):
            cmd = cmd.split(' ')
        return subprocess.check_output(cmd)
    except subprocess.CalledProcessError as e:
        if expected_codes is not None and e.returncode in expected_codes:
            return e.output
        logger.error("Call '%s' failed, due to '%s'", cmd, str(e))
        raise


def ensure_pkgs_on_instance(name: str, pkgs: List[str],) -> None:
    logger.debug("running apt update && apt upgrade ...")
    execute_on_instance(name, ["apt", "update"])
    execute_on_instance(name, ['apt', 'upgrade', '-y'])
    logger.debug(" ... installing packages: %s", ", ".join(pkgs))
    execute_on_instance(name, ['apt', 'install', '-y'] + pkgs)
    logger.debug(" ... done install")


def ensure_user_modules(name: str,
                        modules: List[str],
                        user: Optional[str] = None
                        ) -> None:
    if modules:
        logger.debug('installing modules.')
        execute_on_instance(
            name, ['pip3', 'install', '--user'] + modules, user)
        logger.debug('..done.')


def execute_on_instance(name: str, cmd: List[str],
                        user: Optional[str] = None,
                        ) -> str:
    _cmd = ['lxc', 'exec', name, '--']
    if user is not None:
        _cmd.extend(
            ["su {} -l -c -- '{}'".format(user, ' '.join(cmd))])
    else:
        _cmd.extend(cmd)
    logger.debug("Executing on instance: %s", " ".join(_cmd))
    return subprocess.check_output(" ".join(_cmd), shell=True).decode()


def get_charm_source(charm: str) -> str:
    """Get the source repo for the charm.

    The charms are listed in charm(), the overrides in repo_overrides()
    and thus, we can construct a source using that information.
    """
    assert charm in charms(), f"'{charm}' is not known."
    try:
        return repo_overrides()[charm]
    except KeyError:
        return f"https://opendev.org/openstack/charm-{charm}"


def fetch_charm_source_on_instance(instance_name: str,
                                   charm: str,
                                   branch: Optional[str] = None) -> str:
    source = get_charm_source(charm)
    execute_on_instance(
        instance_name,
        f"if [ -e {charm} ]; then rm -rf {charm}; fi".split(" "),
        user='ubuntu')
    execute_on_instance(instance_name, ['git', 'clone', source, charm],
                        user='ubuntu')
    if branch is not None:
        execute_on_instance(instance_name, ['git', 'checkout', branch],
                            user='ubuntu')
    return charm


def find_tox_targets_on_instance(instance_name: str, dir_: str
                                 ) -> List[Tuple[str, str]]:
    """Assuming that the charm is in :param:`dir_`, get the tox targets from
    the tox file, matching them to the typical ones in the global TOX_TARGETS.

    :returns: a list of tox names to use.
    """
    matcher = re.compile(r"^\[testenv:(\S+)\]")
    tox_file = execute_on_instance(instance_name,
                                   ['cat', f"{dir_}/tox.ini"],
                                   user='ubuntu')
    targets = []
    for line in tox_file.splitlines():
        line = line.strip()
        match = matcher.match(line)
        if match and match[1] in TOX_TARGETS:
            targets.append(("", match[1]))
    if 'build' in targets:
        targets.append('src', 'func-target')
    return targets


def merge_pip_reports(reports: List[List[str]]) -> List[str]:
    """Merge the reports (list of list of string) into the lowest set.

    A requirement line with a version looks like module==version.
    Load the requirements into a Dict[str, LooseVersion] and then compare them
    so that we get the lowest set of constraints that work.  This becomes the
    upper-constraints file.
    """
    lowest_modules = {}
    for report in reports:
        modules = load_module_version(report)
        lowest_modules = pick_lowest(lowest_modules, modules)
    return [f"{m}=={str(lowest_modules[m])}"
            for m in sorted(lowest_modules.keys())]


def load_module_version(report: List[str]) -> Dict[str, LooseVersion]:
    modules = {}
    for line in report:
        if '==' in line:
            name, version_ = line.split('==', 2)
            modules[name] = LooseVersion(version_)
    return modules


def pick_lowest(current: Dict[str, LooseVersion],
                merge: Dict[str, LooseVersion]
                ) -> Dict[str, LooseVersion]:
    current = current.copy()
    for mod, version in merge.items():
        if mod in current:
            if version < current[mod]:
                current[mod] = version
        else:
            current[mod] = version
    return current


def get_pip_reports_for(instance_name: str,
                        dir_: str,
                        targets: List[Tuple[str, str]]
                        ) -> List[List[str]]:
    return [get_pip_report_for(instance_name, dir_, t) for t in targets]


def get_pip_report_for(instance_name: str,
                       dir_: str,
                       target: Tuple[str, str]
                       ) -> List[str]:
    if target[0]:
        to_dir = f"{dir_}/{target[0]}"
    else:
        to_dir = dir_
    cmd = f"cd {to_dir}; tox -e {target[1]} --notest"
    execute_on_instance(instance_name, [cmd], user='ubuntu')
    pip_file = execute_on_instance(
        instance_name,
        [f"{to_dir}/.tox/{target[1]}/bin/pip freeze"],
        user='ubuntu')
    logger.debug(pip_file)
    return [l.strip() for l in pip_file.splitlines()]


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse command line arguments.

    :param argv: List of configure functions functions
    :returns: Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description=('Extract package versions from a charm and ubuntu '
                     'version using an LXD builder of that ubuntu version. '
                     'Attempts provide an upper constraint using Semver.'),
        epilog=("Downloads the source and runs the various tox targets to "
                "extract the CI upper constrains for the charm."))
    parser.add_argument('charm',
                        metavar='CHARM',
                        help="The charm name; must be in charms.txt")
    parser.add_argument('ubuntu',
                        metavar='UBUNTU_VERSION',
                        help="The Ubuntu codename (e.g. focal) to build for.")
    parser.add_argument('--branch', dest='branch',
                        default='master',
                        help="The branch to do constraints for.")
    parser.add_argument('--keep-builder', dest='keep_builder',
                        action='store_true')
    parser.add_argument('--always-new-builder', dest='always_new_builder',
                        action='store_true')
    parser.add_argument('--file',
                        default=None,
                        help="Write output to a file")
    parser.add_argument('--log', dest='loglevel',
                        type=str.upper,
                        default='INFO',
                        choices=('DEBUG', 'INFO', 'WARN', 'ERROR', 'CRITICAL'),
                        help='Loglevel')
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    logger.setLevel(getattr(logging, args.loglevel, 'INFO'))
    logger.debug("Starting...")

    instance_name = f"builder-{args.ubuntu}"

    ensure_instance(
        instance_name, args.ubuntu, args.always_new_builder)
    ensure_pkgs_on_instance(instance_name, ['python3-pip'])
    ensure_user_modules(instance_name, ['tox>=3.18'], user='ubuntu')
    dir_ = fetch_charm_source_on_instance(instance_name, args.charm)
    targets = find_tox_targets_on_instance(instance_name, dir_)
    python_modules = merge_pip_reports(
        get_pip_reports_for(instance_name, dir_, targets))
    formatted = "{}\n".format("\n".join(python_modules))
    if args.file:
        with open(args.file, "wt") as f:
            f.write(formatted)
    else:
        print("modules are:")
        print(formatted)

    if not(args.keep_builder):
        delete_instance(instance_name, force=True)

    logging.info("Ended.")


if __name__ == '__main__':
    main()
