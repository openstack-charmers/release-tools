from typing import Optional, Dict, Any


def decode_channel_map(charm: str,
                       result: Dict[str, Any],
                       track: str,
                       risk: str,
                       base: Optional[str] = None,
                       arch: Optional[str] = None,
                       ) -> int:
    """Decode the channel.

    Try to work out which revisions belong for a charm and the result from
    charmhub.  This is searched on the track/risk basis.  Optionally, it can
    further be constrained using the base the charm was built on (e.g. '20.04')
    and the arch (e.g. 'amd64').

    If more than one revision is found, then an error is returned.

    """
    assert '/' not in track
    revision_nums = set()
    for i, channel_def in enumerate(result['channel-map']):
        base_arch = channel_def['channel']['base']['architecture']
        base_channel = channel_def['channel']['base']['channel']
        channel_track = channel_def['channel']['track']
        channel_risk = channel_def['channel']['risk']
        revision = channel_def['revision']
        revision_num = revision['revision']
        arches = [f"{v['architecture']}/{v['channel']}"
                  for v in revision['bases']]
        arches_str = ",".join(arches)

        if ((base is None or base_channel == base) and
                (arch is None or base_arch == arch) and
                (channel_track, channel_risk) == (track, risk)):
            print(
                f"{charm:<30} ({i:2}) -> {base_arch:6} {base_channel} "
                f"r:{revision_num:3} "
                f"{channel_track:>10}/{channel_risk:<10} -> [{arches_str}]")
            revision_nums.add(revision_num)

    if not revision_nums:
        raise ValueError("No revisions available.")
    if len(revision_nums) > 1:
        raise ValueError(
            "More than 1 revision num found for charm: %s, revisions: %s",
            charm, sorted(revision_nums))
    return sorted(revision_nums)[-1]
