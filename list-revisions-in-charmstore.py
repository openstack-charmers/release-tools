from typing import List, Tuple
import sys

import theblues.charmstore
import charmstore

name = "nova-compute"


def usage():
    print("usage: {} <charm-name>".format(sys.argv[0]))


def parse_args() -> str:
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)
    charm = sys.argv[1]
    return charm


def get_revisions(name: str) -> List[Tuple[str, str]]:
    charm = charmstore.CharmStore().search(name)[0]
    latest = charm.revision
    print("{} revisions for charm: {}".format(latest, name))

    cs = theblues.charmstore.CharmStore()

    results = []
    for a in range(1, int(latest)):
        print(".", end="", flush=True)
        try:
            results.append(("{}/{}".format(name, a),
                            (cs.entity("{}-{}"
                                       .format(name, a))
                             ['Meta']['extra-info']['vcs-revisions'][0]['date']
                             )))
        except Exception as e:
            print("Exception was: {}".format(str(e)))
            pass
    print()
    return results


def print_revisions(revisions: List[Tuple[str, str]]):
    for (name, date) in revisions:
        print(f"{name} - {date}")


def run():
    charm = parse_args()
    revisions = get_revisions(charm)
    print_revisions(revisions)


if __name__ == "__main__":
    run()
