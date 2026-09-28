"""
app.py - Flask 應用程式入口
"""
from flask import Flask, jsonify
from flask_cors import CORS
from init_db import init_db, seed_test_data
from routes.schedule import schedule_bp
from routes.auth import auth_bp
from routes.courses import courses_bp
from routes.grades import grades_bp
from routes.leave import leave_bp
from routes.admin import admin_bp


def create_app():
    app = Flask(__name__)
    CORS(app)                      # 允許前端跨域存取

    init_db()                      # 啟動時自動建表
    seed_test_data()               # 資料表為空時自動填充測試資料

    # 註冊各路線藍圖
    app.register_blueprint(schedule_bp)   # 課表 / 加選 / 退選
    app.register_blueprint(auth_bp)       # 登入 / 修改密碼
    app.register_blueprint(courses_bp)    # 課程總表
    app.register_blueprint(grades_bp)     # 成績查詢
    app.register_blueprint(leave_bp)      # 請假系統
    app.register_blueprint(admin_bp)      # 管理後台（請假審核）

    @app.route('/api', methods=['GET'])
    def api_info():
        return jsonify({
            'name': '大學校務資訊系統 API',
            'version': '1.0.0',
            'endpoints': {
                'login':           'POST   /api/login',
                'change-password': 'POST   /api/change-password',
                'courses':         'GET    /api/courses?student_id=xxx&semester=xxx',
                'schedule':        'GET    /api/schedule?student_id=xxx&semester=xxx',
                'enroll':          'POST   /api/enroll',
                'drop':            'DELETE /api/enroll',
                'grades':          'GET    /api/grades?student_id=xxx',
                'leave':           'POST/GET /api/leave',
                'leave-cancel':    'POST   /api/leave/cancel',
                'leave-review':    'POST   /api/leave/approve | /api/leave/reject',
                'admin-login':     'POST   /api/admin/login',
                'admin-leaves':    'GET    /api/admin/leaves?status=待審核',
                'admin-page':      'GET    /admin'
            }
        })

    return app


if __name__ == '__main__':
    app = create_app()
    print('大學校務資訊系統啟動中...')
    app.run(debug=True)