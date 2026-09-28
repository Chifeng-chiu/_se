"""
routes/grades.py
包含以下 API：
  1. [GET] /api/grades -> 查詢學生歷年成績
"""
from flask import Blueprint, request, jsonify
from database import query

grades_bp = Blueprint('grades', __name__)


@grades_bp.route('/api/grades', methods=['GET'])
def get_grades():
    """
    [GET] 查詢學生成績

    參數（Query string）：
      - student_id : 學生學號（必填）
      - semester   : 學期（可選；過濾指定學期）

    回傳：成績清單（含課程名稱、學期與分數），依學期由新到舊排序。
    """
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'message': '缺少必要參數: student_id'}), 400

    semester = request.args.get('semester')

    sql = """
        SELECT g.course_id, c.course_name AS course_name, g.semester, g.final_score
        FROM grades g
        JOIN courses c ON g.course_id = c.course_id
        WHERE g.student_id = ?
    """
    params = [student_id]
    if semester:
        sql += ' AND g.semester = ?'
        params.append(semester)
    sql += ' ORDER BY g.semester DESC'

    rows = query(sql, tuple(params))
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})