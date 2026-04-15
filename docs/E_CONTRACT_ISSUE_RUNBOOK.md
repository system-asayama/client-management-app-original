# E-Contract Issue Runbook

## Purpose
This runbook defines a fast and repeatable way to create and maintain issue dependencies for the e-contract rollout.

## Scope
- Repository: system-asayama/client-management-app-original
- Ticket IDs: T0-1 to T4-4
- Total issues: 23

## 5-Minute Issue Number Mapping
1. Run issue listing and capture numbers.
2. Build a TID-to-issue-number table.
3. Add dependency comments (`blocked_by`) to each issue.
4. Apply `status:blocked` or `status:ready` based on unresolved dependencies.
5. Verify critical path is strictly sequential: `T2-4 -> T2-5 -> T2-6`.

## Commands
```bash
gh issue list --repo system-asayama/client-management-app-original --limit 50
```

```bash
# Dry run with sample mapping
bash docs/issue_dependency_apply_template.sh \
	--repo system-asayama/client-management-app-original \
	--map docs/issue_number_map.example.tsv \
	--dry-run
```

```bash
# Real execution (replace map file with real numbers)
bash docs/issue_dependency_apply_template.sh \
	--repo system-asayama/client-management-app-original \
	--map docs/issue_number_map.tsv
```

```bash
# Mark blocked
gh issue edit <issue_no> --add-label "status:blocked"

# Add dependency comment
gh issue comment <issue_no> --body "dependency: blocked_by #<dep_no>"

# Move to ready after dependency completion
gh issue edit <issue_no> --remove-label "status:blocked" --add-label "status:ready"
```

## Dependency Map
- T0-1: none
- T0-2: T0-1
- T0-3: T0-2
- T0-4: T0-2
- T1-1: T0-2
- T1-2: T0-1
- T1-3: T1-1, T1-2
- T1-4: T1-1
- T1-5: T1-1
- T2-1: T1-4
- T2-2: T2-1
- T2-3: T1-4
- T2-4: T2-2, T2-3
- T2-5: T2-4
- T2-6: T2-5
- T3-1: T1-3
- T3-2: T1-4, T2-1, T2-2, T2-3
- T3-3: T2-6
- T3-4: T0-1
- T4-1: T1-3
- T4-2: T1-5, T2-5
- T4-3: T2-6, T1-5, T3-2
- T4-4: T4-3

## Day 1 Ready Gate
- T0-1, T0-2 approved
- T1-1, T1-2, T1-3, T1-4 set to `status:ready`
- No unresolved blocker on authentication, API errors, or token policy

## Weekly Review Metrics
- 401/403/409/410 trend
- KMS failure rate
- TSA failure rate
- eKYC failure rate
- Audit verify failure count
- Contract completion rate and average completion time

## Files
- docs/create_econtract_issues.sh
- docs/issue_dependency_apply_template.sh
- docs/issue_number_map.example.tsv
- docs/issue_number_map.tsv
- docs/annotate_day1_issues.sh

## Day 1 Kickoff Command
```bash
bash docs/annotate_day1_issues.sh \
	--repo system-asayama/client-management-app-original \
	--map docs/issue_number_map.tsv
```
