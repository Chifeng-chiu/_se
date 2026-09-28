"""
routes/admin.py
管理後台 API：
  1. [POST] /api/admin/login       -> 管理者登入（回傳 Token）
  2. [POST] /api/admin/logout      -> 登出（銷毀 Token）
  3. [GET]  /api/admin/leaves      -> 查詢所有請假申請（可依狀態過濾）
  4. [GET]  /admin                 -> 管理後台網頁（登入後核准/駁回請假）
"""
import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, render_template
from database import query, execute
from routes.auth import hash_password
from routes.leave import VALID_STATUS

admin_bp = Blueprint('admin', __name__)

# 登入後的有效 Token（記憶體存放，伺服器重啟後需重新登入）
ADMIN_TOKENS = {}


def generate_token(username):
    token = secrets.token_hex(16)
    ADMIN_TOKENS[token] = username
    return token


def get_token():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[len('Bearer '):]
    return None


def admin_required(f):
    """要求請求必須攜帶有效管理員 Token"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_token()
        if not token or token not in ADMIN_TOKENS:
            return jsonify({'success': False, 'message': '未登入或登入已失效'}), 401
        return f(*args, **kwargs)
    return wrapper


@admin_bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    """
    [POST] 管理者登入

    請求 Body (JSON)：
      - username : 管理員帳號
      - password : 密碼
    """
    data = request.get_json(force=True)
    username = (data.get('username') or '').strip()
    password = (data.get('password') or '')

    if not username or not password:
        return jsonify({'success': False, 'message': '請輸入帳號與密碼'}), 400

    rows = query('SELECT * FROM admins WHERE username = ?', (username,))
    if not rows or rows[0]['password_hash'] != hash_password(password):
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'}), 401

    token = generate_token(username)
    return jsonify({
        'success': True,
        'data': {'username': username, 'display_name': rows[0]['display_name'], 'token': token}
    })


@admin_bp.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    """登出並銷毀 Token"""
    token = get_token()
    if token and token in ADMIN_TOKENS:
        del ADMIN_TOKENS[token]
    return jsonify({'success': True, 'message': '已登出'})


@admin_bp.route('/api/admin/leaves', methods=['GET'])
@admin_required
def admin_leaves():
    """
    [GET] 查詢所有請假申請

    參數（Query string）：
      - status : 狀態過濾（可選：待審核/已核准/已駁回/已撤銷）

    回傳：所有請假申請，並附上學生姓名。
    """
    sql = """SELECT l.*, s.name AS student_name
             FROM leave_requests l
             JOIN students s ON l.student_id = s.student_id"""
    params = []

    status = request.args.get('status')
    if status and status in VALID_STATUS:
        sql += ' WHERE l.status = ?'
        params.append(status)

    sql += ' ORDER BY l.created_at DESC, l.leave_id DESC'
    rows = query(sql, tuple(params))
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@admin_bp.route('/admin', methods=['GET'])
def admin_page():
    """管理後台網頁"""
    return render_template('admin.html')


def _review(new_status):
    """管理端審核：核准 / 駁回"""
    data = request.get_json(force=True)
    leave_id = data.get('leave_id')

    if not leave_id:
        return jsonify({'success': False, 'message': '缺少必要欄位: leave_id'}), 400

    rows = query('SELECT * FROM leave_requests WHERE leave_id = ?', (leave_id,))
    if not rows:
        return jsonify({'success': False, 'message': '找不到該請假紀錄'}), 404
    if rows[0]['status'] != '待審核':
        return jsonify({'success': False, 'message': '僅「待審核」的申請可以變更狀態'}), 400

    execute('UPDATE leave_requests SET status = ? WHERE leave_id = ?', (new_status, leave_id))
    label = '核准' if new_status == '已核准' else '駁回'
    return jsonify({'success': True, 'message': f'已{label}該請假申請'})


@admin_bp.route('/api/leave/approve', methods=['POST'])
@admin_required
def approve_leave():
    return _review('已核准')


@admin_bp.route('/api/leave/reject', methods=['POST'])
@admin_required
def reject_leave():
    return _review('已駁回')