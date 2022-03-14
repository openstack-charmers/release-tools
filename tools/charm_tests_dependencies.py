#!/usr/bin/env python3

# try to calculate the dependencies between the charms

# Uses the charms/ directory and iterates to find the tests.yaml and then the
# bundles to work out which charms depend on which other charms, based on
# gate-bundles.

from collections import namedtuple
import os
from pathlib import Path
from typing import Dict, List, Set
import yaml

import gvgen


CWD = os.path.dirname(os.path.realpath(__file__))

CHARMS_DIR = os.path.abspath(os.path.join(CWD, '../charms'))


def load_bundles(charm_dir: Path) -> Dict:
    yaml_file = os.path.join(charm_dir, 'tests.yaml')
    assert os.path.isfile(yaml_file)
    with open(yaml_file) as f:
        tests_yaml = yaml.safe_load(f)
    # find all the bundles from the tests_yaml.
    return get_all_bundle_names(tests_yaml)


def get_bundle_names_at(lb: List) -> Set[str]:
    assert isinstance(lb, list)
    bundles = set()
    for bundle in lb:
        if isinstance(bundle, dict):
            keys = list(bundle.keys())
            assert len(keys) == 1, f"Bundles is malformed? {lb} -> {bundle}"
            candidate = bundle[keys[0]]
            if isinstance(candidate, str):
                bundles.add(candidate)
            elif isinstance(candidate, list):
                # candidates should be a list of dicts
                for sub_spec in candidate:
                    assert isinstance(sub_spec, dict)
                    assert len(sub_spec.keys()) == 1
                    for _, sub_candidate in sub_spec.items():
                        assert isinstance(sub_candidate, str)
                        bundles.add(sub_candidate)
        elif isinstance(bundle, str):
            if ':' in bundle:
                bundle = bundle.split(':')[-1].strip()
            bundles.add(bundle)
    return bundles

def get_all_bundle_names(tests_yaml: Dict) -> Dict[str, Set[str]]:
    bundles = {}
    for key in ('smoke_bundles', 'gate_bundles', 'dev_bundles'):
        if key in tests_yaml:
            bundles_list = tests_yaml[key]
            if bundles_list:
                bundles[key] = get_bundle_names_at(tests_yaml[key])
            else:
                bundles[key] = set()
        else:
            bundles[key] = set()
    return bundles


def find_tests_dir(charm_dir: Path) -> Path:
    candidates = ('tests', 'src/tests')
    for c in candidates:
        dir_ = os.path.join(charm_dir, c)
        tests_yaml = os.path.join(dir_, 'tests.yaml')
        if os.path.exists(tests_yaml):
            return Path(dir_)
    raise FileNotFoundError("Couldn't find a tests.yaml")


def scan_for_charms(charm_dir: Path) -> List[str]:
    return [f for f in os.listdir(charm_dir)
            if os.path.isdir(os.path.join(charm_dir, f))]


def get_charms_from_bundle(bundle_yaml: Dict) -> List[str]:
    """Get the charm names from the bundle.

    Note that 'applications' is the new name, but it can also be under
    'services'
    """
    try:
        applications = bundle_yaml['applications']
    except KeyError:
        applications = bundle_yaml['services']
    charms = set()
    for app, app_spec in applications.items():
        # print(app, app_spec)
        if 'charm' in app_spec:
            charm_spec = app_spec['charm']
            if charm_spec.startswith('..'):
                continue
            if ':' in charm_spec:
                charm_spec = charm_spec.split(':')[1]
            if '/' in charm_spec:
                charm_spec = charm_spec.split('/')[-1]
            if '-' in charm_spec:
                parts = list(charm_spec.split('-'))
                if parts[-1].isdigit():
                    parts = parts[:-1]
                charm_spec = '-'.join(parts)
            if len(charm_spec) == 1:
                assert False

            charms.add(charm_spec)
    return list(sorted(charms))


def get_bundle_yaml(charm_dir: Path, bundle_name: str) -> Dict:
    """Get the bundle file as yaml.

    This also searches for an overlay and merges in that as well.
    """
    file_name = os.path.join(charm_dir, 'bundles', f"{bundle_name}.yaml")
    with open(file_name) as f:
        return yaml.safe_load(f)
    # TODO: deal with an overlay?


def dependencies_for_charm(charm_name: str) -> Set[str]:
    dir_ = find_tests_dir(os.path.join(CHARMS_DIR, charm_name))
    bundle_sets = load_bundles(dir_)
    # print(bundle_sets)
    all_charms = set()
    if 'gate_bundles' in bundle_sets:
        for bundle_name in bundle_sets['gate_bundles']:
            # print(f" bundle name: {bundle_name}")
            bundle_charms = get_charms_from_bundle(
                get_bundle_yaml(dir_, bundle_name))
            all_charms.update(bundle_charms)
    try:
        all_charms.remove(charm_name)
    except KeyError:
        pass
    # print(f"{charm_name}: {all_charms}")
    return all_charms


def get_all_charm_dependencies() -> Dict[str, Set[str]]:
    charms = scan_for_charms(CHARMS_DIR)
    dependencies = {}
    for charm in charms:
        print(f"Doing {charm}:")
        dependencies[charm] = dependencies_for_charm(charm)
    return dependencies


def determine_dag_or_cyclic_for(dependencies: Dict[str, Set[str]],
                                charm: str) -> Set[str]:
    depends = follow_dependencies(dependencies, charm)
    return charm in depends


def follow_dependencies(dependencies: Dict[str, Set[str]],
                                charm: str) -> Set[str]:
    return _follow_dependencies(dependencies, set(), charm)


def _follow_dependencies(dependencies: Dict[str, Set[str]],
                         current: Set[str],
                         charm: str) -> Set[str]:
    if charm not in dependencies:
        current.add(charm)
        return current
    charms = dependencies[charm]
    for c in charms:
        if c not in current:
            current.add(c)
            # note that current is reference and it copies - so as this is
            # single-threaded it's okay and will be a performance improvement.
            current.update(_follow_dependencies(dependencies, current.copy(), c))
    return current


def generate_graph(dependencies: Dict[str, Set[str]]) -> gvgen.GvGen:
    graph = gvgen.GvGen()
    items = {}
    for charm in dependencies.keys():
        items[charm] = graph.newItem(charm)
    # also add any items for charms that are dependencies, but aren't OpenStack
    # controlled charms.
    all_charms = set()
    for targets in dependencies.values():
        all_charms.update(targets)
    for charm in all_charms:
        if charm not in items:
            items[charm] = graph.newItem(charm)
    # now add the links between the items
    for charm, targets in dependencies.items():
        for target in targets:
            graph.newLink(items[charm], items[target])
    # all done
    return graph


def generate_graph_for_charm(
        charm: str,
        dependencies: Dict[str, Set[str]]) -> gvgen.GvGen:
    graph = gvgen.GvGen()
    items = {}
    items[charm] = graph.newItem(charm)
    print(f"doing {charm}")
    for target in dependencies[charm]:
        if target not in items:
            items[target] = graph.newItem(target)
            graph.newLink(items[charm], items[target])
        # now see if we should graph a link back to charm
        print(f"... {target}")
        paths = find_paths_back_to(target, charm, dependencies)
        print(" >> ", paths)
        if paths:
            for path in paths:
                # the path is next -> next -> charm
                if path:
                    current = target
                    for next_ in path:
                        if next_ not in items:
                            items[next_] = graph.newItem(next_)
                            graph.newLink(current, next_)
                        else:
                            break
                        current = next_
    # should add any links back.
    # all done
    print(f"done {charm}")
    return graph


def find_paths_back_to(from_: str,
                       to_: str,
                       dependencies: Dict[str, Set[str]]) -> List[List[str]]:
    print('finding', from_, to_)
    return _find_paths_back_to([], from_, to_, dependencies)

def _find_paths_back_to(path: List[str],
                        at_: str,
                        target: str,
                        dependencies: Dict[str, Set[str]]) -> List[List[str]]:
    print("_find", path, at_, target)
    path_ = path.copy()
    path_.append(at_)
    if len(path_) > 5:
        print("bailing")
        return []
    try:
        next_set = dependencies[at_]
    except KeyError:
        print("keyerror")
        return []
    if target in next_set:
        return [path_ + [target]]
    paths = []
    for next_ in next_set:
        if next_ not in path_:
            paths.extend(_find_paths_back_to(
                path_, next_, target, dependencies))
    return paths



def test() -> None:
    dependencies = get_all_charm_dependencies()
    print(dependencies)
    print()
    for charm in sorted(dependencies.keys()):
        print("charm:", charm, determine_dag_or_cyclic_for(dependencies,
                                                           charm))
    # generate the dotfile
    graph = generate_graph(dependencies)
    with open('graph.viz', 'wt') as f:
        graph.dot(f)



def main() -> None:
    dependencies = get_all_charm_dependencies()
    # for charm in sorted(dependencies.keys()):
        # graph = generate_graph_for_charm(charm, dependencies)
        # with open(os.path.join('graphs', f"{charm}.dot"), "wt") as f:
            # graph.dot(f)
    charm = 'keystone'
    graph = generate_graph_for_charm(charm, dependencies)
    with open(os.path.join('graphs', f"{charm}.dot"), "wt") as f:
        graph.dot(f)
    print('done')


if __name__ == '__main__':
    main()

