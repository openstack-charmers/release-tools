# release-tools

## About
Scripts used by OpenStack Charms automated and manual release processes for Charm Store uploading and publishing.

## Files
File | Purpose / Note
:--- | :---
```charms.txt``` | *A list of all OpenStack charms which are subject to pushing/publishing via the git, gerrit, charmstore flow.*
```commit-message.txt``` | *Not automated*
```create-stable-branch``` | *Not automated*
```get-charms``` | *Clones charm repos and checks out the provided branch.*
```precise.txt``` | *A list of charms to publish only for this series/release.*
```publish-charms``` | *Iterates ```push-and-publish```.*
```push-and-publish``` | *Used by ```push-and-publish-multi-series```.*
```push-and-publish-multi-series``` | *Used by OSCI automation to push and publish charms after changes are merged and changed at the github repos.*
```release-charms``` | *Not automated*
```stable-branch-updates``` | *Not automated*
```trusty.txt``` | *A list of charms to publish only for this series/release.*
```update-stable-charms``` | *Not automated*
```wily.txt``` | *A list of charms to publish only for this series/release.*
```xenial.txt``` | *A list of charms to publish only for this series/release.*

## To-Do
Note:  This initial set of scripts came about in a bit of a hurry when charm store ingestion was down, and OpenStack charms needed to be pushed to cs: en masse for the first time ever (@16.04).

* Add notes for not-automated scripts.
* Refactor and streamline into a cleaner charm-pusher python module which reads a centralized list of charms and series, expressed in yaml.
* Wait for charm-tools and charm store stabilize, perhaps aim for Juju 2.0.1 or 2.1 timeframe?
* Better yet, ideally rely solely on charm series metadata and act accordingly.
