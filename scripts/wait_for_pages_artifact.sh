#!/usr/bin/env bash
set -euo pipefail

artifact_id="${PAGES_ARTIFACT_ID:?Pages upload did not return an artifact ID}"
[[ "$artifact_id" =~ ^[0-9]+$ ]]
endpoint="repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts?name=github-pages"

# Upload can finish before the artifact becomes visible to deployment.
for ((attempt = 1; attempt <= 18; attempt++)); do
  if artifacts=$(gh api "$endpoint" --jq '.artifacts[] | select(.expired == false) | .id') &&
     grep -Fxq "$artifact_id" <<< "$artifacts"; then
    echo "Pages artifact $artifact_id is available."
    exit 0
  fi
  if ((attempt < 18)); then
    echo "Waiting for Pages artifact $artifact_id ($attempt/18)."
    sleep 5
  fi
done

echo "::error::Pages artifact $artifact_id did not become visible in this workflow run."
exit 1
