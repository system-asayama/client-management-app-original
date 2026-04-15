#!/usr/bin/env bash
set -euo pipefail

REPO="system-asayama/client-management-app-original"
OUT_MAP="docs/issue_number_map.tsv"
BODY_FILE="/tmp/econtract_issue_body.md"

cat > "$BODY_FILE" <<'EOF'
目的:
- 電子契約システム導入計画の実装タスクを管理する

対応内容:
- チケットタイトルに記載された対象を実装する
- セキュリティ・法務・監査要件を満たす

依存Issue:
- 依存関係マップに従って追記

完了条件(DoD):
- plan.md の Definition of Done を満たす

検証方法:
- 自動テストと手動確認の証跡を提示

セキュリティ影響:
- yes/no を明記

法務レビュー要否:
- yes/no を明記

ロールバック:
- 手順を記載
EOF

# title|labels
declare -a ITEMS=(
  "[P0][T0-1] 認証共有仕様（Cookie/Session）凍結|priority:P0,area:integration,req:security,req:legal,status:ready"
  "[P0][T0-2] API契約凍結|priority:P0,area:backend,req:security,req:legal,status:ready"
  "[P0][T0-3] 状態遷移凍結（contract/signer）|priority:P0,area:backend,req:security,req:audit,status:ready"
  "[P0][T0-4] 監査ログハッシュ規約凍結|priority:P0,area:backend,req:security,req:audit,status:ready"
  "[P0][T1-1] 電子契約DBスキーマ実装|priority:P0,area:backend,req:security,req:audit,status:ready"
  "[P0][T1-2] 認可ミドルウェア実装|priority:P0,area:backend,req:security,status:ready"
  "[P0][T1-3] 契約API（create/list/detail）実装|priority:P0,area:backend,req:security,status:ready"
  "[P0][T1-4] 署名URL発行・検証実装|priority:P0,area:backend,req:security,status:ready"
  "[P1][T1-5] 監査ログhashチェーン実装|priority:P1,area:backend,req:audit,status:ready"
  "[P0][T2-1] eKYC連携実装|priority:P0,area:integration,req:kyc,req:security,status:ready"
  "[P0][T2-2] 同意API実装|priority:P0,area:backend,req:legal,req:audit,status:ready"
  "[P0][T2-3] 署名順制御実装|priority:P0,area:backend,req:security,status:ready"
  "[P0][T2-4] 事業者署名（SHA-256/KMS/PKCS#7）実装|priority:P0,area:backend,req:kms,req:security,status:ready"
  "[P0][T2-5] RFC3161タイムスタンプ付与実装|priority:P0,area:integration,req:tsa,req:legal,status:ready"
  "[P0][T2-6] 契約確定と証明書PDF生成|priority:P0,area:backend,req:legal,req:audit,status:ready"
  "[P1][T3-1] 契約管理UI実装|priority:P1,area:frontend,status:ready"
  "[P1][T3-2] 署名者UI実装|priority:P1,area:frontend,req:kyc,status:ready"
  "[P1][T3-3] 完了UI実装|priority:P1,area:frontend,status:ready"
  "[P1][T3-4] 既存側導線追加|priority:P1,area:integration,status:ready"
  "[P2][T4-1] Docker/secret整備|priority:P2,area:infra,req:security,status:ready"
  "[P2][T4-2] 監視・アラート整備|priority:P2,area:infra,req:audit,status:ready"
  "[P1][T4-3] E2E/異常系/改ざん検知|priority:P1,area:qa,req:security,req:audit,status:ready"
  "[P2][T4-4] 段階リリース|priority:P2,area:infra,req:legal,status:ready"
)

# TID order aligns with ITEMS
declare -a TIDS=(
  T0-1 T0-2 T0-3 T0-4 T1-1 T1-2 T1-3 T1-4 T1-5
  T2-1 T2-2 T2-3 T2-4 T2-5 T2-6
  T3-1 T3-2 T3-3 T3-4
  T4-1 T4-2 T4-3 T4-4
)

: > "$OUT_MAP"
printf "# ticket_id\tissue_number\n" >> "$OUT_MAP"

for i in "${!ITEMS[@]}"; do
  title="${ITEMS[$i]%%|*}"
  labels="${ITEMS[$i]#*|}"
  tid="${TIDS[$i]}"

  url=$(gh issue create --repo "$REPO" --title "$title" --body-file "$BODY_FILE" --label "$labels")
  issue_no=$(basename "$url")
  printf "%s\t%s\n" "$tid" "$issue_no" >> "$OUT_MAP"
  echo "Created $tid -> #$issue_no"
done

echo "Issue map written: $OUT_MAP"
