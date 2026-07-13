---
name: finish-update
description: Bump version (major/minor/bugfix/rev), update docs, and push to git. Optionally build and publish a GitHub release.
argument-hint: [major|minor|bugfix|rev|branch] [release|beta|branch]
allowed-tools: Read, Edit, Write, Glob, Grep, Bash(git:*), Bash(gh:*), Bash(gradle:*), Bash(./gradlew:*), Bash(npm:*), Bash(yarn:*), Bash(adb:*)
---

## Task: Finish Update — Version Bump, Docs Update, and Git Push

Version type requested: **$1**
Release flag: **$2** (if `release`, build artifact and publish versioned GitHub release after push; if `beta`, build artifact and update the rolling `beta` pre-release on GitHub; if `branch`, build artifact and publish a branch pre-release)

Accepted values for $1: `major`, `minor`, `bugfix` (also accepts `patch` as alias for `bugfix`), `rev`, `branch`.

- `rev` means: **keep the version number the same**, but still update the changelog, architecture docs (if needed), commit, re-tag, and push.
- `branch` means: **keep the version number**, append the current git branch name as a suffix (e.g. `v2.3.5_natdex-support`), do NOT modify any version files or changelog, push the current branch, build the artifact, and optionally publish a pre-release. Skip Steps 3–6.
- If $1 is empty or not one of the above, stop and ask the user which type they want.
- If $2 is `release`, additional steps (build + versioned GitHub release) run after the git push.
- If $2 is `beta`, additional steps (build + update rolling beta pre-release) run after the git push.
- If $2 is `branch` (or `release` when $1 is `branch`), build + publish a branch pre-release (pre-release tagged with the branch-suffixed version).

---

## Step 1: Read Project Documentation First

Before doing anything, check if the project has a `CLAUDE.md`, `CLAUDE-architecture.md`, `ARCHITECTURE.md`, or any `docs/version-management.md`. Read these files. They may describe:
- Which file is the **source of truth** for the version
- Which other files must be kept in sync
- The format and structure of the changelog
- Any special version management workflow
- The build command to produce the release artifact

**Follow the project's documented patterns. Do not fall back to generic discovery if the project has already described its versioning approach.**

---

## Step 2: Discover and Read Version Files

Based on what you learned in Step 1, identify all version files. Also scan for any of the following that were not mentioned in the docs:
- `app.config.js` / `app.config.ts` — check for a `version:` field inside the expo config object
- `package.json` — top-level `"version"` field
- `pyproject.toml`, `setup.py`, `Cargo.toml`, `pubspec.yaml`, `*.csproj`, `pom.xml`, `version.txt`, `VERSION`, `__version__.py`
- Android: `app/build.gradle` or `app/build.gradle.kts` — `versionName` field

Read each file to get the current version string.

If the project docs identified a **source of truth**, read that file first and use its version as the canonical current version.

---

## Step 3: Calculate New Version

If $1 is `rev`, the version stays the same — skip to Step 5.

If $1 is `branch`:
1. Get current git branch name: `git branch --show-current`
2. Sanitize the branch name for use in a tag: replace `/` with `-`, strip any `feature/` or `hotfix/` prefix if desired (keep the descriptive part, e.g. `feature/natdex-support` → `natdex-support`)
3. Set BRANCH_SUFFIX = sanitized branch name
4. Set VERSION_TAG = `v{CURRENT_VERSION}_{BRANCH_SUFFIX}` (e.g. `v2.3.5_natdex-support`)
5. Skip to Step 7 (branch mode skips Steps 4, 5, 6)

Otherwise, parse the current version as `MAJOR.MINOR.PATCH` (semver) and apply the bump:
- `major` → increment MAJOR, reset MINOR and PATCH to 0
- `minor` → increment MINOR, reset PATCH to 0
- `bugfix` or `patch` → increment PATCH only

---

## Step 4: Update Version in All Files

(Skip this step if $1 is `rev`.)

Update the version string in every file identified in Step 2. Be precise — only change the version field, not unrelated occurrences of the number.

Common patterns:
- `version: "OLD"` → `version: "NEW"` in JS/TS config files
- `"version": "OLD"` → `"version": "NEW"` in JSON files
- `version = "OLD"` → `version = "NEW"` in TOML/Python
- `__version__ = "OLD"` in Python files
- `<Version>OLD</Version>` in XML project files
- `versionName "OLD"` → `versionName "NEW"` in Gradle files

---

## Step 5: Update the Changelog

Look for the project's changelog file. Check docs from Step 1 for the exact file and format. Also look for:
- `constants/changelog.ts` or `constants/changelog.js` (TypeScript/JS object format)
- `CHANGELOG.md` / `HISTORY.md` (Markdown format)

**Follow the existing format exactly.**

If $1 is `rev`, update the **existing** entry for the current version (add or amend changes to it rather than creating a new entry).

Otherwise, add a new entry at the **top** of the changelog for NEW_VERSION. For example:

```typescript
'NEW_VERSION': {
  version: 'NEW_VERSION',
  releaseDate: 'YYYY-MM-DD',
  highlights: 'Version bump ($1)',
  changes: [
    {
      category: 'improvement',
      title: 'Version Bump',
      description: '$1 version bump to NEW_VERSION.'
    }
  ]
},
```

Ask the user if they want to provide specific changelog entries before stubbing in the placeholder — if they already told you what changed, use that content instead.

---

## Step 6: Update Architecture / Documentation Files

Check `CLAUDE-architecture.md`, `ARCHITECTURE.md`, or any docs that reference the version number or describe features that have changed. Update them if needed.

This step applies for all bump types including `rev`.

---

## Step 7: Stage, Commit, Tag, and Push

### If $1 is `branch`:

1. Show `git status`
2. Push the current branch (do NOT commit anything — no version files changed):
   ```
   git push
   ```
   If no upstream is set, run `git push --set-upstream origin BRANCH_NAME` first.
3. Create a lightweight tag for the branch build (delete+recreate if it already exists):
   ```
   git tag -d VERSION_TAG                        # delete local if exists (ignore error)
   git push origin :refs/tags/VERSION_TAG        # delete remote if exists (ignore error)
   git tag VERSION_TAG                           # e.g. v2.3.5_natdex-support
   git push origin VERSION_TAG
   ```
4. Report the tag and confirm push succeeded. Then proceed to Step 8.

---

### Otherwise (major / minor / bugfix / rev):

1. Show `git status`
2. Stage all modified version and changelog files specifically (do NOT `git add -A`)
3. Commit:
   - If $1 is `rev`: `chore: update changelog for vVERSION`
   - Otherwise: `chore: bump version to NEW_VERSION ($1)`
4. Create an annotated git tag for the version. If $1 is `rev`, the tag may already exist — delete it locally and on the remote first, then re-create it:
   ```
   git tag -d vVERSION                        # delete local tag if it exists
   git push origin :refs/tags/vVERSION        # delete remote tag if it exists
   git tag -a vVERSION -m "Version VERSION"   # re-create
   ```
   For non-rev bumps, just create fresh:
   ```
   git tag -a vNEW_VERSION -m "Version NEW_VERSION"
   ```
5. Push commits and tags:
   ```
   git push
   git push --tags
   ```
   If no upstream is set, run `git push --set-upstream origin BRANCH_NAME` first.

Report the version and tag, and confirm push succeeded.

---

## Step 8: Build Release Artifact (only if $2 == "release" or $2 == "beta" or $2 == "branch", OR if $1 == "branch")

**Run this step AFTER Step 7 (git is committed and tagged). The build uses the already-bumped version.**

Detect the project type and run the appropriate build command. Check CLAUDE.md / project docs first for the documented build command. Otherwise use these defaults:

- **Android (Gradle):** Look for `gradlew` or `gradle` wrapper. Run the release/debug assemble target, e.g.:
  ```
  cd <app-dir> && ANDROID_HOME=... ./gradlew :app:assembleRelease --no-daemon
  ```
  The output APK is typically at `app/build/outputs/apk/release/app-release.apk` (or `app-release-unsigned.apk`). If a release build is not configured, fall back to `assembleDebug`.
- **Node/npm:** `npm run build`
- **Python:** `python -m build` or as documented

If the build **fails**, stop and report the error to the user. Do not proceed to GitHub release.

After a successful build, note the artifact path(s).

---

## Step 9: Publish Artifact (only if $2 == "release" or $2 == "beta" or $2 == "branch", OR if $1 == "branch" and $2 is non-empty)

### If $1 == "branch" (and $2 is "release", "branch", or any non-empty value): Publish Branch Pre-release

Delete any existing release for this branch tag, then create a new pre-release:

```
gh release delete VERSION_TAG --yes 2>/dev/null || true
gh release create VERSION_TAG ARTIFACT_PATH \
  --title "VERSION_TAG" \
  --notes "Branch build from \`BRANCH_NAME\` at v{CURRENT_VERSION}" \
  --prerelease
```

Report the GitHub release URL. This is the direct download link to share with testers.

---

### If $2 == "beta": Update Rolling Beta Pre-release

Delete and recreate the `beta` GitHub release with the new APK:

```
git push origin :refs/tags/beta           # delete remote beta tag if exists
gh release delete beta --yes              # delete beta release if exists
gh release create beta ARTIFACT_PATH \
  --title "Beta (latest dev build)" \
  --notes "Current build: vNEW_VERSION" \
  --prerelease
```

Report the beta release URL and stop. Do not proceed to 9a/9b.

---

### If $2 == "release": Synthesize Release Notes from the Changelog

### 9a: Synthesize Release Notes from the Changelog

Find the last GitHub release tag by running:
```
gh release list --limit 10
```
Identify the tag of the most recent published release (not the one being created now). Call it `LAST_RELEASE_VERSION`.

Read the project's changelog file in full. Find all entries with versions **between** LAST_RELEASE_VERSION (exclusive) and NEW_VERSION (inclusive) — these are the versions that will be collapsed into this release.

**Do not** simply concatenate the per-version entries. Synthesize them:

1. Collect all individual change items from every intermediate version's changelog entry.
2. Drop any item that was introduced and then reverted/fixed within this same release window (e.g., a bug introduced in v1.2.1 and fixed in v1.2.2 — omit both the original bug entry and the fix entry, since the net effect on users is zero).
3. Consolidate duplicate or closely related items into a single line.
4. Group surviving items by category (e.g., **Features**, **Improvements**, **Bug Fixes**).
5. Write the result as clean, user-facing Markdown. Concise. No internal churn or version-by-version structure.

The goal: a reader should understand "what changed since the last public release" without seeing the intermediate iteration history.

### 9b: Publish the Release

```
gh release create vNEW_VERSION ARTIFACT_PATH \
  --title "vNEW_VERSION" \
  --notes "$(cat <<'EOF'
<synthesized release notes from 9a>
EOF
)"
```

If the artifact is an APK, attach it as an asset. If there are multiple artifacts, attach all of them.

Report the GitHub release URL when done.
