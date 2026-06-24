from __future__ import annotations
import os
from flask import Flask

# データベーステーブル作成（モジュールレベルで1回だけ実行）
try:
    from .db import Base, engine
    # モデルをインポートしてBaseに登録
    from . import models_login  # noqa: F401
    from . import models_auth  # noqa: F401
    from . import models_clients  # noqa: F401
    from . import models_company  # noqa: F401
    from . import models_client_users  # noqa: F401
    from . import models_homepage  # noqa: F401
    from . import models_voucher  # noqa: F401
    from . import models_property  # noqa: F401
    from . import models_truck  # noqa: F401
    from . import models_breeder  # noqa: F401
    from . import models_shortstay  # noqa: F401
    from . import models_construction  # noqa: F401
    from . import models_construction_ext  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("✅ データベーステーブル作成完了")
    
    # ログインシステムの自動マイグレーション実行
    try:
        from .auto_migrations import run_auto_migrations, run_truck_doc_migrations, run_breeder_new_table_migrations, run_pedigree_ancestor_migration, run_truck_schedule_migration, run_truck_store_id_migration, run_platform_table_migrations
        run_auto_migrations()
        print("✅ ログインシステム自動マイグレーション完了")
        run_truck_doc_migrations()
        print("✅ トラック書類カラムマイグレーション完了")
        run_breeder_new_table_migrations()
        print("✅ ブリーダー新テーブルマイグレーション完了")
        run_pedigree_ancestor_migration()
        print("✅ 血統書祖先テーブルマイグレーション完了")
        run_truck_schedule_migration()
        print("✅ 運行スケジュールテーブルマイグレーション完了")
        run_truck_store_id_migration()
        print("✅ トラック・ドライバー store_id マイグレーション完了")
        run_platform_table_migrations()
        print("✅ プラットフォームテーブルマイグレーション完了")
    except Exception as e:
        print(f"⚠️ ログインシステム自動マイグレーションエラー: {e}")
except Exception as e:
    print(f"⚠️ データベーステーブル作成エラー: {e}")

def create_app() -> Flask:
    """
    Flaskアプリケーションを生成して返します。
    Herokuで実行する場合もローカルで実行する場合もこの関数が呼ばれます。
    """
    app = Flask(__name__)

    # SECRET_KEY設定
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # アップロードフォルダ設定
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    _upload_dir = os.path.join(_base_dir, 'static', 'uploads', 'residents')
    os.makedirs(_upload_dir, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = _upload_dir
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB

    # デフォルト設定を読み込み（環境変数が無ければ標準値を使う）
    app.config.update(
        APP_NAME=os.getenv("APP_NAME", "login-system-app"),
        ENVIRONMENT=os.getenv("ENV", "dev"),
        DEBUG=os.getenv("DEBUG", "1") in ("1", "true", "True"),
        VERSION=os.getenv("APP_VERSION", "0.1.0"),
        TZ=os.getenv("TZ", "Asia/Tokyo"),
    )

    # config.py があれば上書き
    try:
        from .config import settings  # type: ignore
        app.config.update(
            ENVIRONMENT=getattr(settings, "ENV", app.config["ENVIRONMENT"]),
            DEBUG=getattr(settings, "DEBUG", app.config["DEBUG"]),
            VERSION=getattr(settings, "VERSION", app.config["VERSION"]),
            TZ=getattr(settings, "TZ", app.config["TZ"]),
        )
    except Exception:
        pass

    # logging.py があればロガーを初期化
    try:
        from .logging import setup_logging  # type: ignore
        setup_logging(debug=app.config["DEBUG"])
    except Exception:
        pass

    # CSRF トークンをテンプレートで使えるようにする
    @app.context_processor
    def inject_csrf():
        from .utils import get_csrf
        return {"get_csrf": get_csrf}

    # テナント/店舗情報をテンプレートで使えるようにする
    @app.context_processor
    def inject_context_info():
        from flask import session, url_for
        from .utils import get_db, _sql
        
        context = {
            'current_tenant_name': None,
            'current_store_name': None,
        }
        
        role = session.get('role')
        try:
            if role in ('system_admin', 'tenant_admin', 'admin', 'employee'):
                context['mypage_url'] = url_for('staff_mypage.dashboard')
            else:
                context['mypage_url'] = url_for('auth.index')
        except Exception:
            context['mypage_url'] = url_for('auth.index')

        context['viewing_as_banner'] = None
        try:
            from flask import request as _req_path
            _current_path = _req_path.path
        except Exception:
            _current_path = ''

        _own_path_prefixes = {
            'system_admin': '/system_admin',
            'app_manager': '/app_manager',
            'tenant_admin': '/tenant_admin',
            'admin': '/admin',
        }
        _own_prefix = _own_path_prefixes.get(role, '')
        _on_own_page = bool(_own_prefix and _current_path.startswith(_own_prefix))

        try:
            store_id_check = session.get('store_id')
            tenant_id_check = session.get('tenant_id')
            app_manager_group_id_check = session.get('app_manager_group_id')

            # system_adminは最初に判定（app_manager_group_idが残っていても影響されない）
            if role == 'system_admin':
                if store_id_check:
                    context['current_dashboard_url'] = url_for('admin.dashboard')
                    if not _on_own_page:
                        context['viewing_as_banner'] = 'システム管理者として閲覧中'
                elif tenant_id_check:
                    context['current_dashboard_url'] = url_for('tenant_admin.dashboard')
                    if not _on_own_page:
                        context['viewing_as_banner'] = 'システム管理者として閲覧中'
                else:
                    context['current_dashboard_url'] = url_for('system_admin.dashboard')
            elif role == 'admin':
                context['current_dashboard_url'] = url_for('admin.dashboard')
            elif role == 'tenant_admin':
                # tenant_adminは自分のページにいるときは自分のダッシュボードへ
                if _on_own_page:
                    context['current_dashboard_url'] = url_for('tenant_admin.dashboard')
                elif store_id_check:
                    context['current_dashboard_url'] = url_for('admin.dashboard')
                    context['viewing_as_banner'] = 'テナント管理者として閲覧中'
                else:
                    context['current_dashboard_url'] = url_for('tenant_admin.dashboard')
            elif role == 'app_manager':
                # app_managerは自分のページにいるときは自分のダッシュボードへ
                if _on_own_page:
                    context['current_dashboard_url'] = url_for('app_manager.dashboard')
                elif store_id_check:
                    context['current_dashboard_url'] = url_for('admin.dashboard')
                    context['viewing_as_banner'] = 'アプリ管理者として閲覧中'
                elif tenant_id_check:
                    context['current_dashboard_url'] = url_for('tenant_admin.dashboard')
                    context['viewing_as_banner'] = 'アプリ管理者として閲覧中'
                else:
                    context['current_dashboard_url'] = url_for('app_manager.dashboard')
            elif store_id_check:
                context['current_dashboard_url'] = url_for('admin.dashboard')
            elif tenant_id_check:
                context['current_dashboard_url'] = url_for('tenant_admin.dashboard')
            elif app_manager_group_id_check:
                context['current_dashboard_url'] = url_for('app_manager.dashboard')
            else:
                context['current_dashboard_url'] = url_for('auth.select_login')
        except Exception:
            context['current_dashboard_url'] = '/'
        
        # テナント情報を取得
        tenant_id = session.get('tenant_id')
        if tenant_id:
            try:
                conn = get_db()
                cur = conn.cursor()
                sql = _sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id=%s')
                cur.execute(sql, (tenant_id,))
                row = cur.fetchone()
                if row:
                    context['current_tenant_name'] = row[0]
                conn.close()
            except Exception:
                pass
        
        # 店舗情報を取得
        store_id = session.get('store_id')
        if store_id:
            try:
                conn = get_db()
                cur = conn.cursor()
                sql = _sql(conn, 'SELECT "名称", tenant_id FROM "T_店舗" WHERE id=%s')
                cur.execute(sql, (store_id,))
                row = cur.fetchone()
                if row:
                    context['current_store_name'] = row[0]
                    if not context['current_tenant_name'] and row[1]:
                        cur2 = conn.cursor()
                        sql2 = _sql(conn, 'SELECT "名称" FROM "T_テナント" WHERE id=%s')
                        cur2.execute(sql2, (row[1],))
                        row2 = cur2.fetchone()
                        if row2:
                            context['current_tenant_name'] = row2[0]
                conn.close()
            except Exception:
                pass

        if context.get('viewing_as_banner'):
            app_manager_group_name = None
            app_mgr_gid = session.get('app_manager_group_id')
            if app_mgr_gid:
                try:
                    from .models_login import TAppManagerGroup
                    from .db import SessionLocal
                    db = SessionLocal()
                    grp = db.query(TAppManagerGroup).filter(TAppManagerGroup.id == app_mgr_gid).first()
                    if grp:
                        app_manager_group_name = grp.group_name
                    db.close()
                except Exception:
                    pass

            subject_parts = []
            if app_manager_group_name:
                subject_parts.append(f'グループ「{app_manager_group_name}」')
            if context.get('current_tenant_name'):
                subject_parts.append(f'テナント「{context["current_tenant_name"]}」')
            if context.get('current_store_name'):
                subject_parts.append(f'店舗「{context["current_store_name"]}」')

            try:
                from flask import request as _req
                path = _req.path
                if '/dashboard' in path:
                    page_name = 'ダッシュボード'
                elif '/distribute' in path:
                    page_name = 'アプリ配布設定'
                elif '/plan' in path:
                    page_name = 'プラン設定'
                elif '/app_managers' in path:
                    page_name = 'アプリ管理者管理'
                elif '/tenants' in path:
                    page_name = 'テナント管理'
                elif '/stores' in path:
                    page_name = '店舗管理'
                elif '/api_keys' in path:
                    page_name = 'APIキー設定'
                elif '/members' in path:
                    page_name = 'メンバー管理'
                elif '/settings' in path:
                    page_name = '設定'
                else:
                    page_name = 'ページ'
            except Exception:
                page_name = 'ページ'

            role_label = context['viewing_as_banner']
            if subject_parts:
                subject_str = '・'.join(subject_parts)
                context['viewing_as_banner'] = f'{role_label} — {subject_str}の{page_name}を表示しています'
            else:
                context['viewing_as_banner'] = f'{role_label} — {page_name}を表示しています'
        
        return context

    # データベース初期化
    try:
        from .utils.db import get_db
        conn = get_db()
        try:
            conn.close()
        except:
            pass
        print("✅ データベース初期化完了")
    except Exception as e:
        print(f"⚠️ データベース初期化エラー: {e}")
    
    # データベースマイグレーション実行
    try:
        from .migrations import run_migrations
        run_migrations()
        print("✅ データベースマイグレーション完了")
    except Exception as e:
        print(f"⚠️ データベースマイグレーションエラー: {e}")

    # blueprints 登録
    try:
        from .blueprints.health import bp as health_bp  # type: ignore
        app.register_blueprint(health_bp)
    except Exception:
        pass

    try:
        from .blueprints.auth import bp as auth_bp
        app.register_blueprint(auth_bp)
    except Exception as e:
        print(f"⚠️ auth blueprint 登録エラー: {e}")

    try:
        from .blueprints.app_manager import bp as app_manager_bp
        app.register_blueprint(app_manager_bp)
    except Exception as e:
        print(f"⚠️ app_manager blueprint 登録エラー: {e}")

    try:
        from .blueprints.system_admin import bp as system_admin_bp
        app.register_blueprint(system_admin_bp)
    except Exception as e:
        print(f"⚠️ system_admin blueprint 登録エラー: {e}")

    try:
        from .blueprints.tenant_admin import bp as tenant_admin_bp
        app.register_blueprint(tenant_admin_bp)
    except Exception as e:
        print(f"⚠️ tenant_admin blueprint 登録エラー: {e}")

    try:
        from .blueprints.admin import bp as admin_bp
        app.register_blueprint(admin_bp)
    except Exception as e:
        print(f"⚠️ admin blueprint 登録エラー: {e}")

    try:
        from .blueprints.employee import bp as employee_bp
        app.register_blueprint(employee_bp)
    except Exception as e:
        print(f"⚠️ employee blueprint 登録エラー: {e}")

    try:
        from .blueprints.migrate import bp as migrate_bp
        app.register_blueprint(migrate_bp)
    except Exception as e:
        print(f"⚠️ migrate blueprint 登録エラー: {e}")

    try:
        from .blueprints.clients import bp as clients_bp
        app.register_blueprint(clients_bp)
    except Exception as e:
        print(f"⚠️ clients blueprint 登録エラー: {e}")

    try:
        from .blueprints.company import bp as company_bp
        app.register_blueprint(company_bp)
    except Exception as e:
        print(f"⚠️ company blueprint 登録エラー: {e}")

    try:
        from .blueprints.chat import bp as chat_bp
        app.register_blueprint(chat_bp)
    except Exception as e:
        print(f"⚠️ chat blueprint 登録エラー: {e}")

    try:
        from .blueprints.files import bp as files_bp
        app.register_blueprint(files_bp)
    except Exception as e:
        print(f"⚠️ files blueprint 登録エラー: {e}")

    try:
        from .blueprints.organization import bp as organization_bp
        app.register_blueprint(organization_bp)
    except Exception as e:
        print(f"⚠️ organization blueprint 登録エラー: {e}")

    try:
        from .blueprints.external import bp as external_bp
        app.register_blueprint(external_bp)
    except Exception as e:
        print(f"⚠️ external blueprint 登録エラー: {e}")

    try:
        from .blueprints.storage import bp as storage_bp
        app.register_blueprint(storage_bp)
    except Exception as e:
        print(f"⚠️ storage blueprint 登録エラー: {e}")

    try:
        from .blueprints.tenant_storage import bp as tenant_storage_bp
        app.register_blueprint(tenant_storage_bp)
    except Exception as e:
        print(f"⚠️ tenant_storage blueprint 登録エラー: {e}")

    try:
        from .blueprints.client_auth import bp as client_auth_bp
        app.register_blueprint(client_auth_bp)
    except Exception as e:
        print(f"⚠️ client_auth blueprint 登録エラー: {e}")

    try:
        from .blueprints.client_mypage import bp as client_mypage_bp
        app.register_blueprint(client_mypage_bp)
    except Exception as e:
        print(f"⚠️ client_mypage blueprint 登録エラー: {e}")

    try:
        from .blueprints.staff_mypage import bp as staff_mypage_bp
        app.register_blueprint(staff_mypage_bp)
        print("✅ staff_mypage blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ staff_mypage blueprint 登録エラー: {e}")

    try:
        from .blueprints.internal_chat import bp as internal_chat_bp
        app.register_blueprint(internal_chat_bp)
        print("✅ internal_chat blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ internal_chat blueprint 登録エラー: {e}")

    try:
        from .blueprints.mobile_api import bp as mobile_api_bp
        app.register_blueprint(mobile_api_bp)
        print("✅ mobile_api blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ mobile_api blueprint 登録エラー: {e}")

    try:
        from .blueprints.debug_routes import debug_bp
        app.register_blueprint(debug_bp)
    except Exception as e:
        print(f"⚠️ debug blueprint 登録エラー: {e}")

    try:
        from .blueprints.video_call import bp as video_call_bp
        app.register_blueprint(video_call_bp)
        print("✅ video_call blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ video_call blueprint 登録エラー: {e}")

    try:
        from .blueprints.kintaikanri import bp as kintaikanri_bp
        app.register_blueprint(kintaikanri_bp)
        print("✅ kintaikanri blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ kintaikanri blueprint 登録エラー: {e}")

    try:
        from .blueprints.finance import bp as finance_bp
        app.register_blueprint(finance_bp)
        print("✅ finance blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ finance blueprint 登録エラー: {e}")

    try:
        from .blueprints.store_dashboard import bp as store_dashboard_bp
        app.register_blueprint(store_dashboard_bp)
        print("✅ store_dashboard blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ store_dashboard blueprint 登録エラー: {e}")

    try:
        from .blueprints.homepage_builder import bp as homepage_builder_bp
        app.register_blueprint(homepage_builder_bp)
        print("✅ homepage_builder blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ homepage_builder blueprint 登録エラー: {e}")

    try:
        from .blueprints.voucher_store import bp as voucher_store_bp
        app.register_blueprint(voucher_store_bp)
        print("✅ voucher_store blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ voucher_store blueprint 登録エラー: {e}")

    try:
        from .blueprints.voucher_bank import bp as voucher_bank_bp
        app.register_blueprint(voucher_bank_bp)
        print("✅ voucher_bank blueprint 登録完了")
    except Exception as e:
        import traceback
        print(f"⚠️ voucher_bank blueprint 登録エラー: {e}")
        traceback.print_exc()

    try:
        from .blueprints.voucher_credit import bp as voucher_credit_bp
        app.register_blueprint(voucher_credit_bp)
        print("✅ voucher_credit blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ voucher_credit blueprint 登録エラー: {e}")

    try:
        from .blueprints.etax import bp as etax_bp
        app.register_blueprint(etax_bp)
        print("✅ etax blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ etax blueprint 登録エラー: {e}")

    try:
        from .blueprints.e_contract_bridge import bp as e_contract_bridge_bp
        app.register_blueprint(e_contract_bridge_bp)
        print("✅ e_contract_bridge blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ e_contract_bridge blueprint 登録エラー: {e}")

    try:
        from e_contract_service.migrations import run_migrations as ec_run_migrations
        from e_contract_service.blueprints.contracts import bp as ec_contracts_bp
        from e_contract_service.blueprints.signing import bp as ec_signing_bp
        from e_contract_service.blueprints.finalize import bp as ec_finalize_bp
        from e_contract_service.blueprints.ui import bp as ec_ui_bp
        from e_contract_service.blueprints.documents import bp as ec_documents_bp

        try:
            ec_run_migrations()
            print("✅ e_contract_service migrations 実行完了")
        except Exception as mig_err:
            print(f"⚠️ e_contract_service migrations エラー: {mig_err}")

        app.register_blueprint(ec_contracts_bp,  url_prefix='/e-contract/api/contracts')
        app.register_blueprint(ec_signing_bp,    url_prefix='/e-contract/api/sign')
        app.register_blueprint(ec_finalize_bp,   url_prefix='/e-contract/api/finalize')
        app.register_blueprint(ec_documents_bp,  url_prefix='/e-contract/api/documents')
        app.register_blueprint(ec_ui_bp,         url_prefix='/e-contract/ui')
        print("✅ e_contract_service blueprints 登録完了")
    except Exception as e:
        print(f"⚠️ e_contract_service blueprints 登録エラー: {e}")

    try:
        from .blueprints.teikan import bp as teikan_bp
        app.register_blueprint(teikan_bp)
        print("✅ teikan blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ teikan blueprint 登録エラー: {e}")

    try:
        from .blueprints.property import property_bp
        app.register_blueprint(property_bp)
        print("✅ property blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ property blueprint 登録エラー: {e}")

    try:
        from .blueprints.truck import bp as truck_bp
        app.register_blueprint(truck_bp)
        print("✅ truck blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ truck blueprint 登録エラー: {e}")

    try:
        from .blueprints.breeder import bp as breeder_bp
        app.register_blueprint(breeder_bp)
        print("✅ breeder blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ breeder blueprint 登録エラー: {e}")

    try:
        from .blueprints.survey_app import bp as survey_app_bp, _run_slot_migrations
        app.register_blueprint(survey_app_bp, url_prefix='/apps/survey')
        _run_slot_migrations()
        print("✅ survey_app blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ survey_app blueprint 登録エラー: {e}")

    try:
        import sys as _sys, os as _os
        _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
        from qr_print_routes import register_qr_print_routes
        register_qr_print_routes(app)
        print("✅ qr_print_routes 登録完了")
    except Exception as e:
        print(f"⚠️ qr_print_routes 登録エラー: {e}")

    try:
        from prize_print_routes import register_prize_print_routes
        register_prize_print_routes(app)
        print("✅ prize_print_routes 登録完了")
    except Exception as e:
        print(f"⚠️ prize_print_routes 登録エラー: {e}")

    try:
        from .blueprints.stampcard_app import bp as stampcard_app_bp
        app.register_blueprint(stampcard_app_bp)
        print("✅ stampcard_app blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ stampcard_app blueprint 登録エラー: {e}")

    try:
        from .blueprints.reservation_app import bp as reservation_app_bp
        app.register_blueprint(reservation_app_bp)
        print("✅ reservation_app blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ reservation_app blueprint 登録エラー: {e}")

    try:
        from .blueprints.shortstay import bp as shortstay_bp
        app.register_blueprint(shortstay_bp)
        print("✅ shortstay blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ shortstay blueprint 登録エラー: {e}")

    try:
        from .blueprints.owner import bp as owner_bp
        app.register_blueprint(owner_bp)
        print("✅ owner blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ owner blueprint 登録エラー: {e}")

    try:
        from .blueprints.construction import bp as construction_bp
        app.register_blueprint(construction_bp)
        print("✅ construction blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ construction blueprint 登録エラー: {e}")

    try:
        from .blueprints.construction_ext import bp as construction_ext_bp
        app.register_blueprint(construction_ext_bp)
        print("✅ construction_ext blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ construction_ext blueprint 登録エラー: {e}")

    try:
        from .blueprints.vtuber import bp as vtuber_bp
        app.register_blueprint(vtuber_bp)
        print("✅ vtuber blueprint 登録完了")
    except Exception as e:
        print(f"⚠️ vtuber blueprint 登録エラー: {e}")

    import json as _json
    @app.template_filter('from_json')
    def from_json_filter(value):
        if not value:
            return {}
        try:
            return _json.loads(value)
        except Exception:
            return {}

    @app.errorhandler(404)
    def not_found(error):
        from flask import render_template
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        from flask import render_template
        return render_template('500.html'), 500

    return app
