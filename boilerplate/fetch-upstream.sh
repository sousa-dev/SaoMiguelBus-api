#!/bin/bash
UPSTREAM_REPO_URL="git@github.com:sousa-dev/djast.git"

git remote add upstream "$UPSTREAM_REPO_URL"

git remote -v

git fetch upstream

git merge upstream/main main --allow-unrelated-histories

echo "Fetched and merged changes from upstream repository."