#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moments Web Viewer - 黑白像素复古风格
"""

import json
import os
from pathlib import Path
from flask import Flask, render_template_string, send_from_directory, jsonify, request
import requests

app = Flask(__name__)

# 配置
BASE_DIR = Path(__file__).parent
MOMENTS_DIR = BASE_DIR / "moments_organized"
QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "sk-84c8ffcad83c4718827763555733ff07")
QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen-max")

# 加载 moments 数据
def load_moments():
    index_file = MOMENTS_DIR / "index.json"
    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

# HTML 模板 - 黑白像素复古风格
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>⬛ Moments Viewer ⬜</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=VT323&family=Press+Start+2P&display=swap');
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg: #0a0a0a;
            --fg: #e0e0e0;
            --accent: #ffffff;
            --dim: #555555;
            --border: #333333;
        }
        
        body {
            font-family: 'VT323', monospace;
            background: var(--bg);
            color: var(--fg);
            min-height: 100vh;
            font-size: 18px;
            line-height: 1.4;
        }
        
        .scanlines {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
            background: repeating-linear-gradient(
                0deg,
                rgba(0,0,0,0.1) 0px,
                rgba(0,0,0,0.1) 1px,
                transparent 1px,
                transparent 2px
            );
            z-index: 9999;
        }
        
        header {
            background: var(--border);
            padding: 20px;
            text-align: center;
            border-bottom: 4px solid var(--dim);
        }
        
        h1 {
            font-family: 'Press Start 2P', cursive;
            font-size: 24px;
            color: var(--accent);
            text-shadow: 2px 2px 0 #333;
            letter-spacing: 2px;
        }
        
        .subtitle {
            color: var(--dim);
            margin-top: 10px;
            font-size: 16px;
        }
        
        .hero-photos {
            display: flex;
            justify-content: center;
            gap: 20px;
            padding: 20px;
            max-width: 1000px;
            margin: 0 auto;
        }
        
        .hero-photos img {
            width: 48%;
            max-height: 300px;
            object-fit: cover;
            border-radius: 10px;
            border: 3px solid var(--dim);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .stats {
            display: flex;
            justify-content: center;
            gap: 40px;
            padding: 20px;
            background: var(--border);
            margin-bottom: 20px;
            border: 2px solid var(--dim);
        }
        
        .stat {
            text-align: center;
        }
        
        .stat-value {
            font-size: 32px;
            color: var(--accent);
            font-family: 'Press Start 2P', cursive;
        }
        
        .stat-label {
            color: var(--dim);
            font-size: 14px;
            margin-top: 5px;
        }
        
        .filter-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .filter-btn {
            font-family: 'VT323', monospace;
            font-size: 18px;
            padding: 10px 20px;
            background: var(--border);
            color: var(--fg);
            border: 2px solid var(--dim);
            cursor: pointer;
            transition: all 0.1s;
        }
        
        .filter-btn:hover, .filter-btn.active {
            background: var(--fg);
            color: var(--bg);
            border-color: var(--accent);
        }
        
        .moments-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
        }
        
        .moment-card {
            background: var(--border);
            border: 2px solid var(--dim);
            cursor: pointer;
            transition: all 0.1s;
            overflow: hidden;
        }
        
        .moment-card:hover {
            border-color: var(--accent);
            transform: translate(-2px, -2px);
            box-shadow: 4px 4px 0 var(--dim);
        }
        
        .moment-thumb {
            width: 100%;
            height: 180px;
            background: var(--bg);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
        }
        
        .moment-thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .moment-thumb .no-image {
            font-size: 48px;
            color: var(--dim);
        }
        
        .moment-info {
            padding: 15px;
        }
        
        .moment-index {
            font-family: 'Press Start 2P', cursive;
            font-size: 12px;
            color: var(--dim);
        }
        
        .moment-time {
            color: var(--accent);
            font-size: 16px;
            margin: 5px 0;
        }
        
        .moment-source {
            display: inline-block;
            padding: 2px 8px;
            font-size: 14px;
            background: var(--bg);
            border: 1px solid var(--dim);
            margin-right: 5px;
        }
        
        .moment-source.btn { color: #ff6b6b; }
        .moment-source.ai { color: #69db7c; }
        .moment-source.log { color: #74c0fc; }
        
        .moment-desc {
            color: var(--fg);
            font-size: 16px;
            margin-top: 10px;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        
        /* Modal */
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.95);
            z-index: 1000;
            overflow-y: auto;
        }
        
        .modal-overlay.active {
            display: block;
        }
        
        .modal-content {
            max-width: 900px;
            margin: 40px auto;
            padding: 20px;
        }
        
        .modal-close {
            position: fixed;
            top: 20px;
            right: 30px;
            font-size: 48px;
            color: var(--fg);
            cursor: pointer;
            font-family: 'VT323', monospace;
            z-index: 1001;
        }
        
        .modal-close:hover {
            color: var(--accent);
        }
        
        .modal-header {
            border-bottom: 2px solid var(--dim);
            padding-bottom: 20px;
            margin-bottom: 20px;
        }
        
        .modal-title {
            font-family: 'Press Start 2P', cursive;
            font-size: 16px;
            color: var(--accent);
            margin-bottom: 10px;
        }
        
        .modal-media {
            margin-bottom: 20px;
        }
        
        .modal-media img, .modal-media video {
            width: 100%;
            max-height: 500px;
            object-fit: contain;
            background: #000;
        }
        
        .media-toggle {
            display: flex;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .modal-section {
            margin-bottom: 20px;
            padding: 15px;
            background: var(--border);
            border: 1px solid var(--dim);
        }
        
        .modal-section h3 {
            font-family: 'Press Start 2P', cursive;
            font-size: 12px;
            color: var(--dim);
            margin-bottom: 10px;
        }
        
        .transcript {
            color: var(--fg);
            font-size: 16px;
            line-height: 1.6;
            white-space: pre-wrap;
        }
        
        /* Summary section */
        .summary-section {
            margin-top: 40px;
            padding: 30px;
            background: var(--border);
            border: 4px solid var(--dim);
        }
        
        .summary-title {
            font-family: 'Press Start 2P', cursive;
            font-size: 18px;
            color: var(--accent);
            margin-bottom: 20px;
            text-align: center;
        }
        
        .summary-btn {
            display: block;
            width: 100%;
            max-width: 400px;
            margin: 0 auto 20px;
            padding: 15px 30px;
            font-family: 'Press Start 2P', cursive;
            font-size: 14px;
            background: var(--bg);
            color: var(--accent);
            border: 3px solid var(--accent);
            cursor: pointer;
            transition: all 0.1s;
        }
        
        .summary-btn:hover {
            background: var(--accent);
            color: var(--bg);
        }
        
        .summary-btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
        
        .summary-content {
            font-size: 18px;
            line-height: 1.8;
            color: var(--fg);
            white-space: pre-wrap;
        }
        
        .loading {
            text-align: center;
            color: var(--dim);
            font-size: 20px;
        }
        
        .loading::after {
            content: '';
            animation: dots 1.5s infinite;
        }
        
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        
        /* Footer */
        footer {
            text-align: center;
            padding: 40px 20px;
            color: var(--dim);
            font-size: 14px;
            border-top: 2px solid var(--border);
            margin-top: 40px;
        }
        
        /* Timeline view - 旅行足迹风格 */
        .view-toggle {
            display: flex;
            gap: 10px;
            margin-left: auto;
        }
        
        .moments-list {
            display: none;
        }
        
        .moments-list.active {
            display: block;
        }
        
        .moments-grid.active {
            display: grid;
        }
        
        .moments-grid:not(.active) {
            display: none;
        }
        
        .timeline {
            position: relative;
            padding-left: 20px;
            margin-left: 8px;
        }
        
        .timeline::before {
            content: '';
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 2px;
            background: linear-gradient(to bottom, #ff6b6b, #69db7c, #74c0fc, #ffd43b, #ff6b6b);
        }
        
        .timeline-item {
            position: relative;
            display: flex;
            gap: 10px;
            padding: 8px 10px;
            background: var(--border);
            border: 1px solid var(--dim);
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.15s;
        }
        
        .timeline-item:hover {
            border-color: var(--accent);
            background: #252525;
        }
        
        /* Clip/pin connecting to timeline */
        .timeline-item::before {
            content: '';
            position: absolute;
            left: -16px;
            top: 20px;
            width: 12px;
            height: 2px;
            background: var(--dim);
        }
        
        .timeline-item::after {
            content: '';
            position: absolute;
            left: -20px;
            top: 16px;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            border: 2px solid var(--bg);
        }
        
        .timeline-item.btn::after { background: #ff6b6b; }
        .timeline-item.ai::after { background: #69db7c; }
        .timeline-item.log::after { background: #74c0fc; }
        
        .timeline-time {
            font-size: 13px;
            font-weight: bold;
            color: #ffd43b;
            padding: 8px 0 4px 0;
            margin-left: 5px;
        }
        
        .timeline-thumb {
            width: 60px;
            height: 50px;
            flex-shrink: 0;
            border-radius: 4px;
            overflow: hidden;
            border: 1px solid var(--dim);
        }
        
        .timeline-thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .timeline-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        
        .timeline-source {
            padding: 2px 8px;
            font-size: 11px;
            background: var(--bg);
            border-radius: 3px;
            align-self: flex-start;
        }
        
        .timeline-source.btn { color: #ff6b6b; }
        .timeline-source.ai { color: #69db7c; }
        .timeline-source.log { color: #74c0fc; }
        
        .timeline-desc {
            color: var(--fg);
            font-size: 14px;
            line-height: 1.5;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        
        .timeline-footer {
            margin-top: 10px;
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .timeline-tag {
            padding: 4px 10px;
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            font-size: 14px;
            color: var(--dim);
        }
        
        /* Music Player */
        .music-player {
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--border);
            border: 2px solid var(--dim);
            padding: 15px 20px;
            border-radius: 30px;
            display: flex;
            align-items: center;
            gap: 15px;
            z-index: 100;
        }
        
        .music-btn {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            border: 2px solid var(--accent);
            background: transparent;
            color: var(--accent);
            font-size: 18px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .music-btn:hover {
            background: var(--accent);
            color: var(--bg);
        }
        
        .music-label {
            font-size: 14px;
            color: var(--dim);
        }
        
        /* Timeline Index Sidebar */
        .timeline-wrapper {
            display: flex;
            gap: 20px;
            position: relative;
        }
        
        .timeline-index-sidebar {
            width: 200px;
            flex-shrink: 0;
            position: sticky;
            top: 20px;
            max-height: calc(100vh - 40px);
            overflow-y: auto;
            background: var(--border);
            border: 2px solid var(--dim);
            padding: 15px 10px;
        }
        
        .timeline-index-title {
            font-family: 'Press Start 2P', cursive;
            font-size: 10px;
            color: var(--accent);
            margin-bottom: 15px;
            text-align: center;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--dim);
        }
        
        .timeline-index-item {
            padding: 5px 6px;
            margin-bottom: 4px;
            cursor: pointer;
            border-left: 3px solid transparent;
            transition: all 0.2s;
        }
        
        .timeline-index-item:hover {
            background: rgba(255,255,255,0.05);
            border-left-color: var(--accent);
        }
        
        .timeline-index-item.active {
            background: rgba(255,255,255,0.1);
            border-left-color: var(--accent);
        }
        
        .index-time {
            font-size: 12px;
            color: #ffd43b;
            font-weight: bold;
            margin-bottom: 4px;
        }
        
        .index-desc {
            font-size: 11px;
            color: var(--fg);
            line-height: 1.3;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }
        
        .timeline-content-wrapper {
            flex: 1;
            min-width: 0;
        }
        
        .timeline-index-toggle {
            display: none;
            position: fixed;
            bottom: 80px;
            left: 20px;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            background: var(--border);
            border: 2px solid var(--accent);
            color: var(--accent);
            font-size: 20px;
            cursor: pointer;
            z-index: 99;
            align-items: center;
            justify-content: center;
        }
        
        .timeline-index-toggle:hover {
            background: var(--accent);
            color: var(--bg);
        }
        
        @media (max-width: 768px) {
            .timeline-wrapper {
                flex-direction: column;
            }
            
            .timeline-index-sidebar {
                position: fixed;
                left: -220px;
                top: 0;
                width: 200px;
                max-height: 100vh;
                z-index: 999;
                transition: left 0.3s;
            }
            
            .timeline-index-sidebar.mobile-show {
                left: 0;
            }
            
            .timeline-index-toggle {
                display: flex;
            }
        }
        
        @media (max-width: 600px) {
            h1 { font-size: 16px; }
            .moments-grid { grid-template-columns: 1fr; }
            .stats { flex-direction: column; gap: 20px; }
            .timeline-thumb { width: 80px; height: 60px; }
            .timeline-content { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="scanlines"></div>
    
    <header>
        <h1>🎨 画谱 🎨</h1>
        <p class="subtitle">AI引导式绘画教学 · 12月19-21日 · 深客松铜奖 🏆</p>
    </header>
    
    <div class="hero-photos">
        <img src="/team_photo_huapu.jpg" alt="画谱团队获奖合影" style="width: 100%; max-width: 800px;">
    </div>
    
    <div class="container">
        <div class="stats">
            <div class="stat">
                <div class="stat-value" id="total-count">0</div>
                <div class="stat-label">总时刻数</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="btn-count">0</div>
                <div class="stat-label">🔴 按钮触发</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="ai-count">0</div>
                <div class="stat-label">🤖 AI识别</div>
            </div>
        </div>
        
        <div class="filter-bar">
            <button class="filter-btn active" data-filter="all">全部</button>
            <button class="filter-btn" data-filter="btn">🔴 按钮</button>
            <button class="filter-btn" data-filter="ai">🤖 AI</button>
            <button class="filter-btn" data-filter="log">📝 日志</button>
            <div class="view-toggle">
                <button class="filter-btn" id="grid-view-btn" onclick="setViewMode('grid')">🔲 网格</button>
                <button class="filter-btn active" id="list-view-btn" onclick="setViewMode('list')">🚶 时间线</button>
            </div>
        </div>
        
        <div class="moments-grid" id="moments-grid">
            <!-- Moments will be loaded here -->
        </div>
        
        <div class="moments-list active" id="moments-list">
            <div class="timeline-wrapper">
                <div class="timeline-index-sidebar" id="timeline-index">
                    <div class="timeline-index-title">📍 快速导航</div>
                    <div id="timeline-index-items">
                        <!-- Index items will be loaded here -->
                    </div>
                </div>
                <div class="timeline-content-wrapper">
                    <div id="timeline-content">
                        <!-- Timeline will be loaded here -->
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Timeline Index Toggle for Mobile -->
        <button class="timeline-index-toggle" id="timeline-index-toggle" onclick="toggleTimelineIndex()">
            📍
        </button>
        
        <div class="summary-section">
            <h2 class="summary-title">📊 AI 活动总结</h2>
            <button class="summary-btn" id="generate-summary">
                ▶ 生成 LLM 总结
            </button>
            <div class="summary-content" id="summary-content"></div>
        </div>
    </div>
    
    <!-- Music Player -->
    <div class="music-player" id="music-player">
        <button class="music-btn" id="music-toggle" onclick="toggleMusic()">▶</button>
        <span class="music-label">🎵 背景音乐</span>
        <audio id="bg-music" loop>
            <source src="https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Chad_Crouch/Arps/Chad_Crouch_-_Shipping_Lanes.mp3" type="audio/mpeg">
        </audio>
    </div>
    
    <footer>
        <p>🌟 时刻足迹 v2.0 | Powered by Qwen-Max</p>
        <p>Generated: {{ generated_time }}</p>
    </footer>
    
    <!-- Modal -->
    <div class="modal-overlay" id="modal">
        <span class="modal-close" onclick="closeModal()">×</span>
        <div class="modal-content" id="modal-content">
            <!-- Content loaded dynamically -->
        </div>
    </div>
    
    <script>
        let momentsData = [];
        let currentFilter = 'all';
        
        // Load moments
        async function loadMoments() {
            const resp = await fetch('/api/moments');
            momentsData = await resp.json();
            updateStats();
            renderMoments();
        }
        
        function updateStats() {
            document.getElementById('total-count').textContent = momentsData.length;
            document.getElementById('btn-count').textContent = momentsData.filter(m => m.source === 'user_anchor').length;
            document.getElementById('ai-count').textContent = momentsData.filter(m => m.source === 'ai_detected').length;
        }
        
        function getSourceType(source) {
            if (source === 'user_anchor') return 'btn';
            if (source === 'ai_detected') return 'ai';
            return 'log';
        }
        
        function getSourceLabel(source) {
            if (source === 'user_anchor') return '🔴 按钮';
            if (source === 'ai_detected') return '🤖 AI';
            return '📝 日志';
        }
        
        function renderMoments() {
            const grid = document.getElementById('moments-grid');
            const list = document.getElementById('moments-list');
            const filtered = currentFilter === 'all' 
                ? momentsData 
                : momentsData.filter(m => getSourceType(m.source) === currentFilter);
            
            // Grid view
            grid.innerHTML = filtered.map(m => `
                <div class="moment-card" onclick="openModal('${m.folder}')">
                    <div class="moment-thumb">
                        ${m.folder ? `<img src="/media/${m.folder}/frame.jpg" onerror="this.parentElement.innerHTML='<span class=no-image>⬜</span>'">` : '<span class="no-image">⬜</span>'}
                    </div>
                    <div class="moment-info">
                        <div class="moment-index">#${m.index}</div>
                        <div class="moment-time">${m.time}</div>
                        <span class="moment-source ${getSourceType(m.source)}">${getSourceLabel(m.source)}</span>
                        <p class="moment-desc">${m.tagline || '无描述'}</p>
                    </div>
                </div>
            `).join('');
            
            // Timeline view - generate index and content separately
            const timelineIndexItems = document.getElementById('timeline-index-items');
            const timelineContent = document.getElementById('timeline-content');
            
            // Generate index items
            timelineIndexItems.innerHTML = filtered.map((m, idx) => {
                const timeOnly = m.time ? m.time.split(' ')[1] || m.time : '未知';
                const shortDesc = (m.tagline || '无描述').substring(0, 20) + (m.tagline && m.tagline.length > 20 ? '...' : '');
                return `
                <div class="timeline-index-item" data-moment-index="${idx}" onclick="scrollToMoment(${idx})">
                    <div class="index-time">${timeOnly}</div>
                    <div class="index-desc">${shortDesc}</div>
                </div>
                `;
            }).join('');
            
            // Generate timeline content
            timelineContent.innerHTML = '<div class="timeline">' + filtered.map((m, idx) => {
                const sourceType = getSourceType(m.source);
                return `
                <div class="timeline-time">✨ ${m.time || '未知时间'}</div>
                <div class="timeline-item ${sourceType}" data-moment-index="${idx}" onclick="openModal('${m.folder}')">
                    <div class="timeline-thumb">
                        ${m.folder ? `<img src="/media/${m.folder}/frame.jpg" onerror="this.style.display='none'">` : ''}
                    </div>
                    <div class="timeline-content">
                        <span class="timeline-source ${sourceType}">${getSourceLabel(m.source)}</span>
                        <div class="timeline-desc">${m.tagline || '无描述'}</div>
                    </div>
                </div>
            `;
            }).join('') + '</div>';
        }
        
        let currentView = 'list';
        function setViewMode(mode) {
            currentView = mode;
            document.getElementById('moments-grid').classList.toggle('active', mode === 'grid');
            document.getElementById('moments-list').classList.toggle('active', mode === 'list');
            document.getElementById('grid-view-btn').classList.toggle('active', mode === 'grid');
            document.getElementById('list-view-btn').classList.toggle('active', mode === 'list');
        }
        
        // Filter (only for filter buttons, not view toggle)
        document.querySelectorAll('.filter-bar > .filter-btn[data-filter]').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.filter-bar > .filter-btn[data-filter]').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.dataset.filter;
                renderMoments();
            });
        });
        
        // Modal
        async function openModal(folder) {
            const resp = await fetch(`/api/moment/${folder}`);
            const data = await resp.json();
            
            const hasVideo = data.files?.video;
            const hasImage = data.files?.frame;
            
            document.getElementById('modal-content').innerHTML = `
                <div class="modal-header">
                    <div class="modal-title">#${data.index} | ${data.time}</div>
                    <span class="moment-source ${getSourceType(data.source)}">${getSourceLabel(data.source)}</span>
                </div>
                
                <div class="modal-media">
                    ${hasVideo ? `
                        <div class="media-toggle">
                            <button class="filter-btn active" onclick="showMedia('video', '${folder}')">▶ 视频</button>
                            <button class="filter-btn" onclick="showMedia('image', '${folder}')">🖼 图片</button>
                        </div>
                        <div id="media-container">
                            <video controls autoplay muted src="/media/${folder}/video.mp4"></video>
                        </div>
                    ` : hasImage ? `<img src="/media/${folder}/frame.jpg">` : '<p class="no-image">无媒体文件</p>'}
                </div>
                
                ${data.ai_tagline ? `
                <div class="modal-section">
                    <h3>📌 标签</h3>
                    <p>${data.ai_tagline}</p>
                </div>
                ` : ''}
                
                ${data.ai_summary ? `
                <div class="modal-section">
                    <h3>🤖 AI Summary</h3>
                    <div style="white-space: pre-wrap; line-height: 1.8;">${data.ai_summary}</div>
                </div>
                ` : ''}
                
                ${data.transcript ? `
                <div class="modal-section">
                    <h3>🎤 语音转录</h3>
                    <p class="transcript">${data.transcript}</p>
                </div>
                ` : ''}
                
                ${data.user_note ? `
                <div class="modal-section">
                    <h3>📋 用户备注</h3>
                    <p>${data.user_note}</p>
                </div>
                ` : ''}
            `;
            
            document.getElementById('modal').classList.add('active');
            document.body.style.overflow = 'hidden';
        }
        
        function showMedia(type, folder) {
            const container = document.getElementById('media-container');
            if (type === 'video') {
                container.innerHTML = `<video controls autoplay muted src="/media/${folder}/video.mp4"></video>`;
            } else {
                container.innerHTML = `<img src="/media/${folder}/frame.jpg">`;
            }
            document.querySelectorAll('.media-toggle .filter-btn').forEach((btn, i) => {
                btn.classList.toggle('active', (type === 'video' && i === 0) || (type === 'image' && i === 1));
            });
        }
        
        function closeModal() {
            document.getElementById('modal').classList.remove('active');
            document.body.style.overflow = '';
        }
        
        document.getElementById('modal').addEventListener('click', (e) => {
            if (e.target.id === 'modal') closeModal();
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });
        
        // Generate summary
        document.getElementById('generate-summary').addEventListener('click', async () => {
            const btn = document.getElementById('generate-summary');
            const content = document.getElementById('summary-content');
            
            btn.disabled = true;
            btn.textContent = '⏳ 生成中...';
            content.innerHTML = '<p class="loading">正在调用 Qwen-Max 生成总结</p>';
            
            try {
                const resp = await fetch('/api/summary', { method: 'POST' });
                const data = await resp.json();
                
                if (data.error) {
                    content.innerHTML = `<p style="color:#ff6b6b">错误: ${data.error}</p>`;
                } else {
                    content.innerHTML = data.summary;
                }
            } catch (err) {
                content.innerHTML = `<p style="color:#ff6b6b">请求失败: ${err.message}</p>`;
            }
            
            btn.disabled = false;
            btn.textContent = '▶ 重新生成';
        });
        
        // Scroll to moment from index
        function scrollToMoment(index) {
            const timelineItems = document.querySelectorAll('.timeline-item[data-moment-index]');
            if (timelineItems[index]) {
                timelineItems[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // Highlight active index item
                document.querySelectorAll('.timeline-index-item').forEach(item => item.classList.remove('active'));
                document.querySelector(`.timeline-index-item[data-moment-index="${index}"]`)?.classList.add('active');
                
                // Close mobile sidebar after selection
                if (window.innerWidth <= 768) {
                    document.getElementById('timeline-index').classList.remove('mobile-show');
                }
            }
        }
        
        // Toggle timeline index on mobile
        function toggleTimelineIndex() {
            document.getElementById('timeline-index').classList.toggle('mobile-show');
        }
        
        // Music player
        let isPlaying = false;
        function toggleMusic() {
            const audio = document.getElementById('bg-music');
            const btn = document.getElementById('music-toggle');
            if (isPlaying) {
                audio.pause();
                btn.textContent = '▶';
            } else {
                audio.play();
                btn.textContent = '⏸';
            }
            isPlaying = !isPlaying;
        }
        
        // Init
        loadMoments();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    from datetime import datetime
    return render_template_string(HTML_TEMPLATE, generated_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

@app.route('/api/moments')
def api_moments():
    moments = load_moments()
    # 加载每个 moment 的详细信息
    result = []
    for m in moments:
        folder = m.get('folder', '')
        info_file = MOMENTS_DIR / folder / 'info.json'
        if info_file.exists():
            with open(info_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
                result.append({
                    'index': m.get('index'),
                    'folder': folder,
                    'time': m.get('time'),
                    'source': info.get('source', m.get('source', '')),
                    'tagline': info.get('ai_tagline', '') or m.get('tagline', '')
                })
        else:
            result.append(m)
    return jsonify(result)

@app.route('/api/moment/<folder>')
def api_moment(folder):
    info_file = MOMENTS_DIR / folder / 'info.json'
    if info_file.exists():
        with open(info_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 获取 index
            moments = load_moments()
            for m in moments:
                if m.get('folder') == folder:
                    data['index'] = m.get('index')
                    data['time'] = m.get('time')
                    break
            
            # 检查文件是否存在
            folder_path = MOMENTS_DIR / folder
            data['files'] = {
                'video': (folder_path / 'video.mp4').exists(),
                'frame': (folder_path / 'frame.jpg').exists(),
                'context': (folder_path / 'context.txt').exists()
            }
            
            # 读取 context.txt 获取完整的 AI 分析
            context_file = folder_path / 'context.txt'
            if context_file.exists():
                try:
                    with open(context_file, 'r', encoding='utf-8') as cf:
                        context_content = cf.read()
                        
                        # 提取 AI 分析部分
                        ai_summary_parts = []
                        
                        # 提取场景描述
                        if '## 场景描述' in context_content:
                            scene_start = context_content.find('## 场景描述') + len('## 场景描述')
                            scene_end = context_content.find('## AI 分析', scene_start)
                            if scene_end == -1:
                                scene_end = context_content.find('##', scene_start)
                            scene_desc = context_content[scene_start:scene_end].strip()
                            if scene_desc:
                                ai_summary_parts.append(f"**场景描述**\n{scene_desc}")
                        
                        # 提取详细描述
                        if '详细描述：' in context_content:
                            detail_start = context_content.find('详细描述：') + len('详细描述：')
                            detail_end = context_content.find('\n分析框架标签', detail_start)
                            if detail_end == -1:
                                detail_end = context_content.find('\n上下文定位', detail_start)
                            if detail_end == -1:
                                detail_end = context_content.find('\n证据摘录', detail_start)
                            detail_desc = context_content[detail_start:detail_end].strip()
                            if detail_desc:
                                ai_summary_parts.append(f"**详细描述**\n{detail_desc}")
                        
                        # 提取分析框架标签
                        if '分析框架标签：' in context_content:
                            framework_start = context_content.find('分析框架标签：') + len('分析框架标签：')
                            framework_end = context_content.find('\n', framework_start)
                            framework = context_content[framework_start:framework_end].strip()
                            if framework:
                                ai_summary_parts.append(f"**分析框架**\n{framework}")
                        
                        # 提取证据摘录
                        if '证据摘录：' in context_content:
                            evidence_start = context_content.find('证据摘录：') + len('证据摘录：')
                            evidence_end = context_content.find('\n\n##', evidence_start)
                            if evidence_end == -1:
                                evidence_end = len(context_content)
                            evidence = context_content[evidence_start:evidence_end].strip()
                            if evidence:
                                ai_summary_parts.append(f"**证据摘录**\n{evidence}")
                        
                        # 组合完整的 AI Summary
                        if ai_summary_parts:
                            data['ai_summary'] = '\n\n'.join(ai_summary_parts)
                except Exception as e:
                    print(f"Error reading context.txt: {e}")
            
            return jsonify(data)
    return jsonify({'error': 'Not found'}), 404

@app.route('/team_photo_1.jpg')
def serve_team_photo_1():
    return send_from_directory(Path(__file__).parent, 'team_photo_1.jpg')

@app.route('/team_photo_2.jpg')
def serve_team_photo_2():
    return send_from_directory(Path(__file__).parent, 'team_photo_2.jpg')

@app.route('/team_photo_huapu.jpg')
def serve_team_photo_huapu():
    return send_from_directory(Path(__file__).parent, 'team_photo_huapu.jpg')

@app.route('/media/<path:filepath>')
def serve_media(filepath):
    return send_from_directory(MOMENTS_DIR, filepath)

@app.route('/api/summary', methods=['POST'])
def api_summary():
    try:
        moments = load_moments()
        
        # 收集摘要信息
        summaries = []
        for m in moments[:50]:  # 限制数量避免 token 过多
            folder = m.get('folder', '')
            info_file = MOMENTS_DIR / folder / 'info.json'
            if info_file.exists():
                with open(info_file, 'r', encoding='utf-8') as f:
                    info = json.load(f)
                    tagline = info.get('ai_tagline', '') or info.get('user_note', '')
                    if tagline:
                        summaries.append(f"[{m.get('time', '')}] {tagline}")
        
        prompt = f"""你是一个观察者，正在总结「画谱」团队在深客松黑客马拉松中的开发历程。

画谱团队成员：温标林、郭文涛、王宇豪、苏慧康  项目：AI引导式绘画教学  口号："绘画不是魔法，是逻辑"  最终成绩：铜奖

这是「画谱」在活动中（2025年12月19-21日）的 {len(moments)} 个关键时刻：

{chr(10).join(summaries[:80])}

请按时间线分析画谱团队的开发历程，输出阶段性总结（markdown格式）：

## 📅 时间线概览  ## 🚀 阶段一：项目启动（19日晚21:00-24:00）  ## 💻 阶段二：核心开发（20日凌晨-白天）  ## 🎨 阶段三：功能完善（20日下午）  ## 🏆 阶段四：冲刺收尾（21日）  ## 💡 技术亮点  ## 🌟 团队协作

基于时间线实际内容分析，多引用具体讨论，使用emoji

注意使用markdown格式输出各个阶段的分析"""


        headers = {
            'Authorization': f'Bearer {QWEN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': LLM_MODEL,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 2000
        }
        
        resp = requests.post(QWEN_API_URL, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        
        result = resp.json()
        summary = result.get('choices', [{}])[0].get('message', {}).get('content', '生成失败')
        
        return jsonify({'summary': summary})
        
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 Moments Web Viewer - 无按钮组版本")
    print("=" * 60)
    print(f"数据目录: {MOMENTS_DIR}")
    print(f"本地访问: http://localhost:8889")
    print()
    print("启动内网穿透（如果需要外网访问）:")
    print("  方法1: npx localtunnel --port 8889")
    print("  方法2: ssh -R 80:localhost:8889 serveo.net")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8889, debug=False)
