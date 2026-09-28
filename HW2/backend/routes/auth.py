"""
routes/auth.py
包含以下 API：
  1. [POST] /api/login           -> 學生登入（學號 + 密碼）
  2. [POST] /api/change-password -> 修改密碼
"""
import hashlib
from flask import Blueprint, request, jsonify
from config import Config
from database import query, execute

auth_bp = Blueprint('auth', __name__)


def hash_password(password):
    """以 SHA-256 產生密碼雜湊（與 init_db seed 一致）"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


@auth_bp.route('/api/login', methods=['POST'])
def login():
    """
    [POST] 學生登入

    請求 Body (JSON)：
      - student_id : 學號
      - password   : 密碼

    成功回傳學生基本資料與目前學期；失敗統一回傳 401，避免暴露「學號存在」。
    """
    data = request.get_json(force=True)
    student_id = (data.get('student_id') or '').strip()
    password = data.get('password') or ''

    if not student_id or not password:
        return jsonify({'success': False, 'message': '請輸入學號與密碼'}), 400

    rows = query('SELECT * FROM students WHERE student_id = ?', (student_id,))
    if not rows or rows[0]['password_hash'] != hash_password(password):
        return jsonify({'success': False, 'message': '學號或密碼錯誤'}), 401

    student = rows[0]
    return jsonify({
        'success': True,
        'data': {
            'student_id': student['student_id'],
            'name': student['name'],
            'department': student['department'],
            'class_name': student['class_name'],
            'grade': student['grade'],
            'status': student['status'],
            'semester': Config.CURRENT_SEMESTER,
        }
    })


@auth_bp.route('/api/change-password', methods=['POST'])
def change_password():
    """
    [POST] 修改密碼

    請求 Body (JSON)：
      - student_id    : 學號
      - old_password  : 舊密碼
      - new_password  : 新密碼（至少 4 碼）
    """
    data = request.get_json(force=True)
    student_id = (data.get('student_id') or '').strip()
    old_password = data.get('old_password') or ''
    new_password = data.get('new_password') or ''

    if not student_id or not old_password or not new_password:
        return jsonify({'success': False, 'message': '請完整填寫欄位'}), 400

    if len(new_password) < 4:
        return jsonify({'success': False, 'message': '新密碼至少需要 4 個字元'}), 400

    rows = query('SELECT * FROM students WHERE student_id = ?', (student_id,))
    if not rows:
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    if rows[0]['password_hash'] != hash_password(old_password):
        return jsonify({'success': False, 'message': '舊密碼錯誤'}), 400

    execute(
        'UPDATE students SET password_hash = ? WHERE student_id = ?',
        (hash_password(new_password), student_id)
    )
    return jsonify({'success': True, 'message': '密碼修改成功'})


if __name__ == '__main__':
    # 方便在 CLI 直接測試雜湊值
    print(hash_password('1234'))