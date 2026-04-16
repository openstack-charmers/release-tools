# release-tools

## About
Scripts used by OpenStack Charms automated and manual release processes for Charm Store uploading and releasing.

## Files
File | Purpose / Note
:--- | :---
```bug-link-overrides```    | A list of exceptions and overrides for charm bug trackers that deviate from the usual URL structure.
```build-charm```           | Build src charms, enforce certain file and directory expectations.  Used by OSCI during tests.  Called by ```push-and-release``` as needed.
```check-repo-links```      | Check the repo links
```check-bug-links```       | Check the bug links
```check-series```          | A crude check for LTS series presence in charm metadata.  It is not gating, just informational.
```create-stable-branch```  | Create stable branches in charm repos.  Called by ```release-charms```, also used by humans during release processes.
```generate-repo-info```    | Used by OSCI to generate indentifying information about the checked out git repo and inject it into the charm dir before pushing and releasing.
```get-charms```            | Clones charm repos and checks out the provided branch.
```push-and-release```      | Used by OSCI automation to build, push and release charms after changes are merged and changed at the github repos.
```release-stable-charms``` | Do a new STABLE RELEASE from MASTER for all charms.
```repo-link-overrides```   | A list of exceptions and overrides for charm repos that deviate from the usual URL structure.
```stable-branch-updates``` | Post-Release Repo Tasks: Flip stable charm-helpers and Zaza bits;  Update .gitreview with new stable branch name. Called by ```update-stable-charms```.
```update-stable-charms```  | Applies stable-branch-updates to all charms.
```./DEPRECATED_SAVE_EXAMPLES/```         | Bone yard of old scripts which may or may not be useful or dangerous.
```batch-example```         | Tactical tool to sync tox, requirements, charm helpers.  Inspect, edit, use, and abuse.
```what-is```               | Tactical tool to identify the charm type (classic or source) based solely on the contents of the cloned repo directory.
```_*```                    | Not typically used as stand-alone tools;  generally used as a call from another script (see batch-example).

## `_update-charmcraft.py`

A tool for migrating and modifying `charmcraft.yaml` files in charm repositories.
It preserves the original YAML formatting as much as possible to keep diffs minimal.

### Batch usage

```shell
./do-batch-with update-charmcraft <file> <subcommand> ...
```

### Subcommands

#### `delete`

Removes one or more `build-on`/`run-on` entries from the `bases` section by channel
(Ubuntu series). Handles both the short form (a `channel` key directly on the base
entry) and the long form (`build-on`/`run-on` sub-keys).

```
_update-charmcraft.py <file> delete --base <channel> [--base <channel> ...]
```

Example — remove the Ubuntu 20.04 entries from a `charmcraft.yaml`:

```bash
_update-charmcraft.py charmcraft.yaml delete --base 20.04
```

#### `cc3ify`

Converts a `charmcraft.yaml` from the deprecated charmcraft v2 `bases` format to
the charmcraft v3 `platforms` format.  The appropriate output style is chosen
automatically by inspecting the `bases` section:

| Input shape | Output style |
|---|---|
| Single base, `build-on` == `run-on` per entry | Top-level `base` + `build-base` keys, shorthand arch platform keys (`amd64:`, `arm64:`, …) |
| Multiple bases, `build-on` == `run-on` per entry | Multi-base shorthand (`ubuntu@22.04:amd64:`, `ubuntu@24.04:arm64:`, …) — no top-level `base`/`build-base` |
| Any entry where `build-on` ≠ `run-on` (cross-build) | Standard multi-base notation — one platform entry per `build-for` arch, each with a single-element `build-for` list |

```
_update-charmcraft.py <file> cc3ify [--base <base>] [--platforms <arch,...>]
```

`--base` and `--platforms` are optional overrides for single-base mode.
When not provided, values are inferred from the `bases` section.
Both flags are ignored in cross-build and multi-base shorthand modes.

**Example 1** — single base, inferred from file:

```bash
_update-charmcraft.py charmcraft.yaml cc3ify
```

Result:

```yaml
base: ubuntu@22.04
build-base: ubuntu@22.04
platforms:
  amd64:
  arm64:
  ppc64el:
  s390x:
```

**Example 2** — multiple bases, identical `build-on`/`run-on` per entry (shorthand):

```yaml
platforms:
  ubuntu@22.04:amd64:
  ubuntu@22.04:arm64:
  ubuntu@24.04:amd64:
  ubuntu@24.04:arm64:
```

**Example 3** — cross-build (`build-on` amd64 only, `run-on` multiple arches):

```yaml
platforms:
  ubuntu-22.04-amd64:
    build-on:
      - ubuntu@22.04:amd64
    build-for:
      - ubuntu@22.04:amd64
  ubuntu-22.04-arm64:
    build-on:
      - ubuntu@22.04:amd64
    build-for:
      - ubuntu@22.04:arm64
  # … one entry per build-for arch
```

## To-Do

* Refactor and streamline into a cleaner charm-pusher python module which reads a centralized list of charms and series, expressed in yaml.  Or something more elegant.
