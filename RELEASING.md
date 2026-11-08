# Releasing

For maintainers. A release is a merge commit, an annotated tag, a source archive
and a GitHub release that all name the same tree.

## Version

[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The public interface
is the `007` CLI, the receipt and report schemas, and the dashboard snapshot.

- **Patch:** fixes and docs.
- **Minor:** a new compatible instrument or command.
- **Major:** a breaking change to the CLI, a schema or the snapshot.

## Prepare the release PR

1. **Version.** `SKILL.md` `metadata.version` is the single source, and
   `007 --version` reads it. Update the two pins that check it: `VERSION` in
   `scripts/dashboard.py` and `test_skill_identity_and_version` in
   `tests/test_package.py`.
2. **Changelog.** Turn `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`, add an empty
   `## [Unreleased]` above it, and update the compare links at the bottom.
3. **Release record.** `evidence/vX.Y.Z/release-evidence.md`: what qualifies the
   release (exact-commit CI, independent review status) and what it does not
   claim.
4. **Manifest, last.** It lists `git ls-files` minus the manifest itself, so
   stage new files first:

   ```bash
   v=vX.Y.Z
   git ls-files | grep -vx "evidence/$v/manifest.sha256" | xargs shasum -a 256 > "evidence/$v/manifest.sha256"
   shasum -a 256 -c "evidence/$v/manifest.sha256"
   ```

   The tag CI checks it with `sha256sum --check`. Regenerate it after any
   change, including a review fix.

## Release

1. **Merge** the PR with a merge commit, not a squash or rebase. Check that the
   merge tree equals the qualified head tree:
   `git rev-parse M^{tree} M^2^{tree}` must print the same hash twice, where `M`
   is the merge commit. CI on `main` must pass for `M`.
2. **Tag:** `git tag -a vX.Y.Z -m "007 Framework X.Y.Z" M`, then
   `git push origin vX.Y.Z`. The exact-tag CI must pass, with "Verify release
   manifest" shown as success, not skipped.
3. **Archive**, twice, and compare:

   ```bash
   git archive --format=tar.gz --prefix=007-framework-X.Y.Z/ -o a.tar.gz vX.Y.Z
   git archive --format=tar.gz --prefix=007-framework-X.Y.Z/ -o b.tar.gz vX.Y.Z
   cmp a.tar.gz b.tar.gz && mv a.tar.gz 007-framework-X.Y.Z.tar.gz && rm b.tar.gz
   shasum -a 256 007-framework-X.Y.Z.tar.gz > SHA256SUMS.txt
   ```

4. **Check the package** in an empty directory:

   ```bash
   tar -xzf 007-framework-X.Y.Z.tar.gz && cd 007-framework-X.Y.Z
   shasum -a 256 -c evidence/vX.Y.Z/manifest.sha256
   python3 bin/007 --version
   gitleaks dir --redact .
   ```

5. **Publish** the GitHub release with `007-framework-X.Y.Z.tar.gz` and
   `SHA256SUMS.txt`. The notes carry two sections:
   - **Exact distribution identity:** commit, tree (and the qualified head it
     equals), tag object, archive SHA-256 and size, manifest SHA-256, file count
     (`git rev-parse vX.Y.Z^{commit} vX.Y.Z^{tree} vX.Y.Z`,
     `git ls-tree -r --name-only vX.Y.Z | wc -l`).
   - **Qualification:** actual-main CI, exact-tag CI, independent review status.

Planned: a tag-triggered release workflow that builds the archive, attaches
build provenance through OIDC, and creates the release, replacing steps 3–5.
Until it exists, run them by hand.

## Rules

- A CI failure on `main` is investigated. Re-run only for a demonstrated flake,
  and record it in the release notes.
- The independent review follows `AGENTS.md`. A review whose served identity is
  unverified does not qualify a release; the notes say so.
- Publish first, announce after. The announcement is a separate step.
