#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash docs/issue_dependency_apply_template.sh \
#     --repo system-asayama/client-management-app-original \
#     --map docs/issue_number_map.tsv
#
# Map file format (TSV):
#   ticket_id<TAB>issue_number
#   Example: T1-3<TAB>128

REPO=""
MAP_FILE=""
DRY_RUN="false"

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
    --dry-run)
      DRY_RUN="true"
      shift
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

if ! command -v gh >/dev/null 2>&1; then
  echo "gh command is required" >&2
  exit 1
fi

declare -A ISSUE
while IFS=$'\t' read -r tid num; do
  [[ -z "${tid}" ]] && continue
  [[ "${tid:0:1}" == "#" ]] && continue
  ISSUE["$tid"]="$num"
done < "$MAP_FILE"

required_tickets=(
  T0-1 T0-2 T0-3 T0-4
  T1-1 T1-2 T1-3 T1-4 T1-5
  T2-1 T2-2 T2-3 T2-4 T2-5 T2-6
  T3-1 T3-2 T3-3 T3-4
  T4-1 T4-2 T4-3 T4-4
)

for t in "${required_tickets[@]}"; do
  if [[ -z "${ISSUE[$t]:-}" ]]; then
    echo "Missing ticket mapping: $t" >&2
    exit 1
  fi
done

# Dependency map (ticket IDs)
declare -A DEPS
DEPS[T0-1]=""
DEPS[T0-2]="T0-1"
DEPS[T0-3]="T0-2"
DEPS[T0-4]="T0-2"
DEPS[T1-1]="T0-2"
DEPS[T1-2]="T0-1"
DEPS[T1-3]="T1-1,T1-2"
DEPS[T1-4]="T1-1"
DEPS[T1-5]="T1-1"
DEPS[T2-1]="T1-4"
DEPS[T2-2]="T2-1"
DEPS[T2-3]="T1-4"
DEPS[T2-4]="T2-2,T2-3"
DEPS[T2-5]="T2-4"
DEPS[T2-6]="T2-5"
DEPS[T3-1]="T1-3"
DEPS[T3-2]="T1-4,T2-1,T2-2,T2-3"
DEPS[T3-3]="T2-6"
DEPS[T3-4]="T0-1"
DEPS[T4-1]="T1-3"
DEPS[T4-2]="T1-5,T2-5"
DEPS[T4-3]="T2-6,T1-5,T3-2"
DEPS[T4-4]="T4-3"

apply_dependency() {
  local ticket="$1"
  local issue_no="${ISSUE[$ticket]}"
  local deps_csv="${DEPS[$ticket]:-}"

  if [[ -z "$deps_csv" ]]; then
    return 0
  fi

  local dep_lines=""
  IFS=',' read -r -a dep_arr <<< "$deps_csv"
  for dep_ticket in "${dep_arr[@]}"; do
    dep_lines+="- blocked_by #${ISSUE[$dep_ticket]} (${dep_ticket})"$'\n'
  done

  local body
  body=$'dependency update\n'"$dep_lines"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY-RUN] gh issue comment $issue_no --repo $REPO --body ..."
    echo "[DRY-RUN] gh issue edit $issue_no --repo $REPO --add-label status:blocked"
  else
    gh issue comment "$issue_no" --repo "$REPO" --body "$body"
    gh issue edit "$issue_no" --repo "$REPO" --add-label "status:blocked"
  fi
}

for t in "${required_tickets[@]}"; do
  apply_dependency "$t"
done

echo "Done. Dependency comments and blocked labels applied."