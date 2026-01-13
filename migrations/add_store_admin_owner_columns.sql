-- T_管理者_店舗テーブルにオーナーと管理権限のカラムを追加
-- 実行日: 2025-12-31

-- is_ownerカラムを追加（店舗のオーナーかどうか）
ALTER TABLE `T_管理者_店舗` 
ADD COLUMN `is_owner` INT DEFAULT 0 COMMENT '店舗のオーナーかどうか（1店舗につき1人）';

-- can_manage_adminsカラムを追加（管理権限）
ALTER TABLE `T_管理者_店舗` 
ADD COLUMN `can_manage_admins` INT DEFAULT 0 COMMENT '店舗管理者を管理する権限';

-- インデックスを追加（パフォーマンス向上）
CREATE INDEX idx_store_admin_owner ON `T_管理者_店舗` (`store_id`, `is_owner`);
CREATE INDEX idx_store_admin_manage ON `T_管理者_店舗` (`admin_id`, `can_manage_admins`);

-- 既存データの確認用クエリ（実行前に確認）
-- SELECT * FROM `T_管理者_店舗`;

-- ロールバック用クエリ（必要な場合）
-- ALTER TABLE `T_管理者_店舗` DROP COLUMN `is_owner`;
-- ALTER TABLE `T_管理者_店舗` DROP COLUMN `can_manage_admins`;
-- DROP INDEX idx_store_admin_owner ON `T_管理者_店舗`;
-- DROP INDEX idx_store_admin_manage ON `T_管理者_店舗`;
