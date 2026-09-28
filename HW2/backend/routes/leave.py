"""
routes/leave.py
請假系統 API：
  1. [POST]   /api/leave           -> 提出請假申請
  2. [GET]    /api/leave           -> 查詢個人請假紀錄
  3. [POST]   /api/leave/cancel    -> 撤銷請假申請（僅限待審核）
  4. [POST]   /api/leave/approve   -> 核准請假（管理端審核）
  5. [POST]   /api/leave/reject    -> 駁回請假（管理端審核）
"""
from datetime import datetime
from flask import Blueprint, request, jsonify
from database import query, execute

leave_bp = Blueprint('leave', __name__)

LEAVE_TYPES = ('事假', '病假', '公假', '喪假', '其他')
VALID_STATUS = ('待審核', '已核准', '已駁回', '已撤銷')


@leave_bp.route('/api/leave', methods=['POST'])
def create_leave():
    """
    [POST] 提出請假申請

    請求 Body (JSON)：
      - student_id : 學號（必填）
      - leave_type : 類別（事假/病假/公假/喪假/其他）
      - start_date : 開始日期 YYYY-MM-DD
      - end_date   : 結束日期 YYYY-MM-DD（不可早於開始）
      - periods    : 節次（可選，如「1-4」或「全天」）
      - reason     : 事由（必填）

    送出後狀態為「待審核」，等待管理端核准或駁回。
    """
    data = request.get_json(force=True)
    student_id = (data.get('student_id') or '').strip()
    leave_type = data.get('leave_type') or ''
    start_date = data.get('start_date') or ''
    end_date = data.get('end_date') or ''
    periods = data.get('periods') or ''
    reason = data.get('reason') or ''

    if not student_id:
        return jsonify({'success': False, 'message': '缺少必要欄位: student_id'}), 400
    if leave_type not in LEAVE_TYPES:
        return jsonify({'success': False, 'message': '請選擇有效的請假類別'}), 400
    if not start_date or not end_date:
        return jsonify({'success': False, 'message': '請選擇請假日期'}), 400
    if not reason or not str(reason).strip():
        return jsonify({'success': False, 'message': '請填寫請假事由'}), 400

    # 計算請假天數
    try:
        s = datetime.strptime(start_date, '%Y-%m-%d')
        e = datetime.strptime(end_date, '%Y-%m-%d')
        days = (e - s).days + 1
    except ValueError:
        return jsonify({'success': False, 'message': '日期格式錯誤'}), 400
    if days < 1:
        return jsonify({'success': False, 'message': '結束日期不可早於開始日期'}), 400

    if not query('SELECT 1 FROM students WHERE student_id = ?', (student_id,)):
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    execute(
        '''INSERT INTO leave_requests
           (student_id, leave_type, start_date, end_date, periods, reason, days, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, '待審核')''',
        (student_id, leave_type, start_date, end_date, periods, str(reason).strip(), days)
    )
    return jsonify({'success': True, 'message': '請假申請已送出，等待審核'}), 201


@leave_bp.route('/api/leave', methods=['GET'])
def list_leaves():
    """
    [GET] 查詢個人請假紀錄

    參數（Query string）：
      - student_id : 學號（必填）
      - status     : 狀態過濾（可選：待審核/已核准/已駁回/已撤銷）

    依申請時間由新到舊排序。
    """
    student_id = request.args.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'message': '缺少必要參數: student_id'}), 400

    sql = 'SELECT * FROM leave_requests WHERE student_id = ?'
    params = [student_id]
    status = request.args.get('status')
    if status and status in VALID_STATUS:
        sql += ' AND status = ?'
        params.append(status)

    sql += ' ORDER BY created_at DESC, leave_id DESC'
    rows = query(sql, tuple(params))
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@leave_bp.route('/api/leave/cancel', methods=['POST'])
def cancel_leave():
    """
    [POST] 撤銷請假申請（僅限「待審核」狀態）
    """
    data = request.get_json(force=True)
    leave_id = data.get('leave_id')
    student_id = data.get('student_id')

    if not leave_id or not student_id:
        return jsonify({'success': False, 'message': '缺少必要欄位: leave_id, student_id'}), 400

    rows = query(
        'SELECT * FROM leave_requests WHERE leave_id = ? AND student_id = ?',
        (leave_id, student_id)
    )
    if not rows:
        return jsonify({'success': False, 'message': '找不到該請假紀錄'}), 404
    if rows[0]['status'] != '待審核':
        return jsonify({'success': False, 'message': '僅「待審核」的申請可以撤銷'}), 400

    execute("UPDATE leave_requests SET status = '已撤銷' WHERE leave_id = ?", (leave_id,))
    return jsonify({'success': True, 'message': '請假申請已撤銷'})