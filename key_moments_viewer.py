#!/usr/bin/env python3
"""
Key Moments Viewer - 独立Web服务 (带时间线)
端口: 8084
功能: 展示key moments视频和AI总结，左侧时间线，支持下载和复制
"""

import json
import os
import mimetypes
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import threading
import argparse
import urllib.request
import urllib.error
import urllib.parse

# Config
MAIN_SYSTEM_URL = "http://localhost:8082"

# 配置
PORT = 8084
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "integrated_data"
MOMENTS_FILE = DATA_DIR / "key_moments" / "moments.json"
MOMENTS_MEDIA_DIR = DATA_DIR / "key_moments"

def load_moments():
    """加载所有关键时刻"""
    if MOMENTS_FILE.exists():
        try:
            with open(MOMENTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('moments', [])
        except:
            return []
    return []

# HTML模板 - 黑白像素复古风格 + 左侧时间线
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⬛ Key Moments ⬜</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=VT323&family=Press+Start+2P&display=swap');
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        :root {
            --bg: #0a0a0a;
            --fg: #e0e0e0;
            --accent: #ffffff;
            --dim: #555555;
            --border: #333333;
            --user-color: #ff6b6b;
            --ai-color: #69db7c;
        }
        
        body {
            font-family: 'VT323', monospace;
            background: var(--bg);
            color: var(--fg);
            min-height: 100vh;
            font-size: 18px;
        }
        
        .scanlines {
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            background: repeating-linear-gradient(0deg, rgba(0,0,0,0.1) 0px, rgba(0,0,0,0.1) 1px, transparent 1px, transparent 2px);
            z-index: 9999;
        }
        
        header {
            background: var(--border);
            padding: 15px 20px;
            text-align: center;
            border-bottom: 4px solid var(--dim);
            position: fixed;
            top: 0; left: 0; right: 0;
            z-index: 100;
        }
        
        h1 {
            font-family: 'Press Start 2P', cursive;
            font-size: 16px;
            color: var(--accent);
            text-shadow: 2px 2px 0 #333;
        }
        
        .main-layout {
            display: flex;
            margin-top: 55px;
            min-height: calc(100vh - 55px);
        }
        
        /* 左侧时间线 */
        .timeline-sidebar {
            width: 16.67%;
            background: var(--border);
            border-right: 2px solid var(--dim);
            position: fixed;
            left: 0; top: 55px; bottom: 0;
            overflow-y: auto;
        }
        
        .timeline-header {
            padding: 20px 15px;
            border-bottom: 2px solid var(--dim);
            background: var(--bg);
            position: sticky;
            top: 0;
        }
        
        .timeline-title {
            font-family: 'Press Start 2P', cursive;
            font-size: 14px;
            color: var(--accent);
            margin-bottom: 15px;
        }
        
        .timeline-stats {
            display: flex;
            gap: 20px;
            font-size: 22px;
        }
        
        .timeline-stats .count {
            font-family: 'Press Start 2P', cursive;
            font-size: 24px;
            margin-right: 5px;
        }
        
        .dot-user { color: var(--user-color); }
        .dot-ai { color: var(--ai-color); }
        
        .timeline-list { padding: 12px; }
        
        .timeline-item {
            display: flex;
            gap: 12px;
            padding: 12px;
            margin-bottom: 10px;
            background: var(--bg);
            border: 2px solid var(--dim);
            cursor: pointer;
            position: relative;
        }
        
        .timeline-item:hover {
            border-color: var(--accent);
            background: #1a1a1a;
        }
        
        .timeline-item.active {
            border-color: var(--accent);
            box-shadow: 0 0 8px rgba(255,255,255,0.2);
        }
        
        .timeline-indicator {
            width: 6px;
            position: absolute;
            left: 0; top: 0; bottom: 0;
        }
        
        .timeline-indicator.user { background: var(--user-color); }
        .timeline-indicator.ai { background: var(--ai-color); }
        
        .timeline-thumb {
            width: 80px;
            height: 55px;
            background: #000;
            border: 2px solid var(--dim);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            flex-shrink: 0;
            overflow: hidden;
        }
        
        .timeline-thumb video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .timeline-thumb .no-thumb {
            font-size: 24px;
            color: var(--dim);
        }
        
        .timeline-info { flex: 1; min-width: 0; }
        
        .timeline-time {
            font-size: 16px;
            color: #ffd43b;
            margin-bottom: 5px;
        }
        
        .timeline-label {
            font-size: 18px;
            color: var(--fg);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .timeline-source {
            font-size: 14px;
            margin-top: 5px;
        }
        
        .timeline-source.user { color: var(--user-color); }
        .timeline-source.ai { color: var(--ai-color); }
        
        /* 主内容区 */
        .main-content {
            flex: 1;
            margin-left: 16.67%;
            padding: 15px;
        }
        
        .filter-bar {
            display: flex;
            gap: 8px;
            margin-bottom: 15px;
        }
        
        .filter-btn {
            font-family: 'VT323', monospace;
            font-size: 15px;
            padding: 6px 14px;
            background: var(--bg);
            color: var(--fg);
            border: 2px solid var(--dim);
            cursor: pointer;
        }
        
        .filter-btn:hover, .filter-btn.active {
            background: var(--fg);
            color: var(--bg);
            border-color: var(--accent);
        }
        
        .moments-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
            gap: 15px;
        }
        
        .moment-card {
            background: var(--border);
            border: 2px solid var(--dim);
            overflow: hidden;
            position: relative;
        }
        
        .moment-card:hover, .moment-card.active {
            border-color: var(--accent);
        }
        
        .moment-card.active {
            box-shadow: 0 0 15px rgba(255,255,255,0.2);
        }
        
        .card-indicator {
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 4px;
        }
        
        .card-indicator.user { background: var(--user-color); }
        .card-indicator.ai { background: var(--ai-color); }
        
        .moment-video-container {
            background: #000;
            aspect-ratio: 16/9;
            border-bottom: 2px solid var(--dim);
        }
        
        .moment-video {
            width: 100%;
            height: 100%;
            object-fit: contain;
        }
        
        .no-video {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--dim);
            font-size: 40px;
        }
        
        .moment-content { padding: 12px; }
        
        .moment-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .moment-time {
            color: #ffd43b;
            font-size: 13px;
        }
        
        .source-badge {
            padding: 3px 10px;
            font-size: 11px;
            font-weight: bold;
            border: 2px solid;
        }
        
        .source-badge.user {
            color: var(--user-color);
            border-color: var(--user-color);
        }
        
        .source-badge.ai {
            color: var(--ai-color);
            border-color: var(--ai-color);
        }
        
        .moment-tagline {
            font-family: 'Press Start 2P', cursive;
            font-size: 10px;
            color: var(--accent);
            margin-bottom: 8px;
            line-height: 1.5;
        }
        
        .moment-summary {
            font-size: 15px;
            color: var(--fg);
            line-height: 1.4;
            margin-bottom: 12px;
            max-height: 80px;
            overflow-y: auto;
        }
        
        .moment-actions {
            display: flex;
            gap: 8px;
        }
        
        .btn {
            font-family: 'VT323', monospace;
            font-size: 15px;
            padding: 6px 14px;
            background: var(--bg);
            color: var(--fg);
            border: 2px solid var(--dim);
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        
        .btn:hover {
            background: var(--fg);
            color: var(--bg);
        }
        
        .btn-primary {
            background: var(--accent);
            color: var(--bg);
            border-color: var(--accent);
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--dim);
        }
        
        .empty-state h2 {
            font-family: 'Press Start 2P', cursive;
            font-size: 14px;
            margin-bottom: 12px;
        }
        
        .copy-feedback {
            position: fixed;
            bottom: 25px;
            left: 50%;
            transform: translateX(-50%);
            background: #69db7c;
            color: #000;
            padding: 10px 20px;
            border: 2px solid #fff;
            font-family: 'Press Start 2P', cursive;
            font-size: 9px;
            display: none;
            z-index: 1000;
        }
        
        .copy-feedback.show { display: block; }
        
        .refresh-btn {
            position: fixed;
            bottom: 25px;
            right: 25px;
            width: 45px;
            height: 45px;
            border: 2px solid var(--accent);
            background: var(--border);
            color: var(--accent);
            font-size: 22px;
            cursor: pointer;
        }
        
        .refresh-btn:hover {
            background: var(--accent);
            color: var(--bg);
        }
        
        @media (max-width: 900px) {
            .timeline-sidebar { display: none; }
            .main-content { margin-left: 0; }
            .moments-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="scanlines"></div>
    
    <header>
        <h1>⬛ KEY MOMENTS ⬜</h1>
    </header>
    
    <div class="main-layout">
        <div class="timeline-sidebar">
            <div class="timeline-header">
                <div class="timeline-title">TIMELINE</div>
                <div class="timeline-stats">
                    <span class="dot-user"><span class="count" id="userCount">0</span> 🔴</span>
                    <span class="dot-ai"><span class="count" id="aiCount">0</span> 🤖</span>
                </div>
            </div>
            <div class="timeline-list" id="timelineList"></div>
        </div>
        
        <div class="main-content">
            <div class="filter-bar">
                <button class="filter-btn active" data-filter="all" onclick="filterMoments('all')">ALL</button>
                <button class="filter-btn" data-filter="user" onclick="filterMoments('user')">🔴 USER</button>
                <button class="filter-btn" data-filter="ai" onclick="filterMoments('ai')">🤖 AI</button>
            </div>
            
            <div class="moments-grid" id="momentsGrid"></div>
            
            <div class="empty-state" id="emptyState" style="display: none;">
                <h2>NO MOMENTS YET</h2>
                <p>Start capturing with the main system</p>
            </div>
        </div>
    </div>
    
    <button class="refresh-btn" onclick="loadMoments()" title="Refresh">↻</button>
    <div class="copy-feedback" id="copyFeedback">COPIED!</div>
    
    <script>
        let moments = [];
        let currentFilter = 'all';
        let selectedId = null;
        
        async function loadMoments() {
            try {
                const response = await fetch('/api/moments');
                moments = await response.json();
                renderTimeline();
                renderMoments();
                updateStats();
            } catch (e) {
                console.error('Load failed:', e);
            }
        }
        
        function updateStats() {
            document.getElementById('userCount').textContent = moments.filter(m => m.source === 'user_anchor').length;
            document.getElementById('aiCount').textContent = moments.filter(m => m.source !== 'user_anchor').length;
        }
        
        function getType(source) {
            return source === 'user_anchor' ? 'user' : 'ai';
        }
        
        function fmtTime(ts) {
            return new Date(ts * 1000).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        }
        
        function fmtDate(ts) {
            return new Date(ts * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        }
        
        function renderTimeline() {
            const list = document.getElementById('timelineList');
            const sorted = [...moments].sort((a, b) => b.timestamp - a.timestamp);
            
            list.innerHTML = sorted.map(m => {
                const type = getType(m.source);
                const tag = (m.ai_tagline || m.tagline || 'Untitled').substring(0, 22);
                const vp = m.video_path || '';
                const hasV = vp && !vp.includes('placeholder');
                const vUrl = hasV ? `/media/${vp.split('/').pop()}` : '';
                
                return `
                    <div class="timeline-item ${selectedId === m.id ? 'active' : ''}" 
                         data-id="${m.id}" onclick="selectMoment('${m.id}')">
                        <div class="timeline-indicator ${type}"></div>
                        <div class="timeline-thumb">
                            ${hasV ? `<video src="${vUrl}" preload="metadata" muted></video>` : '<span class="no-thumb">📹</span>'}
                        </div>
                        <div class="timeline-info">
                            <div class="timeline-time">${fmtTime(m.timestamp)} · ${fmtDate(m.timestamp)}</div>
                            <div class="timeline-label">${esc(tag)}</div>
                            <div class="timeline-source ${type}">${type === 'user' ? '🔴 USER' : '🤖 AI'}</div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function renderMoments() {
            const grid = document.getElementById('momentsGrid');
            const empty = document.getElementById('emptyState');
            
            let filtered = moments;
            if (currentFilter === 'user') filtered = moments.filter(m => m.source === 'user_anchor');
            else if (currentFilter === 'ai') filtered = moments.filter(m => m.source !== 'user_anchor');
            
            if (filtered.length === 0) {
                grid.style.display = 'none';
                empty.style.display = 'block';
                return;
            }
            
            grid.style.display = 'grid';
            empty.style.display = 'none';
            
            const sorted = [...filtered].sort((a, b) => b.timestamp - a.timestamp);
            
            grid.innerHTML = sorted.map(m => {
                const vp = m.video_path || '';
                const hasV = vp && !vp.includes('placeholder');
                const vUrl = hasV ? `/media/${vp.split('/').pop()}` : '';
                const type = getType(m.source);
                const tag = m.ai_tagline || m.tagline || 'Untitled';
                const sum = m.ai_description || m.description || 'No summary';
                
                return `
                    <div class="moment-card ${selectedId === m.id ? 'active' : ''}" id="card-${m.id}" data-id="${m.id}">
                        <div class="card-indicator ${type}"></div>
                        <div class="moment-video-container">
                            ${hasV ? `<video class="moment-video" controls preload="metadata"><source src="${vUrl}" type="video/mp4"></video>` : '<div class="no-video">📹</div>'}
                        </div>
                        <div class="moment-content">
                            <div class="moment-header">
                                <span class="source-badge ${type}">${type === 'user' ? '🔴 USER' : '🤖 AI'}</span>
                                <span class="moment-time">${fmtTime(m.timestamp)} · ${fmtDate(m.timestamp)}</span>
                            </div>
                            <div class="moment-tagline">${esc(tag)}</div>
                            <div class="moment-summary">${esc(sum)}</div>
                            <div class="moment-actions">
                                ${hasV ? `<a href="${vUrl}" download class="btn btn-primary">⬇ DOWNLOAD</a>` : ''}
                                <button class="btn" onclick="copySummary('${m.id}')">📋 COPY</button>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        function selectMoment(id) {
            selectedId = id;
            document.querySelectorAll('.timeline-item').forEach(el => el.classList.toggle('active', el.dataset.id === id));
            document.querySelectorAll('.moment-card').forEach(el => el.classList.toggle('active', el.dataset.id === id));
            const card = document.getElementById('card-' + id);
            if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        
        function filterMoments(f) {
            currentFilter = f;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.filter === f));
            renderMoments();
        }
        
        function esc(t) {
            if (!t) return '';
            const d = document.createElement('div');
            d.textContent = t;
            return d.innerHTML;
        }
        
        function copySummary(id) {
            const m = moments.find(x => x.id === id);
            if (!m) return;
            const type = getType(m.source);
            const txt = `${type === 'user' ? '🔴 USER' : '🤖 AI'}: ${m.ai_tagline || m.tagline || 'Moment'}\n\n${m.ai_description || m.description || ''}\n\n---\nID: ${m.id}\nTime: ${new Date(m.timestamp * 1000).toLocaleString()}`;
            navigator.clipboard.writeText(txt).then(showFeedback).catch(() => {
                const ta = document.createElement('textarea');
                ta.value = txt;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                showFeedback();
            });
        }
        
        function showFeedback() {
            const fb = document.getElementById('copyFeedback');
            fb.classList.add('show');
            setTimeout(() => fb.classList.remove('show'), 2000);
        }
        
        loadMoments();
        setInterval(loadMoments, 30000);
    </script>
</body>
</html>
'''

class MomentsHandler(SimpleHTTPRequestHandler):
    """处理Key Moments请求的Handler"""
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/' or path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
            return
        
        if path == '/api/moments':
            moments = load_moments()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(moments, ensure_ascii=False).encode('utf-8'))
            return
        
        if path.startswith('/media/'):
            filename = path[7:]
            filepath = MOMENTS_MEDIA_DIR / filename
            
            if filepath.exists():
                mime_type, _ = mimetypes.guess_type(str(filepath))
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                
                self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({'moments': load_moments()}).encode('utf-8'))
        else:
            self.send_error(404)

    def do_POST(self):
        # Proxy API requests to main system
        if self.path.startswith('/api/realtime_asr/') or self.path.startswith('/api/meeting_notes/'):
            self._proxy_to_main_system()
            return
            
        self.send_error(404)
    
    def log_message(self, format, *args):
        print(f"[MomentsViewer] {args[0]}")

def run_server():
    """启动服务器"""
    parser = argparse.ArgumentParser(description='Key Moments Viewer')
    parser.add_argument('--port', type=int, default=8084, help='Port to run the server on')
    args = parser.parse_args()
    
    server_port = args.port
    
    server = HTTPServer(('0.0.0.0', server_port), MomentsHandler)
    print(f"""
╔════════════════════════════════════════════════════════╗
║   📹 Key Moments Viewer                                ║
║   View, download, and share your captured moments      ║
╚════════════════════════════════════════════════════════╝

🌐 Server running at: http://localhost:{server_port}
📁 Moments directory: {MOMENTS_MEDIA_DIR}

Press Ctrl+C to stop
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
        server.shutdown()


if __name__ == '__main__':
    run_server()
