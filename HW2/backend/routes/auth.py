"""
routes/auth.py
帳號驗證 API：
  1. [POST] /api/login -> 驗證帳號密碼，成功回傳使用者身分 role
"""
from flask import Blueprint, request, jsonify
from database import query

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/login', methods=['POST'])
def login():
    """
    [POST] 登入驗證

    請求 Body (JSON)：
      - user_id  : 帳號（必填）
      - password : 密碼（必填）

    成功：回傳該使用者的 role（'student' / 'admin'）
    失敗：400（缺參數）或 401（帳號或密碼錯誤）
    """
    data = request.get_json(force=True)
    user_id = data.get('user_id')
    password = data.get('password')

    # --- 驗證必要欄位 ---
    if not user_id or not password:
        return jsonify({
            'success': False,
            'message': '缺少必要欄位: user_id, password'
        }), 400

    # --- 查詢使用者 ---
    rows = query(
        'SELECT user_id, role FROM users WHERE user_id = ? AND password = ?',
        (user_id, password)
    )
    if not rows:
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'}), 401

    user = rows[0]

    return jsonify({
        'success': True,
        'message': '登入成功',
        'data': {
            'user_id': user['user_id'],
            'role': user['role']
        }
    })