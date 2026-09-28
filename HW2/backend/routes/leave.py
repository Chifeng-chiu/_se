"""
routes/leave.py
包含學生請假與管理員審核的核心 API：
  1. [POST] /api/leave                -> 學生送出請假單
  2. [GET]  /api/admin/leaves          -> 管理員撈出所有「審核中」的假單
  3. [PUT]  /api/admin/leaves/<id>      -> 管理員審核：更新為「已批准」或「退回」
"""
from flask import Blueprint, request, jsonify
from database import query, execute, get_connection

leave_bp = Blueprint('leave', __name__)

# 允許的假別
LEAVE_TYPES = ('病假', '事假', '公假', '喪假', '其他')

# 管理員可設定的狀態（僅這兩種）
ALLOWED_STATUS = ('已批准', '退回')


@leave_bp.route('/api/leave', methods=['POST'])
def create_leave():
    """
    [POST] 學生送出請假單

    請求 Body (JSON)：
      - student_id : 學號（必填）
      - leave_type : 假別（必填，如：病假/事假/公假）
      - leave_date : 請假日期（必填，格式 YYYY-MM-DD）
      - reason     : 請假事由（必填）

    寫入後狀態預設為「審核中」。
    """
    data = request.get_json(force=True)
    student_id = data.get('student_id')
    leave_type = data.get('leave_type')
    leave_date = data.get('leave_date')
    reason = data.get('reason')

    # --- 驗證必要欄位 ---
    if not student_id or not leave_type or not leave_date or not reason:
        return jsonify({
            'success': False,
            'message': '缺少必要欄位: student_id, leave_type, leave_date, reason'
        }), 400

    # --- 驗證假別 ---
    if leave_type not in LEAVE_TYPES:
        return jsonify({
            'success': False,
            'message': f'無效假別，僅允許: {", ".join(LEAVE_TYPES)}'
        }), 400

    # --- 確認學生存在 ---
    if not query('SELECT 1 FROM students WHERE student_id = ?', (student_id,)):
        return jsonify({'success': False, 'message': '找不到該學生'}), 404

    # --- 寫入資料庫 (取得自動產生的 leave_id) ---
    conn = get_connection()
    cursor = conn.execute(
        '''INSERT INTO leave_requests (student_id, leave_type, leave_date, reason, status)
           VALUES (?, ?, ?, ?, '審核中')''',
        (student_id, leave_type, leave_date, reason)
    )
    conn.commit()
    leave_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'success': True,
        'message': '請假申請已送出，待管理員審核',
        'data': {
            'leave_id': leave_id,
            'student_id': student_id,
            'leave_type': leave_type,
            'leave_date': leave_date,
            'reason': reason,
            'status': '審核中'
        }
    }), 201


@leave_bp.route('/api/admin/leaves', methods=['GET'])
def list_pending_leaves():
    """
    [GET] 管理員撈出所有「審核中」的假單
    回傳清單依請假單號遞減排序（新的在前）。
    """
    rows = query(
        '''SELECT l.leave_id, l.student_id, s.name AS student_name,
                  l.leave_type, l.leave_date, l.reason, l.status
           FROM leave_requests l
           JOIN students s ON l.student_id = s.student_id
           WHERE l.status = '審核中'
           ORDER BY l.leave_id DESC'''
    )

    return jsonify({
        'success': True,
        'data': rows,
        'total': len(rows)
    })


@leave_bp.route('/api/admin/leaves/<int:leave_id>', methods=['PUT'])
def review_leave(leave_id):
    """
    [PUT] 管理員審核假單

    請求 Body (JSON)：
      - status : '已批准' 或 '退回'（必填）

    防呆：
      - 不存在的假單 -> 404
      - 假單已被審核過 -> 400（不可重複審核）
    """
    data = request.get_json(force=True)
    new_status = data.get('status')

    # --- 驗證狀態參數 ---
    if new_status not in ALLOWED_STATUS:
        return jsonify({
            'success': False,
            'message': f'無效狀態，僅允許: {", ".join(ALLOWED_STATUS)}'
        }), 400

    # --- 確認假單存在 ---
    rows = query(
        'SELECT * FROM leave_requests WHERE leave_id = ?',
        (leave_id,)
    )
    if not rows:
        return jsonify({'success': False, 'message': '找不到該請假單'}), 404
    leave = rows[0]

    # --- 防呆: 已審核完畢不可重複審核 ---
    if leave['status'] != '審核中':
        return jsonify({
            'success': False,
            'message': '該假單已審核完畢，不可重複審核'
        }), 400

    # --- 更新狀態 ---
    execute(
        'UPDATE leave_requests SET status = ? WHERE leave_id = ?',
        (new_status, leave_id)
    )

    return jsonify({
        'success': True,
        'message': f'審核成功，狀態已更新為「{new_status}」',
        'data': {
            'leave_id': leave_id,
            'student_id': leave['student_id'],
            'leave_type': leave['leave_type'],
            'leave_date': leave['leave_date'],
            'status': new_status
        }
    })