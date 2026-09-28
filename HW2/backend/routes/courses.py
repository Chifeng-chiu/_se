"""
routes/courses.py
包含以下 API：
  1. [GET] /api/courses -> 課程總表（含該生已選標記與剩餘名額）
"""
from flask import Blueprint, request, jsonify
from config import Config
from database import query

courses_bp = Blueprint('courses', __name__)


@courses_bp.route('/api/courses', methods=['GET'])
def list_courses():
    """
    [GET] 查詢課程總表

    參數（Query string）：
      - student_id : 學生學號（可選；提供時會標記該生「已選上」的課程）
      - semester   : 學期（可選；預設目前學期）

    回傳：所有課程，附上 enrolled（該生是否已選）與 remaining（剩餘名額）。
    """
    student_id = request.args.get('student_id')
    semester = request.args.get('semester') or Config.CURRENT_SEMESTER

    courses = query('SELECT * FROM courses ORDER BY course_id')

    enrolled = set()
    if student_id:
        rows = query(
            "SELECT course_id FROM course_enrollments "
            "WHERE student_id = ? AND semester = ? AND status = '已選上'",
            (student_id, semester)
        )
        enrolled = {row['course_id'] for row in rows}

    data = [{
        **course,
        'enrolled': course['course_id'] in enrolled,
        'remaining': course['max_capacity'] - course['current_enrolled'],
    } for course in courses]

    return jsonify({'success': True, 'data': data, 'total': len(data)})