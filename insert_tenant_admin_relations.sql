-- T_テナント管理者_テナント中間テーブルにデータを追加

-- test tenant (ID: 12) をテストテナント (tenant_id: 1) に割り当て（オーナー）
INSERT INTO "T_テナント管理者_テナント" (admin_id, tenant_id, is_owner)
SELECT 12, 1, 1
WHERE NOT EXISTS (
    SELECT 1 FROM "T_テナント管理者_テナント" 
    WHERE admin_id = 12 AND tenant_id = 1
);

-- 浅山弘志 (ID: 13) を税理士法人OKS (tenant_id: 2) に割り当て（オーナー）
INSERT INTO "T_テナント管理者_テナント" (admin_id, tenant_id, is_owner)
SELECT 13, 2, 1
WHERE NOT EXISTS (
    SELECT 1 FROM "T_テナント管理者_テナント" 
    WHERE admin_id = 13 AND tenant_id = 2
);

-- 浅山弘志 (ID: 13) をテストテナント (tenant_id: 1) にも割り当て（一般管理者）
INSERT INTO "T_テナント管理者_テナント" (admin_id, tenant_id, is_owner)
SELECT 13, 1, 0
WHERE NOT EXISTS (
    SELECT 1 FROM "T_テナント管理者_テナント" 
    WHERE admin_id = 13 AND tenant_id = 1
);

-- 確認用クエリ
SELECT * FROM "T_テナント管理者_テナント" ORDER BY admin_id, tenant_id;
