const express = require('express');
const { Pool } = require('pg');

const app = express();
app.use(express.json());

const pool = new Pool({
  host: process.env.DB_HOST || 'db',
  user: process.env.DB_USER || 'myuser',
  password: process.env.DB_PASSWORD || 'mypassword',
  database: process.env.DB_NAME || 'mydb',
  port: process.env.DB_PORT || 5432,
});

// 初始化資料表
async function initDB() {
  try {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
    `);
    const count = await pool.query('SELECT COUNT(*) FROM messages');
    if (parseInt(count.rows[0].count) === 0) {
      await pool.query("INSERT INTO messages (content) VALUES ('Hello Docker! 這是第一筆來自 PostgreSQL 的預設資料。')");
    }
    console.log('Database initialized successfully');
  } catch (err) {
    console.error('Database initialization error:', err);
  }
}
initDB();

// 健康檢查與系統資訊 API
app.get('/api/status', async (req, res) => {
  try {
    const dbRes = await pool.query('SELECT version(), current_timestamp;');
    res.json({
      status: 'running',
      service: 'Node.js Microservice',
      nodeVersion: process.version,
      dbStatus: 'connected',
      dbVersion: dbRes.rows[0].version,
      dbTime: dbRes.rows[0].current_timestamp
    });
  } catch (err) {
    res.status(500).json({ status: 'error', message: err.message });
  }
});

// 取得所有留言
app.get('/api/messages', async (req, res) => {
  try {
    const result = await pool.query('SELECT * FROM messages ORDER BY id DESC LIMIT 20');
    res.json(result.rows);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 新增留言
app.post('/api/messages', async (req, res) => {
  const { content } = req.body;
  if (!content) return res.status(400).json({ error: 'Content is required' });
  try {
    const result = await pool.query(
      'INSERT INTO messages (content) VALUES ($1) RETURNING *',
      [content]
    );
    res.status(201).json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 刪除留言
app.delete('/api/messages/:id', async (req, res) => {
  try {
    const result = await pool.query(
      'DELETE FROM messages WHERE id = $1 RETURNING *',
      [req.params.id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 修改留言
app.put('/api/messages/:id', async (req, res) => {
  const { content } = req.body;
  if (!content || !content.trim()) return res.status(400).json({ error: 'Content is required' });
  try {
    const result = await pool.query(
      'UPDATE messages SET content = $1 WHERE id = $2 RETURNING *',
      [content.trim(), req.params.id]
    );
    if (result.rowCount === 0) return res.status(404).json({ error: 'Not found' });
    res.json(result.rows[0]);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Backend service listening on port ${PORT}`);
});
