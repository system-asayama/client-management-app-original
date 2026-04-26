# -*- coding: utf-8 -*-
"""
プリンタ印刷設定管理 Blueprint
new-pos-system-app/admin_printer_format.py から移植
pos_app ブループリントに統合
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import logging

pos_printer_format_bp = Blueprint('pos_printer_format', __name__, url_prefix='/apps/pos')


@pos_printer_format_bp.route('/admin/printer-format/<printer_name>')
def printer_format_settings(printer_name):
    """プリンタ印刷設定画面"""
    from app.blueprints.pos_app import (
        SessionLocal, current_store_id, is_store_admin_or_higher,
        PrinterFormatSetting, Base, _shared_engine_or_none
    )
    if not session.get("logged_in") or not is_store_admin_or_higher():
        return redirect(url_for("pos_app.admin_login", next=request.path))

    s = SessionLocal()
    try:
        sid = current_store_id()
        eng = _shared_engine_or_none()
        if eng:
            try:
                Base.metadata.create_all(bind=eng, tables=[PrinterFormatSetting.__table__])
            except Exception as e:
                logging.warning(f"Could not create PrinterFormatSetting table: {e}")

        setting = s.query(PrinterFormatSetting).filter(
            PrinterFormatSetting.store_id == sid,
            PrinterFormatSetting.printer_name == printer_name
        ).first()

        if not setting:
            setting = PrinterFormatSetting(store_id=sid, printer_name=printer_name)
            s.add(setting)
            s.commit()

        return render_template(
            'pos/printer_format_settings.html',
            printer_name=printer_name,
            setting=setting
        )
    except Exception as e:
        logging.error(f"Error in printer_format_settings: {e}", exc_info=True)
        flash(f'設定画面の表示に失敗しました: {str(e)}', 'error')
        return redirect(url_for('pos_app.admin_printers'))
    finally:
        s.close()


@pos_printer_format_bp.route('/admin/printer-format/<printer_name>/save', methods=['POST'])
def save_printer_format_settings(printer_name):
    """プリンタ印刷設定を保存"""
    from app.blueprints.pos_app import (
        SessionLocal, current_store_id, is_store_admin_or_higher,
        PrinterFormatSetting, Base, _shared_engine_or_none
    )
    if not session.get("logged_in") or not is_store_admin_or_higher():
        return redirect(url_for("pos_app.admin_login", next=request.path))

    s = SessionLocal()
    try:
        sid = current_store_id()
        eng = _shared_engine_or_none()
        if eng:
            try:
                Base.metadata.create_all(bind=eng, tables=[PrinterFormatSetting.__table__])
            except Exception as e:
                logging.warning(f"Could not create PrinterFormatSetting table: {e}")

        setting = s.query(PrinterFormatSetting).filter(
            PrinterFormatSetting.store_id == sid,
            PrinterFormatSetting.printer_name == printer_name
        ).first()

        if not setting:
            setting = PrinterFormatSetting(store_id=sid, printer_name=printer_name)
            s.add(setting)

        setting.print_mode = request.form.get('print_mode', 'kitchen')
        setting.margin_before = int(request.form.get('margin_before', 1))
        setting.margin_after = int(request.form.get('margin_after', 1))
        setting.show_title = 1 if request.form.get('show_title') else 0
        setting.title_text = request.form.get('title_text', 'ご注文内容')
        setting.title_size = int(request.form.get('title_size', 2))
        setting.title_align = request.form.get('title_align', 'center')
        setting.title_bold = 1 if request.form.get('title_bold') else 0
        setting.show_separator = 1 if request.form.get('show_separator') else 0
        setting.show_datetime = 1 if request.form.get('show_datetime') else 0
        setting.datetime_format = request.form.get('datetime_format', 'YYYY/MM/DD HH:mm:ss')
        setting.show_price = 1 if request.form.get('show_price') else 0
        setting.show_new_additional = 1 if request.form.get('show_new_additional') else 0
        setting.kitchen_datetime_format = request.form.get('kitchen_datetime_format', 'HH:mm')
        setting.updated_at = datetime.utcnow()

        s.commit()
        flash(f'プリンタ「{printer_name}」の印刷設定を保存しました', 'success')
        return redirect(url_for('pos_app.admin_printers'))
    except Exception as e:
        s.rollback()
        logging.error(f"Error saving printer format settings: {e}", exc_info=True)
        flash(f'設定の保存に失敗しました: {str(e)}', 'error')
        return redirect(url_for('pos_printer_format.printer_format_settings', printer_name=printer_name))
    finally:
        s.close()
