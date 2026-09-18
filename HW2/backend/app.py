"""
app.py - Flask 應用程式入口
"""
from flask import Flask, jsonify
from flask_cors import CORS
from init_db import init_db
from routes.schedule import schedule_bp

def create_app():
    app = Flask(__name__)
    CORS(app)                      # 允許前端跨域存取

    init_db()                      # 啟動時自動建表

    app.register_blueprint(schedule_bp)   # 註冊課表/加選/退選路由

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