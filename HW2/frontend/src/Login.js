/**
 * Login.js - 校務系統登入頁
 * 採用傳統校務系統登入介面風格
 */
import React, { useState } from 'react';
import { login } from './services/api';

export default function Login({ onLogin }) {
  const [studentId, setStudentId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!studentId || !password) {
      setError('請輸入學號與密碼');
      return;
    }
    setLoading(true);
    try {
      const res = await login(studentId, password);
      onLogin(res.data.data);
    } catch (err) {
      const message = err.response?.data?.message || '登入失敗，請稍後再試';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-title">國立金門大學</div>
        <div className="login-subtitle">National Quemoy University</div>
        <div className="login-panel">
          <div className="login-head">校務資訊系統</div>
          <form onSubmit={handleSubmit}>
            <table className="login-table">
              <tbody>
                <tr>
                  <td className="login-label">帳號（學號）</td>
                  <td>
                    <input
                      type="text"
                      value={studentId}
                      onChange={(e) => setStudentId(e.target.value)}
                      autoFocus
                    />
                  </td>
                </tr>
                <tr>
                  <td className="login-label">密　碼</td>
                  <td>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </td>
                </tr>
              </tbody>
            </table>
            {error && <div className="login-error">{error}</div>}
            <div className="login-buttons">
              <input type="submit" value="登入" className="retro-btn black login-submit" />
              <button
                type="button"
                className="retro-btn black login-submit"
                onClick={() => { setStudentId(''); setPassword(''); setError(''); }}
              >
                清除
              </button>
            </div>
          </form>
          <div className="login-hint">測試帳號：A123456789 / 1234</div>
        </div>
      </div>
    </div>
  );
}