"""
init_db.py - 資料庫初始化（建立資料表 + 種子資料）
"""
import hashlib
from database import get_connection, query


def hash_password(password):
    """密碼以 SHA-256 雜湊儲存，不存明碼"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def init_db():
    """依 Schema 建立表格與索引"""
    conn = get_connection()

    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            department VARCHAR(50) NOT NULL,
            grade INT DEFAULT 1,
            status VARCHAR(20) DEFAULT '在學',
            class_name VARCHAR(50)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            course_id VARCHAR(20) PRIMARY KEY,
            course_name VARCHAR(100) NOT NULL,
            name_en VARCHAR(150),
            credits INT NOT NULL,
            course_type VARCHAR(20) NOT NULL,
            teacher VARCHAR(50),
            max_capacity INT NOT NULL,
            current_enrolled INT DEFAULT 0,
            class_group VARCHAR(30),
            group_no VARCHAR(5),
            time VARCHAR(30),
            room VARCHAR(50)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS course_enrollments (
            enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id VARCHAR(10) NOT NULL,
            course_id VARCHAR(20) NOT NULL,
            semester VARCHAR(10) NOT NULL,
            status VARCHAR(20) DEFAULT '已選上',
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (course_id) REFERENCES courses(course_id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS grades (
            grade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id VARCHAR(10) NOT NULL,
            course_id VARCHAR(20) NOT NULL,
            semester VARCHAR(10) NOT NULL,
            final_score DECIMAL(5,2),
            FOREIGN KEY (student_id) REFERENCES students(student_id),
            FOREIGN KEY (course_id) REFERENCES courses(course_id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS leave_requests (
            leave_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id VARCHAR(10) NOT NULL,
            leave_type VARCHAR(20) NOT NULL,
            start_date VARCHAR(10) NOT NULL,
            end_date VARCHAR(10) NOT NULL,
            periods VARCHAR(30),
            reason VARCHAR(200),
            days INT DEFAULT 1,
            status VARCHAR(10) DEFAULT '待審核',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students(student_id)
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(50)
        )
    ''')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_student ON course_enrollments(student_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_course ON course_enrollments(course_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_grades_student ON grades(student_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_leave_student ON leave_requests(student_id)')

    conn.commit()
    conn.close()
    print('[OK] 資料庫初始化完成')


def seed_test_data():
    """填充測試資料：學生、課程、選課與成績"""
    if not query('SELECT 1 FROM students LIMIT 1'):
        conn = get_connection()
        students = [
            # school_id, 姓名,            密碼(1234), 科系,     年級, 狀態, 班級
            ('A123456789', '王小明', hash_password('1234'), '資訊工程學系', 3, '在學', '資工二'),
            ('A123456788', '陳小美', hash_password('1234'), '資訊工程學系', 2, '在學', '資工二'),
        ]
        for s in students:
            conn.execute(
                "INSERT INTO students (student_id, name, password_hash, department, grade, status, class_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", s
            )
        conn.commit()
        conn.close()
        print('  [OK] 新增學生 2 名 (預設密碼: 1234)')

    if not query('SELECT 1 FROM courses LIMIT 1'):
        conn = get_connection()
        courses = [
            # id,   名稱,                  英文名,                                                                  學分, 必選修, 教師,         名額, 班級,       分組, 上課時間, 教室
            ('0890', '資訊科技於金門社區長者之運用', 'The Application of Information Technology for the Elderly in Kinmen Communities', 2, '必修', '黃玉苹,趙于翔', 55, '日大學通識', '01', '(四)5-6', 'D203護理系普通教室'),
            ('0156', '作業系統',               'Operating System',                  3, '必修', '馮玄明',   50, '資工三', '01', '(一)2-4', 'I101圖資電腦教室'),
            ('0148', '計算機結構',             'Computer Architecture',             3, '必修', '陳鍾誠',   50, '資工二', '01', '(四)2-4', 'E320多媒體實驗室'),
            ('0149', '資料庫系統管理',          'Database System and Management',    3, '必修', '馮玄明',   50, '資工二', '01', '(一)5-7', 'I101圖資電腦教室'),
            ('0150', 'TCP/IP協定',            'TCP/IP Protocol Suite',              3, '選修', '柯志亨',   45, '資工二', '01', '(三)2-4', 'E321電腦網路實驗室'),
            ('0151', '電路學',                 'Circuits Studies',                  3, '必修', '陳正德',   50, '資工二', '01', '(二)2-4', 'E202教室(理工大樓)'),
            ('0152', '現代程式語言',          'Modern Programming Language',       3, '選修', '李錫捷',   45, '資工二', '01', '(二)5-7', 'E320多媒體實驗室'),
            ('0153', '現代軟體工程',          'Modern Software Engineering',        3, '選修', '陳鍾誠',   40, '資工二', '01', '(五)2-4', 'E320多媒體實驗室'),
        ]
        for c in courses:
            conn.execute(
                "INSERT INTO courses (course_id, course_name, name_en, credits, course_type, teacher, "
                "max_capacity, current_enrolled, class_group, group_no, time, room) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)", c
            )
        conn.commit()
        conn.close()
        print('  [OK] 新增課程 8 門')

    # 管理者帳號（後台登入用）
    if not query('SELECT 1 FROM admins LIMIT 1'):
        conn = get_connection()
        conn.execute(
            "INSERT INTO admins (username, password_hash, display_name) VALUES (?, ?, ?)",
            ('admin', hash_password('admin123'), '系統管理者')
        )
        conn.commit()
        conn.close()
        print('  [OK] 新增管理員 (admin / admin123)')

    # 王小明已選 2 門課（113-1）
    if not query("SELECT 1 FROM course_enrollments WHERE student_id = 'A123456789' LIMIT 1"):
        conn = get_connection()
        conn.execute(
            "INSERT INTO course_enrollments (student_id, course_id, semester, status) VALUES (?, ?, ?, '已選上')",
            ('A123456789', '0148', '113-1')
        )
        conn.execute(
            "INSERT INTO course_enrollments (student_id, course_id, semester, status) VALUES (?, ?, ?, '已選上')",
            ('A123456789', '0153', '113-1')
        )
        conn.execute("UPDATE courses SET current_enrolled = current_enrolled + 1 WHERE course_id IN ('0148', '0153')")
        conn.commit()
        conn.close()
        print('  [OK] 新增選課: 王小明 已選 0148, 0153')

    # 王小明歷年成績（112-2）
    if not query("SELECT 1 FROM grades WHERE student_id = 'A123456789' LIMIT 1"):
        conn = get_connection()
        grades = [
            ('A123456789', '0156', '112-2', 85),
            ('A123456789', '0148', '112-2', 90),
            ('A123456789', '0149', '112-2', 88),
        ]
        for g in grades:
            conn.execute(
                "INSERT INTO grades (student_id, course_id, semester, final_score) VALUES (?, ?, ?, ?)", g
            )
        conn.commit()
        conn.close()
        print('  [OK] 新增成績: 王小明 112-2 共 3 筆')


if __name__ == '__main__':
    init_db()
    seed_test_data()
    print(' 初始化與測試資料填充完成')