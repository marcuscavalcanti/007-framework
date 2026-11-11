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
   RELEASE_MANIFEST=evidence/vX.Y.Z/manifest.sha256 python3 - <<'PY'
   import hashlib, os, subprocess, tempfile
   from pathlib import Path
   target = Path(os.environ['RELEASE_MANIFEST'])
   if target.is_absolute() or '..' in target.parts or not target.name or any(c in str(target) for c in '\n\r\\'):
       raise SystemExit('manifest destination must be a relative repository file')
   if any(path.is_symlink() for path in (target, *target.parents)):
       raise SystemExit('manifest refuses symbolic links along its destination')
   names = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')[:-1]
   names = [name for name in names if name != target.as_posix()]
   if any(any(c in name for c in '\n\r\\') or any(p.is_symlink() for p in (Path(name), *Path(name).parents)) for name in names):
       raise SystemExit('manifest refuses escaped filenames and symbolic links')
   lines = [hashlib.sha256(Path(name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names]
   temporary = None
   try:
       with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent,
                                        prefix='.' + target.name + '.', delete=False) as output:
           temporary = Path(output.name)
           output.write(''.join(lines))
       os.replace(temporary, target)
   finally:
       if temporary is not None:
           temporary.unlink(missing_ok=True)
   PY
   shasum -a 256 -c evidence/vX.Y.Z/manifest.sha256
   ```

   The tag CI checks it with `shasum -a 256 --check` on Linux and macOS. Regenerate it after any
   change, including a review fix.
   Spaces in tracked filenames are preserved. Unsupported escape characters or
   symbolic links (including the destination and its parents) fail before
   publication; the tracked inventory is not split by shell whitespace. The
   complete list replaces the destination atomically, so a failed hash read
   does not publish a partial list. Run in a checkout with no concurrent writer.

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

The tag-triggered `release.yml` prepares the source archive twice, checks their
bytes and the extracted manifest, computes SHA256SUMS and attaches GitHub build
provenance through OIDC. It accepts stable annotated tags whose version agrees
with the CLI and whose release record exists. It retains a source-candidate
Actions artifact for the maintainer. Exact-tag CI, independent review and the
publication authorization remain required before step 5. Account configuration,
PyPI Trusted Publishing and announcement each keep their separate approval.

If tag-triggered preparation fails, keep the annotated tag and record the failed
run. After the workflow fix reaches `main`, dispatch `release.yml` on `main`
with the existing `tag` and its exact `tag_object` SHA. The job checks out the
tag, confirms the annotated object and builds from its peeled commit. Verify the
attestation against the workflow and commit that ran on `main`. Verify the
packaged source commit against the original annotated tag and retain the
successful exact-tag CI record.

## Rules

- CI runs for pull requests, pushes to `main`, and `v*` tags. Development
  branches receive CI through their pull request. Main and tag runs qualify
  their own release gates.
- CI retains the required `test (3.11)`, `test (3.12)` and `test (3.13)` check
  names on Linux and adds `test (3.13) macOS`. The package job exercises a
  wheel through pipx on Python 3.11. Dependabot proposes weekly GitHub Actions
  updates. Changes to required checks or account protection need a separate
  maintainer decision.
- A CI failure on `main` is investigated. Re-run only for a demonstrated flake,
  and record it in the release notes.
- The independent review follows `AGENTS.md` reviewer identity levels.
  `verified` qualifies; `pinned-no-reroute` qualifies only as "qualified with
  unverified reviewer identity", stated verbatim in the notes; `failed` does not
  qualify. Served identity is never filled from the request.
- Publish first, announce after. The announcement is a separate step. It may
  report any verdict (PROVEN, NOT-PROVEN or KILL) of a technically qualified
  release. NOT-PROVEN never states the thesis as proven, and a pilot's GO means
  only that a confirmation is feasible.
