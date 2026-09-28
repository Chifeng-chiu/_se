# -*- coding: utf-8 -*-
"""
system.py - 校務系統 (單檔 Flask: 前端 + 後端)
================================================
前端：登入 -> 學生(課表/請假) 或 管理員(審核) (2005 傳統 HTML Table 排版)
後端：Flask + SQLite
  - GET  /                         首頁 (登入畫面)
  - GET  /index.html               同上
  - GET  /enroll.html              線上加退選作業頁
  - POST /api/login                登入 (回傳 role: student/admin)
  - POST /api/leave                學生送出請假單
  - GET  /api/admin/leaves         管理員撈出審核中假單
  - PUT  /api/admin/leaves/<id>    批准或退回

預設帳號：student / 123456 , admin / 123456
啟動：python system.py  ->  開啟 http://localhost:5000
"""
import os
import sqlite3
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'system.db')

INDEX_PAGE = r"""__INDEX_HTML__"""

ENROLL_PAGE = r"""__ENROLL_HTML__"""

LEAVE_TYPES = ('病假', '事假', '公假', '喪假', '其他')
ALLOWED_STATUS = ('已批准', '退回')


# ============================================================
# 資料庫
# ============================================================
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def query(sql, params=()):
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def execute(sql, params=()):
    conn = get_connection()
    cur = conn.execute(sql, params)
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected


def init_db():
    conn = get_connection()

    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id VARCHAR(50) PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'student'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50) NOT NULL
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS leave_requests (
            leave_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id VARCHAR(10) NOT NULL,
            leave_type VARCHAR(20) NOT NULL,
            leave_date VARCHAR(10) NOT NULL,
            reason VARCHAR(500),
            status VARCHAR(20) DEFAULT '審核中'
        )
    ''')

    conn.commit()

    # seed 預設帳號
    if not query('SELECT 1 FROM users LIMIT 1'):
        for uid, pw, role in [('student', '123456', 'student'), ('admin', '123456', 'admin')]:
            execute("INSERT INTO users (user_id, password, role) VALUES (?, ?, ?)",
                    (uid, pw, role))

    if not query('SELECT 1 FROM students LIMIT 1'):
        execute("INSERT INTO students (student_id, name) VALUES (?, ?)",
                ('A123456789', '王小明'))

    conn.close()


app = Flask(__name__)
CORS(app)
init_db()


# ============================================================
# 頁面路由
# ============================================================
@app.route('/')
def home():
    return render_template_string(INDEX_PAGE)


@app.route('/index.html')
def home_alt():
    return render_template_string(INDEX_PAGE)


@app.route('/enroll.html')
def enroll_page():
    return render_template_string(ENROLL_PAGE)


@app.route('/api')
def api_info():
    return jsonify({'name': '校務系統 API', 'version': '1.0.0'})


# ============================================================
# 登入
# ============================================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json(force=True)
    user_id = data.get('user_id')
    password = data.get('password')

    if not user_id or not password:
        return jsonify({'success': False, 'message': '缺少必要欄位: user_id, password'}), 400

    rows = query('SELECT user_id, role FROM users WHERE user_id = ? AND password = ?',
                 (user_id, password))
    if not rows:
        return jsonify({'success': False, 'message': '帳號或密碼錯誤'}), 401

    user = rows[0]
    return jsonify({'success': True, 'message': '登入成功',
                    'data': {'user_id': user['user_id'], 'role': user['role']}})


# ============================================================
# 學生請假
# ============================================================
@app.route('/api/leave', methods=['POST'])
def create_leave():
    data = request.get_json(force=True)
    student_id = data.get('student_id')
    leave_type = data.get('leave_type')
    leave_date = data.get('leave_date')
    reason = data.get('reason')

    if not student_id or not leave_type or not leave_date or not reason:
        return jsonify({'success': False,
                        'message': '缺少必要欄位: student_id, leave_type, leave_date, reason'}), 400

    if leave_type not in LEAVE_TYPES:
        return jsonify({'success': False,
                        'message': f'無效假別，僅允許: {", ".join(LEAVE_TYPES)}'}), 400

    if not query('SELECT 1 FROM students WHERE student_id = ?', (student_id,)):
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO leave_requests (student_id, leave_type, leave_date, reason, status) VALUES (?, ?, ?, ?, '審核中')",
        (student_id, leave_type, leave_date, reason)
    )
    conn.commit()
    leave_id = cur.lastrowid
    conn.close()

    return jsonify({'success': True, 'message': '請假申請已送出，待管理員審核',
                    'data': {'leave_id': leave_id, 'student_id': student_id,
                             'leave_type': leave_type, 'leave_date': leave_date,
                             'reason': reason, 'status': '審核中'}}), 201


# ============================================================
# 管理員審核
# ============================================================
@app.route('/api/admin/leaves', methods=['GET'])
def list_pending_leaves():
    rows = query(
        '''SELECT l.leave_id, l.student_id, s.name AS student_name,
                  l.leave_type, l.leave_date, l.reason, l.status
           FROM leave_requests l
           LEFT JOIN students s ON l.student_id = s.student_id
           WHERE l.status = '審核中'
           ORDER BY l.leave_id DESC'''
    )
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@app.route('/api/admin/leaves/<int:leave_id>', methods=['PUT'])
def review_leave(leave_id):
    data = request.get_json(force=True)
    new_status = data.get('status')

    if new_status not in ALLOWED_STATUS:
        return jsonify({'success': False,
                        'message': f'無效狀態，僅允許: {", ".join(ALLOWED_STATUS)}'}), 400

    rows = query('SELECT * FROM leave_requests WHERE leave_id = ?', (leave_id,))
    if not rows:
        return jsonify({'success': False, 'message': '找不到該請假單'}), 404
    leave = rows[0]

    if leave['status'] != '審核中':
        return jsonify({'success': False, 'message': '該假單已審核完畢，不可重複審核'}), 400

    execute('UPDATE leave_requests SET status = ? WHERE leave_id = ?', (new_status, leave_id))

    return jsonify({'success': True, 'message': f'審核成功，狀態已更新為「{new_status}」',
                    'data': {'leave_id': leave_id, 'student_id': leave['student_id'],
                             'leave_type': leave['leave_type'], 'leave_date': leave['leave_date'],
                             'status': new_status}})


if __name__ == '__main__':
    print('校務系統啟動中: http://localhost:5000')
    app.run(debug=True, port=5000)