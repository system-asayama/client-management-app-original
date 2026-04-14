#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash docs/annotate_day1_issues.sh \
#     --repo system-asayama/client-management-app-original \
#     --map docs/issue_number_map.tsv

REPO=""
MAP_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --map)
      MAP_FILE="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$REPO" || -z "$MAP_FILE" ]]; then
  echo "Required: --repo and --map" >&2
  exit 1
fi

if [[ ! -f "$MAP_FILE" ]]; then
  echo "Map file not found: $MAP_FILE" >&2
  exit 1
fi

declare -A ISSUE
while IFS=$'\t' read -r tid num; do
  [[ -z "${tid}" ]] && continue
  [[ "${tid:0:1}" == "#" ]] && continue
  ISSUE["$tid"]="$num"
done < "$MAP_FILE"

for t in T0-1 T0-2 T1-1 T1-2 T1-3 T1-4; do
  if [[ -z "${ISSUE[$t]:-}" ]]; then
    echo "Missing ticket mapping: $t" >&2
    exit 1
  fi
done

dep_lines() {
  local t="$1"
  case "$t" in
    T0-1) echo "- blocked_by: none" ;;
    T0-2) echo "- blocked_by: #${ISSUE[T0-1]} (T0-1)" ;;
    T1-1) echo "- blocked_by: #${ISSUE[T0-2]} (T0-2)" ;;
    T1-2) echo "- blocked_by: #${ISSUE[T0-1]} (T0-1)" ;;
    T1-3)
      echo "- blocked_by: #${ISSUE[T1-1]} (T1-1)"
      echo "- blocked_by: #${ISSUE[T1-2]} (T1-2)"
      ;;
    T1-4) echo "- blocked_by: #${ISSUE[T1-1]} (T1-1)" ;;
    *) echo "- blocked_by: unknown" ;;
  esac
}

for t in T0-1 T0-2 T1-1 T1-2 T1-3 T1-4; do
  issue_no="${ISSUE[$t]}"
  deps="$(dep_lines "$t")"

  body=$(cat <<EOF
Day 1 kickoff checklist
- ticket_id: ${t}
- owner: TBD
- due: TBD
- status_target_today: in-progress
- dependency_check:
${deps}

Acceptance focus (today)
- DoD short check passed
- security impact reviewed
- rollback note added
EOF
)

  gh issue comment "$issue_no" --repo "$REPO" --body "$body" >/dev/null
  echo "Commented #$issue_no ($t)"
done

echo "Day 1 kickoff comments applied."
