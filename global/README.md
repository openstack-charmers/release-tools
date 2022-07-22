There are 3 basic OpenStack Charm structure:

1. Classic (non-reactive) + Zaza functional tests
2. Source (reactive) + Zaza functional tests
3. Ops (Operator framework)

The 'global' dir contains gold reference files for each of the above,
which should be maintained as the source of truth, and pushed out
into charm repos, rather than the other way around.

There is currently no systematic enforcement of the above, but the
centrally-managed files have DO NOT EDIT headers as a warning that
snowflake changes may be lost eventually when the next batch is
run.

If there is a desire or need to change a charm's tox file as a
snowflake, it should be deeply considered and questioned.
