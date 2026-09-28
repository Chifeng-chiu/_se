"""
app.py - Flask 應用程式入口
"""
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from init_db import init_db
from routes.schedule import schedule_bp
from routes.leave import leave_bp
from routes.auth import auth_bp

def create_app():
    app = Flask(__name__)
    CORS(app)                      # 允許前端跨域存取

    init_db()                      # 啟動時自動建表

    app.register_blueprint(schedule_bp)   # 註冊課表/加選/退選路由

    app.register_blueprint(leave_bp)      # 註冊學生請假 / 管理員審核路由

    app.register_blueprint(auth_bp)       # 註冊登入驗證路由

    @app.route('/', methods=['GET'])
    def home():
        return render_template('index.html')

    @app.route('/index.html', methods=['GET'])
    def home_alt():
        return render_template('index.html')

    @app.route('/enroll.html', methods=['GET'])
    def enroll_page():
        return render_template('enroll.html')

    @app.route('/api', methods=['GET'])
    def api_info():
        return jsonify({
            'name': '大學校務資訊系統 API',
            'version': '1.0.0',
            'endpoints': {
                'schedule':  'GET    /api/schedule?student_id=xxx&semester=xxx',
                'enroll':    'POST   /api/enroll',
                'drop':      'DELETE /api/enroll'
            }
        })

    return app

if __name__ == '__main__':
    app = create_app()
    print('🚀 大學校務資訊系統啟動中...')
    app.run(debug=True)