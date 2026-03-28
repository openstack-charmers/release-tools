#!python3

from datetime import datetime
import os
import argparse
import subprocess


def get_command_output(command):
    """Runs a shell command and returns its output."""
    result = subprocess.run(
        command, shell=True, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def get_revision(charm_name, track, base_channel, architecture, channel):
    """Gets the revision number from charmcraft status."""
    command = (
        f"charmcraft status {charm_name} --format json | "
        f'jq \'.[] | select(.track == "{track}").mappings[] | '
        f'select(.base.channel=="{base_channel}" and .base.architecture == "{architecture}") | '
        f'.releases[] | select(.channel == "{channel}").revision\''
    )
    revision = get_command_output(command)
    return revision


def get_revision_date(charm_name, revision):
    """Gets the revision creation date from charmcraft revisions."""
    command = (
        f"charmcraft revisions --format json {charm_name} | "
        f"jq '.[] | select(.revision == {revision}).created_at'"
    )
    revision_date = get_command_output(command)
    return revision_date.strip('"')  # Remove surrounding quotes from jq output


def get_commit_date(charm_name, branch):
    """Gets the last commit date of the given remote branch in the specified charm repository."""
    # Ensure the branch is fetched from the remote
    fetch_command = f"git -C {charm_name} fetch origin {branch}"
    fetch_result = get_command_output(fetch_command)
    if fetch_result is None:
        print(
            f"Failed to fetch branch '{branch}' from remote in repository '{charm_name}'."
        )
        return None

    # Get the last commit date from the fetched remote branch
    command = f"git -C {charm_name} log -1 --format=%ci origin/{branch}"
    commit_date = get_command_output(command)
    if not commit_date:
        print(
            f"Failed to retrieve commit date for branch '{branch}' on remote in repository '{charm_name}'."
        )
        return None

    return commit_date


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Fetch charmhub revision and commit dates, and print charms where the commit is newer than the revision."
    )
    parser.add_argument("--charm-name", help="Charm name (e.g., ceph-mon)")
    parser.add_argument(
        "--charm-dir", help="Directory containing multiple charm repositories"
    )
    parser.add_argument("--track", required=True, help="Track (e.g., squid)")
    parser.add_argument(
        "--base-channel", required=True, help="Base channel (e.g., 22.04)"
    )
    parser.add_argument(
        "--architecture", required=True, help="Architecture (e.g., amd64)"
    )
    parser.add_argument(
        "--channel", required=True, help="Channel (e.g., squid/candidate)"
    )
    parser.add_argument(
        "--branch", required=True, help="Branch (e.g., stable/squid-jammy)"
    )
    args = parser.parse_args()

    # Ensure either charm_name or charm_dir is provided
    if not (args.charm_name or args.charm_dir):
        print("Error: You must specify either --charm-name or --charm-dir.")
        return

    # If charm-dir is specified, iterate over subdirectories
    charm_dirs = []
    if args.charm_dir:
        if not os.path.isdir(args.charm_dir):
            print(f"Error: The directory '{args.charm_dir}' does not exist.")
            return
        # Get all subdirectories in the given directory
        charm_dirs = [
            os.path.join(args.charm_dir, d)
            for d in os.listdir(args.charm_dir)
            if os.path.isdir(os.path.join(args.charm_dir, d))
        ]

    # If charm_name is specified, process it as a single charm
    if args.charm_name:
        charm_dirs.append(args.charm_name)

    for charm_path in charm_dirs:
        charm_name = os.path.basename(charm_path)

        # Fetch revision
        revision = get_revision(
            charm_name,
            args.track,
            args.base_channel,
            args.architecture,
            args.channel,
        )
        if not revision:
            print(f"Failed to retrieve revision for charm '{charm_name}'.")
            continue

        # Fetch revision date
        revision_date = get_revision_date(charm_name, revision)
        if not revision_date:
            print(f"Failed to retrieve revision date for charm '{charm_name}'.")
            continue

        # Fetch commit date
        commit_date = get_commit_date(charm_path, args.branch)
        if not commit_date:
            print(f"Failed to retrieve commit date for charm '{charm_name}'.")
            continue

        # Convert dates to datetime objects for comparison
        revision_datetime = datetime.fromisoformat(revision_date)
        commit_datetime = datetime.fromisoformat(commit_date)

        # Print result only if commit date is newer than revision date
        if commit_datetime > revision_datetime:
            print(
                f"{charm_name}: Revision Date: {revision_date}, Commit Date: {commit_date}"
            )


if __name__ == "__main__":
    main()
