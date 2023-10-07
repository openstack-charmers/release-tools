# Creating new tracks in Charmhub

The scripts in this subdirectory can be used to create tracks for charms that the user has access to.

## Background

The charmhub has added a facility to 'self-serve' creating tracks. Please review [the article][1] for further information.

Note that once the functionality has been finalized, it will be added to `charmhub-lp-tools` so that the metadata for the channel can be added and then just synced to the charmhub. This is temporarily in release-tools for convenience until this happens.

[1]: https://juju.is/docs/sdk/create-a-track-for-your-charm

## Scripts provided:

* `get-creds.sh` - get a short-lived set of credentials for charmhub so that tracks can be created.
* `list-tracks.sh` - list the existing tracks for a charm.
* `make-track.sh` - make a new track.

## Get the credentials

Run `get-creds.sh` in this subdirectory.  It will perform a login and put the credentials in a file called `charmhub-creds.dat`. You will almost certainly have to do a login/authorization via a web-browser.

## List existing tracks for a charm.

Use `list-tracks.sh` to list the existing tracks for a charm.

e.g.

```sh
$ ./list-tracks.sh
usage: ./list-tracks.sh {charm-name}

$ ./list-tracks.sh aodh
Tracks that exist for aodh are:
2023.1
2023.2
queens
rocky
stein
train
ussuri
victoria
wallaby
xena
yoga
zed
```

## Make a new track for a charm

Use `make-track.sh` to create the track:

```sh
$  ./make-track.sh
usage: ./make-track.sh {charm-name} {track-name}
$ ./make-track.sh garbage thing
Error in result; perhaps the charm name is wrong?
result is: '{"error-list":[{"code":"resource-not-found","message":"Name garbage not found in the charm namespace"}]}'
```

The command will fail if the track already exists.

## Preferred usage

As creating tracks is only done for each release, and the system will probably change, the approach to creating all the tracks is:

* Using release-tools `charmhub-lp-tool` get a list of all the charms.  e.g. `charmhub-lp-tool -p openstack list` will give a list of the latest charms.  Ensure that the charmed-openstack-info repository is up to date and has all the latest charms.

This will give an output like:

```
-------------------- ------------------------------ ---------------------------------------- ----------
Team                 Charmhub name                  LP Project Name                          Repository
-------------------- ------------------------------ ---------------------------------------- ----------
openstack-charmers   aodh                           charm-aodh                               https://opendev.org/openstack/charm-aodh.git
openstack-charmers   barbican                       charm-barbican                           https://opendev.org/openstack/charm-barbican.git
openstack-charmers   barbican-vault                 charm-barbican-vault                     https://opendev.org/openstack/charm-barbican-vault.git
openstack-charmers   ceilometer                     charm-ceilometer                         https://opendev.org/openstack/charm-ceilometer.git
openstack-charmers   ceilometer-agent               charm-ceilometer-agent                   https://opendev.org/openstack/charm-ceilometer-agent.git
openstack-charmers   cinder                         charm-cinder                             https://opendev.org/openstack/charm-cinder.git
openstack-charmers   cinder-backup                  charm-cinder-backup                      https://opendev.org/openstack/charm-cinder-backup.git
openstack-charmers   cinder-ceph                    charm-cinder-ceph                        https://opendev.org/openstack/charm-cinder-ceph.git
openstack-charmers   openstack-dashboard            charm-openstack-dashboard                https://opendev.org/openstack/charm-openstack-dashboard.git
openstack-charmers   designate                      charm-designate                          https://opendev.org/openstack/charm-designate.git
openstack-charmers   designate-bind                 charm-designate-bind                     https://opendev.org/openstack/charm-designate-bind.git
...
```

* Edit this into a file so that this looks like:

```sh
#!/usr/bin/env bash
./make-track.sh aodh 2023.2
./make-track.sh barbican 2023.3
./make-track.sh barbican-vault 2023.2
```

Use your editor to make this easy: i.e. use search/replace, etc.

* Run the file to create the tracks.
