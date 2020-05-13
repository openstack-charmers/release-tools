# release-tools

## About
Scripts used by OpenStack Charms automated and manual release processes for Charm Store uploading and releasing.

## Files
File | Purpose / Note
:--- | :---
```build-charm```           | Build src charms, enforce certain file and directory expectations.  Used by OSCI during tests.  Called by ```push-and-release``` as needed.
```charms.txt```            | The master list of all OpenStack charms which are subject to pushing/releasing via the git, gerrit, charm store flow.
```check-bug-links```       | Check the bug links
```create-stable-branch```  | Create stable branches in charm repos.  Called by ```release-charms```, also used by humans during release processes.
```generate-repo-info```    | Used by OSCI to generate indentifying information about the checked out git repo and inject it into the charm dir before pushing and releasing.
```get-charms```            | Clones charm repos and checks out the provided branch.
```push-and-release```      | Used by OSCI automation to build, push and release charms after changes are merged and changed at the github repos.
```release-stable-charms``` | Do a new STABLE RELEASE from MASTER for all charms.
```source-charms.txt```     | Master list of 'source charms,' used by ```update-tox-files```.
```stable-branch-updates``` | Post-Release Repo Tasks: Flip stable charm-helpers and Amulet bits;  Update .gitreview with new stable branch name. Called by ```update-stable-charms```.
```update-stable-charms```  | Applies stable-branch-updates to all charms.
```./DEPRECATED_SAVE_EXAMPLES/```         | Bone yard of old scripts which may or may not be useful or dangerous.
```batch-example```         | Tactical tool to sync tox, requirements, charm helpers.  Inspect, edit, use, and abuse.
```what-is```               | Tactical tool to identify the charm type (classic or source) and test framework (amulet or zaza) based solely on the contents of the cloned repo directory.
```_*```                    | Not typically used as stand-alone tools;  generally used as a call from another script (see batch-example).

## To-Do

* Refactor and streamline into a cleaner charm-pusher python module which reads a centralized list of charms and series, expressed in yaml.  Or something more elegant.
