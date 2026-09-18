/**
 * index.js - React 應用程式進入點
 * 將 App 元件掛載到 public/index.html 的 <div id="root">
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);