"""
init_db.py - 資料庫初始化（建立資料表）
"""
from database import get_connection

def init_db():
    """依 Schema 建立四張資料表與索引"""
    conn = get_connection()

    conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            department VARCHAR(50) NOT NULL,
            grade INT DEFAULT 1,
            status VARCHAR(20) DEFAULT '在學'
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            course_id VARCHAR(20) PRIMARY KEY,
            course_name VARCHAR(100) NOT NULL,
            credits INT NOT NULL,
            course_type VARCHAR(20) NOT NULL,
            teacher VARCHAR(50),
            max_capacity INT NOT NULL,
            current_enrolled INT DEFAULT 0
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

    conn.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_student ON course_enrollments(student_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_enrollment_course ON course_enrollments(course_id)')

    conn.commit()
    conn.close()
    print('[OK] 資料庫初始化完成')


def seed_test_data():
    """填充測試資料：必要的學生與課程"""
    from database import query

    # 只有當資料表為空時才填入
    if not query('SELECT 1 FROM students LIMIT 1'):
        conn = get_connection()
        conn.execute(
            "INSERT INTO students (student_id, name, password_hash, department, grade, status) VALUES (?, ?, ?, ?, ?, ?)",
            ('A123456789', '王小明', 'hash', '資工系', 3, '在學')
        )
        conn.commit()
        conn.close()
        print('  [OK] 新增學生: 王小明 (A123456789)')

    if not query('SELECT 1 FROM courses LIMIT 1'):
        conn = get_connection()
        courses = [
            ('CS101', '程式設計', 3, '必修', '王教授', 60),
            ('CS201', '資料結構', 3, '必修', '李教授', 50),
            ('CS301', '資料庫系統', 3, '必修', '陳教授', 45),
            ('CS401', '人工智慧導論', 3, '選修', '林教授', 40),
        ]
        for c in courses:
            conn.execute(
                "INSERT INTO courses (course_id, course_name, credits, course_type, teacher, max_capacity, current_enrolled) VALUES (?, ?, ?, ?, ?, ?, 0)",
                c
            )
        conn.commit()
        conn.close()
        print('  [OK] 新增課程 4 門')


if __name__ == '__main__':
    init_db()
    seed_test_data()
    print(' 初始化與測試資料填充完成')
