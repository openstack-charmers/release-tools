# release-tools

## About
Scripts used by OpenStack Charms automated and manual release processes for Charm Store uploading and releasing.

## Files
File | Purpose / Note
:--- | :---
```build-charm```           | Build src charms, enforce certain file and directory expectations.  Used by OSCI during tests.  Called by ```push-and-release``` as needed.
```charms.txt```            | The master list of all OpenStack charms which are subject to pushing/releasing via the git, gerrit, charm store flow.
```commit-message.txt```    | Used by ```commit-review-stable-charms``` by humans for various batch tasks.
```commit-review-stable-charms``` | Submit gerrit reviews on changes made in local charm checkout dirs; Generally useful for humans during batch changes (not used in OSCI).
```create-stable-branch```  | Create stable branches in charm repos.  Called by ```release-charms```, also used by humans during release processes.
```generate-repo-info```    | Used by OSCI to generate indentifying information about the checked out git repo and inject it into the charm dir before pushing and releasing.
```get-charms```            | Clones charm repos and checks out the provided branch.
```push-and-release```      | Used by OSCI automation to build, push and release charms after changes are merged and changed at the github repos.
```release-stable-charms``` | Do a new STABLE RELEASE from MASTER for all charms.
```source-charms.txt```     | Master list of 'source charms,' used by ```update-tox-files```.
```stable-branch-updates``` | Post-Release Repo Tasks: Flip stable charm-helpers and Amulet bits;  Update .gitreview with new stable branch name. Called by ```update-stable-charms```.
```update-stable-charms```  | Applies stable-branch-updates to all charms.
```update-tox-files```      | Enforce tox.ini file consistency across all charm repos (this is still in dev).
```./deprecated/```         | Bone yard of old scripts which should no longer be used.

## To-Do

* Refactor and streamline into a cleaner charm-pusher python module which reads a centralized list of charms and series, expressed in yaml.  Or something more elegant.
