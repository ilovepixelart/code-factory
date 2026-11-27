# Releasing Code Factory

The first public alpha targets one owner using Local mode from source on macOS or running
the board and database in Server mode. Both setups expose the board on loopback. Claude Code
and Codex authenticate separately in Local mode. GitHub delivery requires the GitHub CLI and a
repository whose merge policy permits merge commits.

1. On a fresh macOS host, follow the [Local mode quickstart](../quickstart.md#local-mode).
   Confirm sign-in, the sample board, repository tracking and a first agent run. Keep the sandbox
   and merge approval enabled. Run `python3 scripts/check_compose.py` to verify Server mode
   sign-in and persistence. **Verify** also runs this smoke test separately on Ubuntu.
2. Pass the full gate and the dependency audits. The **Verify** workflow runs each part of the gate
   as its own job on native Ubuntu x64 runners (`scripts/gate.sh --part`), each test job with its
   own PostgreSQL instance and the integration tests in two halves (`--shard`); a last job combines
   their coverage, checks the floor once and sends it to SonarCloud. It also scans all reachable
   commits; the local gate covers macOS and arm64. Run the browser tests by hand before a release
   (`pnpm --dir web e2e`): they are not in the gate or CI. Use passing jobs before claiming support
   for an additional platform.
   Ubuntu's real sandbox tests must start Bubblewrap with seccomp enabled. A runner that reaches
   the [nested user namespace failure](https://github.com/anthropics/sandbox-runtime/issues/428)
   is an open compatibility issue. Keep the sandbox enabled while investigating.
3. Build the app and verify the installed wheel outside the source checkout. Use a local database
   ending in `_test` and install the matching PostgreSQL client utilities. The smoke test uses an
   isolated schema, starts the installed board, checks sign-in and assets, and restores its backup.

   ```sh
   sh scripts/build_release.sh
   uv run --no-sync python scripts/check_release.py dist/*.whl
   ```

   Set `CODE_FACTORY_GATE_DATABASE_URL` in the environment before running the smoke test.

4. Run the signed-in Claude Code and Codex acceptance cases with
   `uv run --no-sync python scripts/replay_runs.py --live`. In a designated GitHub trial
   repository, open a real pull request through Factory. Require the full gate and owner approval,
   then verify that the approved head is the merged one and the board records it as Merged.
5. Enable required checks, merge commits and private vulnerability reporting in the public
   repository. Attach the verified source and release notes to the alpha tag. Publish packages
   only from the same reviewed revision and verified build.
