import ast
import os
import re
import subprocess
import time

from nim_router.logger import logger

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GIT_TIMEOUT = 90
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"

_BRANCH_RE = re.compile(r"^[A-Za-z0-9._\-/]{1,100}$")


class GitUpdateError(Exception):
    """Raised when an update operation cannot be completed."""

def _run_git(args: list[str], timeout: int = _GIT_TIMEOUT) -> tuple[int, str, str]:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=_BASE_DIR,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # rstrip only: leading whitespace is significant in `git status --porcelain`
        # output, where the first two columns are the status code.
        return res.returncode, res.stdout.rstrip("\n"), res.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git executable not found on this system"
    except subprocess.TimeoutExpired:
        return 124, "", f"git command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def _validate_branch(branch: str) -> str:
    branch = (branch or "main").strip()
    if (
        not _BRANCH_RE.match(branch)
        or branch.startswith("-")
        or ".." in branch
        or branch.startswith("/")
        or branch.endswith("/")
        or "//" in branch
    ):
        raise GitUpdateError(f"Invalid branch name: {branch!r}")
    return branch


def is_git_repo() -> bool:
    code, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"], timeout=15)
    return code == 0 and out == "true"


def _parse_commits(raw: str) -> list[dict]:
    commits: list[dict] = []
    for record in raw.split(_RECORD_SEP):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) < 5:
            continue
        full, short, subject, author, date = parts[:5]
        commits.append({
            "hash": short or full[:7],
            "full_hash": full,
            "subject": subject,
            "author": author,
            "date": date,
        })
    return commits


def _log_commits(ref_range: str) -> list[dict]:
    code, out, _ = _run_git([
        "log",
        f"--format=%H{_FIELD_SEP}%h{_FIELD_SEP}%s{_FIELD_SEP}%an{_FIELD_SEP}%aI{_RECORD_SEP}",
        ref_range,
    ], timeout=30)
    if code != 0:
        return []
    return _parse_commits(out)


def _dirty_files() -> list[str]:
    code, out, _ = _run_git(["status", "--porcelain"], timeout=30)
    if code != 0 or not out.strip():
        return []
    files = []
    for line in out.split("\n"):
        if len(line) < 4:
            continue
        # Porcelain format: XY <path> (or "XY <old> -> <new>" for renames)
        entry = line[3:]
        if " -> " in entry:
            entry = entry.split(" -> ")[-1]
        entry = entry.strip()
        if entry:
            files.append(entry)
    return files


def _find_conflicted_files() -> list[str]:
    """Return tracked files that contain unresolved conflict markers.

    Git can report a successful pull while leaving conflict markers in the
    working tree (for example when a file is untracked locally but tracked
    upstream). Such a file would break Python imports, so the update must be
    rolled back.
    """
    code, out, _ = _run_git(["ls-files", "-z"], timeout=30)
    if code != 0:
        return []
    broken = []
    marker = re.compile(r"^(<<<<<<< |=======$|>>>>>>> )", re.MULTILINE)
    for rel in out.split("\0"):
        if not rel:
            continue
        path = os.path.join(_BASE_DIR, rel)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except (OSError, ValueError):
            continue
        if marker.search(content):
            broken.append(rel)
    return broken


def _rollback_to(commit: str) -> None:
    """Reset the working tree and index back to a commit.

    `git reset --hard` also clears the unmerged index stages that a failed
    stash apply leaves behind, so the repository is left in a clean, usable
    state rather than mid-merge.
    """
    _run_git(["merge", "--abort"], timeout=30)
    _run_git(["reset", "--hard", commit], timeout=60)
    _run_git(["checkout", "--", "."], timeout=30)


def check_update(branch: str = "main") -> dict:
    """Fetch the remote and compare the local checkout against origin/<branch>."""
    branch = _validate_branch(branch)

    if not is_git_repo():
        return {
            "ok": False,
            "repo": False,
            "error": "This installation is not a git repository, so it cannot self-update.",
        }

    code, current_branch, err = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=15)
    if code != 0:
        return {"ok": False, "repo": True, "error": err or "Could not determine current branch."}

    code, local_commit, _ = _run_git(["rev-parse", "HEAD"], timeout=15)
    local_commit = local_commit[:7] if code == 0 else ""

    fetch_code, _, fetch_err = _run_git(
        ["fetch", "--quiet", "origin", branch], timeout=_GIT_TIMEOUT
    )
    if fetch_code != 0:
        return {
            "ok": False,
            "repo": True,
            "error": f"Could not reach the remote repository: {fetch_err or 'git fetch failed'}",
            "current_branch": current_branch,
            "local_commit": local_commit,
        }

    remote_ref = f"origin/{branch}"
    code, remote_commit, _ = _run_git(["rev-parse", remote_ref], timeout=15)
    if code != 0:
        return {
            "ok": False,
            "repo": True,
            "error": f"Remote branch '{branch}' was not found on the origin remote.",
            "current_branch": current_branch,
            "local_commit": local_commit,
        }
    remote_commit = remote_commit[:7]

    def _count(spec: str) -> int:
        c, out, _ = _run_git(["rev-list", "--count", spec], timeout=30)
        try:
            return int(out)
        except (TypeError, ValueError):
            return 0

    behind = _count(f"HEAD..{remote_ref}")
    ahead = _count(f"{remote_ref}..HEAD")

    dirty = _dirty_files()

    incoming = _log_commits(f"HEAD..{remote_ref}")
    local_only = _log_commits(f"{remote_ref}..HEAD")

    return {
        "ok": True,
        "repo": True,
        "target_branch": branch,
        "current_branch": current_branch,
        "local_commit": local_commit,
        "remote_commit": remote_commit,
        "behind": behind,
        "ahead": ahead,
        "diverged": behind > 0 and ahead > 0,
        "up_to_date": behind == 0,
        "dirty": len(dirty) > 0,
        "dirty_files": dirty[:20],
        "dirty_count": len(dirty),
        "incoming": incoming,
        "local_only": local_only,
        "checked_at": time.time(),
    }


def pull_update(branch: str = "main", force: bool = False) -> dict:
    """Fast-forward the local checkout to origin/<branch>."""
    branch = _validate_branch(branch)

    if not is_git_repo():
        raise GitUpdateError("This installation is not a git repository, so it cannot self-update.")

    code, current_branch, err = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], timeout=15)
    if code != 0:
        raise GitUpdateError(err or "Could not determine current branch.")

    if current_branch != branch:
        raise GitUpdateError(
            f"Local branch is '{current_branch}' but updates target '{branch}'. "
            f"Switch to '{branch}' to update from the dashboard."
        )

    dirty = _dirty_files()
    stash_ref = ""
    if dirty and not force:
        raise GitUpdateError(
            "The working tree has uncommitted changes. Commit or stash them before updating: "
            + ", ".join(dirty[:5])
            + (f" (+{len(dirty) - 5} more)" if len(dirty) > 5 else "")
        )
    if dirty and force:
        # Preserve local work in the stash rather than discarding it.
        code, out, err = _run_git(["stash", "push", "-u", "-m", "nim-router pre-update stash"], timeout=60)
        if code != 0:
            raise GitUpdateError(f"Could not stash local changes: {err or out or 'git stash failed'}")
        code, stash_ref, _ = _run_git(["rev-parse", "--verify", "refs/stash"], timeout=15)
        # Keep the FULL sha: an abbreviated sha is ambiguous once the stash
        # reflog holds more than one entry, and `git stash apply` would then
        # fail to restore the right one.
        stash_ref = stash_ref.strip() if code == 0 else ""

    code, _, fetch_err = _run_git(["fetch", "--quiet", "origin", branch], timeout=_GIT_TIMEOUT)
    if code != 0:
        _restore_stash(stash_ref)
        raise GitUpdateError(f"Could not reach the remote repository: {fetch_err or 'git fetch failed'}")

    code, behind_out, _ = _run_git(
        ["rev-list", "--count", f"HEAD..origin/{branch}"], timeout=30
    )
    behind = int(behind_out) if behind_out.isdigit() else 0
    if behind == 0:
        _restore_stash(stash_ref)
        return {
            "ok": True,
            "updated": False,
            "message": "Already up to date with the latest release.",
            "commits": [],
        }

    before_commit_full = _run_git(["rev-parse", "HEAD"], timeout=15)[1]
    before_commit = before_commit_full[:7]

    # --ff-only guarantees a fast-forward: never creates a merge commit and
    # never rewrites local history.
    code, out, err = _run_git(
        ["pull", "--ff-only", "origin", branch], timeout=_GIT_TIMEOUT
    )
    if code != 0:
        _restore_stash(stash_ref)
        detail = (err or out or "git pull failed").strip()
        raise GitUpdateError(f"Update failed: {detail}")

    after_commit = _run_git(["rev-parse", "HEAD"], timeout=15)[1][:7]
    applied = _log_commits(f"{before_commit}..{after_commit}")

    restored = True
    if stash_ref:
        restored = _restore_stash(stash_ref)
        if not restored:
            # `git stash pop` conflicted: the local edits collide with the
            # pulled changes and git left conflict markers in the working
            # tree. Roll the update back completely so the installation is
            # never left broken, then re-apply the stash on the pre-update
            # tree (where it applies cleanly) so no local work is lost.
            logger.error(
                "The update conflicted with local changes; rolling back to "
                f"{before_commit} and restoring your files."
            )
            _rollback_to(before_commit_full)
            restored = _restore_stash(stash_ref)
            raise GitUpdateError(
                "The update conflicted with your local changes. The gateway was "
                f"left on {before_commit} with your files restored. "
                "Please review the changes and try again."
            )

    # Safety net: never leave conflict markers in tracked files, which would
    # break Python imports on the next start.
    broken = _find_conflicted_files()
    if broken:
        logger.error(
            f"Conflict markers detected after update in: {', '.join(broken)}. "
            f"Rolling back to {before_commit}."
        )
        _rollback_to(before_commit_full)
        if stash_ref:
            _restore_stash(stash_ref)
        raise GitUpdateError(
            "The update produced conflicting files ("
            + ", ".join(broken)
            + f"). The gateway was rolled back to {before_commit}."
        )

    logger.success(f"Updated nim-router from {before_commit} to {after_commit} ({len(applied)} commit(s)).")

    return {
        "ok": True,
        "updated": True,
        "message": f"Updated to {after_commit} ({len(applied)} commit(s) applied).",
        "before_commit": before_commit,
        "after_commit": after_commit,
        "commits": applied,
        "local_changes_restored": restored,
        "stash_ref": stash_ref[:7] if (stash_ref and not restored) else "",
    }


def _stash_ref_for(sha: str) -> str:
    """Return the `stash@{N}` reference matching a stash commit sha.

    `git stash drop` only accepts a reflog reference (stash@{N}); passing a
    raw commit hash fails with "not a stash reference". The numeric index
    must be resolved at drop time because earlier entries can shift.
    """
    if not sha:
        return ""
    code, out, _ = _run_git(["stash", "list", "--format=%H %gd"], timeout=30)
    if code != 0:
        return ""
    for line in out.split("\n"):
        parts = line.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].startswith(sha):
            return parts[1]
    return ""


def _restore_stash(stash_ref: str) -> bool:
    """Apply a pre-update stash back onto the working tree.

    Uses `git stash apply` (not `pop`) so the stash entry survives a conflict.
    That way the update can be rolled back and the stash re-applied cleanly
    on the pre-update tree instead of leaving the entry stranded.
    """
    if not stash_ref:
        return True
    code, out, err = _run_git(["stash", "apply", stash_ref], timeout=60)
    if code == 0:
        # Applied cleanly -> the stash entry is no longer needed.
        _drop_stash(stash_ref)
        return True
    logger.warning(
        f"Could not restore stashed local changes ({err or out or 'git stash apply failed'}); "
        f"they remain in the stash (ref {stash_ref})."
    )
    return False


def _drop_stash(stash_ref: str) -> None:
    """Remove a stash entry by commit sha, if it is still present."""
    ref = _stash_ref_for(stash_ref)
    if not ref:
        return
    _run_git(["stash", "drop", ref], timeout=30)


def build_frontend(force: bool = True) -> bool:
    """Rebuild the web UI bundle so a pulled frontend change is served."""
    import shutil

    frontend_dir = os.path.join(_BASE_DIR, "frontend")
    npm_bin = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm_bin:
        logger.warning("Node.js/npm not found; skipping web UI rebuild.")
        return False

    node_modules_dir = os.path.join(frontend_dir, "node_modules")
    if not os.path.exists(node_modules_dir):
        logger.info("Installing frontend dependencies via npm...")
        res = subprocess.run([npm_bin, "install"], cwd=frontend_dir, timeout=600)
        if res.returncode != 0:
            logger.error("npm install failed; web UI rebuild skipped.")
            return False

    logger.info("Rebuilding web UI assets (Vite)...")
    try:
        res = subprocess.run([npm_bin, "run", "build"], cwd=frontend_dir, timeout=600)
    except subprocess.TimeoutExpired:
        logger.error("Web UI rebuild timed out.")
        return False
    if res.returncode == 0:
        logger.success("Web UI assets rebuilt successfully.")
        return True
    logger.error("Web UI rebuild failed.")
    return False
