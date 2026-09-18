"""
routes/schedule.py
包含以下核心 API：
  1. [GET]    /api/schedule          -> 查詢個人課表 (已選上的課程)
  2. [POST]   /api/enroll            -> 加選課程 (含重複選課與名額檢查)
  3. [DELETE] /api/enroll            -> 退選課程 (軟刪除)
"""
from flask import Blueprint, request, jsonify
from database import query, execute

schedule_bp = Blueprint('schedule', __name__)


@schedule_bp.route('/api/schedule', methods=['GET'])
def get_schedule():
    """
    [GET] 查詢個人課表

    參數（Query string）：
      - student_id : 學生學號（必填）
      - semester   : 學期（必填）

    回傳：該名學生該學期「已選上」的課程清單，
          僅包含選課成功 (status = '已選上') 的課程，
          並附上課程名稱、學分與授課教師。
    """
    # --- 取得並驗證參數 ---
    student_id = request.args.get('student_id')
    semester = request.args.get('semester')

    # 缺少必要參數時回傳 400
    if not student_id or not semester:
        return jsonify({'success': False, 'message': '缺少必要參數: student_id, semester'}), 400

    # --- 確認學生存在 ---
    student = query('SELECT * FROM students WHERE student_id = ?', (student_id,))
    if not student:
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    # --- 查詢個人課表 ---
    # 以 course_enrollments 為核心，JOIN courses 取得課程資訊
    # 只查 status = '已選上'（排除退選/候補中的記錄）
    sql = """
        SELECT
            e.course_id,
            c.course_name AS course_name,   -- 課程名稱
            c.credits    AS credits,        -- 學分
            c.teacher    AS teacher,        -- 授課教師
            e.semester,
            e.status
        FROM course_enrollments e
        JOIN courses c ON e.course_id = c.course_id
        WHERE e.student_id = ?          -- 指定學生
          AND e.semester = ?            -- 指定學期
          AND e.status = '已選上'         -- 只取已選上的課
    """
    courses = query(sql, (student_id, semester))

    return jsonify({
        'success': True,
        'data': courses,
        'total': len(courses)
    })


@schedule_bp.route('/api/enroll', methods=['POST'])
def enroll_course():
    """
    [POST] 加選課程

    請求 Body (JSON)：
      - student_id : 學生學號
      - course_id  : 課程代號
      - semester   : 學期

    加選前的檢查邏輯：
      (1) 是否已選過該課（同一學生 + 同一課程 + 同一學期）
      (2) 課程名額是否已滿（current_enrolled >= max_capacity）

    加選成功後：
      1. 在 course_enrollments 新增一筆 status = '已選上' 的記錄
      2. 將 courses 表該課程的 current_enrolled 數量 + 1
    """
    # --- 取得請求資料 ---
    data = request.get_json(force=True)
    student_id = data.get('student_id')
    course_id = data.get('course_id')
    semester = data.get('semester')

    # 驗證必要欄位
    if not student_id or not course_id or not semester:
        return jsonify({'success': False, 'message': '缺少必要欄位: student_id, course_id, semester'}), 400

    # --- 檢查 (0): 學生與課程是否存在 ---
    if not query('SELECT 1 FROM students WHERE student_id = ?', (student_id,)):
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    course_row = query('SELECT * FROM courses WHERE course_id = ?', (course_id,))
    if not course_row:
        return jsonify({'success': False, 'message': '找不到該課程'}), 404
    course = course_row[0]

    # --- 檢查 (1): 是否已選過該課 ---
    # 同一學生在相同學期重複加選同一門課，直接拒絕
    duplicate = query(
        'SELECT 1 FROM course_enrollments WHERE student_id = ? AND course_id = ? AND semester = ?',
        (student_id, course_id, semester)
    )
    if duplicate:
        return jsonify({'success': False, 'message': '該學期已選過此課程，無法重複加選'}), 400

    # --- 檢查 (2): 名額是否已滿 ---
    if course['current_enrolled'] >= course['max_capacity']:
        return jsonify({'success': False, 'message': '課程名額已滿'}), 400

    # --- 加選：新增選課記錄 ---
    execute(
        '''INSERT INTO course_enrollments (student_id, course_id, semester, status)
           VALUES (?, ?, ?, '已選上')''',
        (student_id, course_id, semester)
    )

    # --- 加選：課程已選人數 +1 ---
    execute(
        'UPDATE courses SET current_enrolled = current_enrolled + 1 WHERE course_id = ?',
        (course_id,)
    )

    return jsonify({
        'success': True,
        'message': '加選成功',
        'data': {
            'student_id': student_id,
            'course_id': course_id,
            'semester': semester,
            'course_name': course['course_name'],
            'teacher': course['teacher'],
            'current_enrolled': course['current_enrolled'] + 1
        }
    }), 201


@schedule_bp.route('/api/enroll', methods=['DELETE'])
def drop_course():
    """
    [DELETE] 退選課程

    請求 Body (JSON)：
      - student_id : 學生學號
      - course_id  : 課程代號
      - semester   : 學期

    邏輯：
      1. 確認該學生在此學期「確實已選上」此課程
      2. 更新該筆 course_enrollments 的 status 為「退選」
      3. 將 courses 的 current_enrolled 數量 -1

    防呆設計：
      - 該學期未找到選課記錄 -> 400「找不到該選課記錄」
      - 該筆記錄已是「退選」狀態 -> 400「該課程已退選，不可重複退選」
      採用「軟刪除」方式保留歷史紀錄，不實際刪除資料列。
    """
    # --- 取得請求資料 ---
    data = request.get_json(force=True)
    student_id = data.get('student_id')
    course_id = data.get('course_id')
    semester = data.get('semester')

    # 驗證必要欄位
    if not student_id or not course_id or not semester:
        return jsonify({'success': False, 'message': '缺少必要欄位: student_id, course_id, semester'}), 400

    # --- 防呆 (1): 確認該生在此學期是否曾選過此課 ---
    enrollment_rows = query(
        'SELECT * FROM course_enrollments WHERE student_id = ? AND course_id = ? AND semester = ?',
        (student_id, course_id, semester)
    )
    if not enrollment_rows:
        return jsonify({'success': False, 'message': '找不到該選課記錄，無法退選'}), 400

    enrollment = enrollment_rows[0]

    # --- 防呆 (2): 確認該筆記錄確實是「已選上」狀態 ---
    if enrollment['status'] != '已選上':
        return jsonify({'success': False, 'message': '該課程已退選或狀態異常，不可重複退選'}), 400

    # --- 執行退選：將 status 更新為「退選」（軟刪除，保留歷史）---
    execute(
        '''UPDATE course_enrollments SET status = '退選'
           WHERE enrollment_id = ?''',
        (enrollment['enrollment_id'],)
    )

    # --- 課程已選人數 -1 (避免扣到負數) ---
    execute(
        '''UPDATE courses SET current_enrolled = current_enrolled - 1
           WHERE course_id = ? AND current_enrolled > 0''',
        (course_id,)
    )

    return jsonify({
        'success': True,
        'message': '退選成功',
        'data': {
            'student_id': student_id,
            'course_id': course_id,
            'semester': semester,
            'enrollment_id': enrollment['enrollment_id'],
            'status': '退選'
        }
    })