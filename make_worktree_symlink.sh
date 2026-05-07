#!/bin/bash
# make_worktree_symlink.sh - Create symlinks for gitignored files in a worktree
# Run this script from the root of the NEW worktree after:
#   git worktree add -b <branch> <path>
#
# Usage:
#   cd /path/to/worktree
#   bash /path/to/original/make_worktree_symlink.sh

set -e

# Detect paths
MAIN_REPO_DIR="$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)"
WORKTREE_DIR="$(git rev-parse --show-toplevel)"

echo "Main repo: $MAIN_REPO_DIR"
echo "Worktree:  $WORKTREE_DIR"
echo ""

if [ "$MAIN_REPO_DIR" = "$WORKTREE_DIR" ]; then
    echo "Error: this doesn't appear to be a worktree (same as main repo)."
    exit 1
fi

# Items to symlink from main repo to worktree
ITEMS=(
    "bin"
    "include"
    "lib"
    "share"
    "pyvenv.cfg"
    ".env"
    "log"
    "scripts/data_analyzed"
)

for item in "${ITEMS[@]}"; do
    src="$MAIN_REPO_DIR/$item"
    dst="$WORKTREE_DIR/$item"

    if [ -e "$dst" ] || [ -L "$dst" ]; then
        echo "SKIP: $dst already exists"
        continue
    fi

    if [ ! -e "$src" ]; then
        echo "SKIP: $src does not exist in main repo"
        continue
    fi

    # Ensure parent directory exists in worktree
    mkdir -p "$(dirname "$dst")"
    ln -s "$src" "$dst"
    echo "LINK: $src -> $dst"
done

echo ""
echo "Done. Verifying symlinks:"
for item in "${ITEMS[@]}"; do
    dst="$WORKTREE_DIR/$item"
    if [ -L "$dst" ]; then
        echo "  OK: $item -> $(readlink "$dst")"
    fi
done
