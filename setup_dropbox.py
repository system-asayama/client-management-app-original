"""
DropboxアクセストークンをDBに登録するスクリプト
"""
from app.db import SessionLocal
from sqlalchemy import text

DROPBOX_TOKEN = "sl.u.AGaBfx-TM_FXtT8eL3yyPryLSmKwXKRM0zS0CGHgnZIF2FOdqFcQJOpbtkN_Je-qLZ81ebTfBIeqGmSKqm-dY9BCRjqZ_sYdFQbpYuVoQ1e4wSk1cO2LFWha3dyeeboAPbP2dwteuBgqMOkmyjR05Z3hdG_FcqdZvzfI1tNDflVt1hDSDDmWsF8_aWhYagfYlnbRDFmaFyGwxPJCC4toHhYrM4dIuRaOSiUJ8TPSB9JtKy3GOseglVr2YOBTPXwrrYaecu58cqP9g6UVr9wpVeffnlkHsX7uGRFIQV7ELVmWqws6JZ__O1PMWWBv87NT6sgazwQv3OYnJEqvt1z-eLr1vUPdyHj8T-bpIJjyJRmfEQ0rfzAHt-0EkLGdDZaVifAdQNpM-sQ0g3H7ROcNGA0ZvMQaOOrMwyGrd3py584fAgS7voDQwyyoWkYY3fHBLZuCWVvrIsiv7oZ52RvPFwMYqzQ91uuuDTH4a5lNb01jwIt5rsAJMOywp1L8ujaBEi3qMXVKgZmlDk4KlGLubsVVe53O6yzfoH3l14qbO-ghivpIqfEIpPeWS2bsGFuOla6WQbEe4wYjUk5Hybup_Furzyz97hm2BUmZ2h56aLG-b2QeuHvjY_UHrn4QxulSMazEh7fO1SQYEei7mEqPTUosTFXBL2XEACNTj5825RBvE4H0nbo3G8M5v2PRNcmeABGnU6NmFdlI1P165dSOkyusYQUUgtQKxGE9WMvkvo-rH5PmXSYjxNXslFiLqLJkfrX-wm_9f3OW3gD-IOuJX4Roon9iMo9j8zVH9KCutMWhU0m-zcMXipjjvd_-7W4etYgdtF5tbSGtv546MDes45zhrDVUWQkkf1elmMrOU3cYsg-yPyygSAAWsl1DESfMsRZ7pCrxQdpFi04X1RY1zY0Qyk5QGNntzH21yojAT17iF1OW2Bd6v2BOhjUDGyfXRk9vI10SEmDwXBxQwG0hD1qwiZNSY_vjN6Amfcat8FMPb7KLHIBI4BoKfV_sIcmc0Z5Z5CDEtD6Vag3Mkogly7mjVD5K_-DPCSz7tcR9bC4idJmJhASbvW9LEsnG_Ty4DMQ-Su3IoEfzBgRgy0PIxN3xZf7_PtnFy8mAGZf5t56L3q6qamH51SrU9VKFAqoPgWGHSBclaiqHw2F_fGI7Y9acnWh5wyOrns9IpD_M9cnkibXbMunZChJ2-YuXL7yDfI5c1pFUJwulnEW5gDitMXqFpWopK_YefJGCPj7oKXvRyEuvPtlXbqsUrhoL6LJjRBatzYFaAKmRtgv9BzINQiv-uFBP82dgVyelA_WBfjqarA"

db = SessionLocal()
try:
    # テナント一覧を確認
    tenants = db.execute(text('SELECT id, name FROM "T_テナント" ORDER BY id')).fetchall()
    print("=== テナント一覧 ===")
    for t in tenants:
        print(f"  id={t[0]}, name={t[1]}")

    # 全テナントにDropboxを設定
    for tenant in tenants:
        tenant_id = tenant[0]
        # 既存設定を無効化
        db.execute(text("""
            UPDATE "T_外部ストレージ連携"
            SET status = 'inactive'
            WHERE tenant_id = :tenant_id
        """), {"tenant_id": tenant_id})
        # 新規登録
        db.execute(text("""
            INSERT INTO "T_外部ストレージ連携"
            (tenant_id, provider, access_token, status)
            VALUES (:tenant_id, 'dropbox', :access_token, 'active')
        """), {"tenant_id": tenant_id, "access_token": DROPBOX_TOKEN})
        print(f"  テナントID={tenant_id} にDropboxを設定しました")

    db.commit()
    print("=== 完了 ===")
finally:
    db.close()
