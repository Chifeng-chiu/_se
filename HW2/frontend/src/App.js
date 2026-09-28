/**
 * App.js - 應用程式入口元件
 * 未登入時顯示登入頁，登入後進入校務系統儀表板
 */
import React, { useState } from 'react';
import Login from './Login';
import StudentDashboard from './StudentDashboard';

function App() {
  const [student, setStudent] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('nqu-student') || 'null');
    } catch {
      return null;
    }
  });

  const handleLogin = (studentData) => {
    localStorage.setItem('nqu-student', JSON.stringify(studentData));
    setStudent(studentData);
  };

  const handleLogout = () => {
    localStorage.removeItem('nqu-student');
    setStudent(null);
  };

  return (
    <div className="App">
      {student ? (
        <StudentDashboard student={student} onLogout={handleLogout} />
      ) : (
        <Login onLogin={handleLogin} />
      )}
    </div>
  );
}

export default App;