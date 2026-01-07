// ===== i18n 国际化系统 =====
// 翻译配置
const translations = {
    zh: {
        // 标题和面板
        'title': '集成系统 - 复古风格',
        'stats': '统计',
        'people': '人物列表',
        'video_feed': 'Live Feed',
        'key_moments': '关键时刻',
        'voice': '语音&AI',
        'linkography': '时间地图',
        
        // 统计标签
        'frames': '帧数',
        'people_count': '追踪人数',
        'fps': '实时FPS',
        'known_people': '已知人物',
        
        // 按钮
       'start_asr': '启动',
        'stop_asr': '停止',
        'pause_asr': '暂停',
        'resume_asr': '继续',
        'clear_transcript': '清空',
        'start_notes': '生成纪要',
        'stop_notes': '停止纪要',
        'download_notes': '下载',
        'transcribe_audio': '转写音频',
        'generate_notes_btn': '生成纪要',
        'mark_moment': '标记时刻',
        
        // 状态
        'recording': '录制中',
        'not_recording': '未录制',
        'paused': '已暂停',
        'available': '可用',
        'not_available': '不可用',
        'running': '运行中',
        'stopped': '已停止',
        'ready': '就绪',
        
        // 语音识别
        'realtime_asr': '实时语音识别',
        'transcript': '转录文本',
        'no_transcript': '暂无转录内容',
        'asr_status': '状态',
        'asr_model': '模型',
        
        // AI纪要
        'ai_notes': 'AI会议纪要',
        'key_points': '关键要点',
        'todo_items': '待办事项',
        'no_notes': '暂无纪要内容',
        'generating': '生成中...',
        
        // 关键时刻
        'moment_user': '用户标记',
        'moment_ai': 'AI识别',
        'moment_delete': '删除',
        'no_moments': '暂无关键时刻',
        'moment_at': '时刻',
        
        // AI直播间
        'ai_live': 'AI直播间',
        'live_on': 'LIVE ON',
        'live_off': 'LIVE OFF',
        'send': '发送',
        'chat_placeholder': '发送弹幕...',
        
        // 时间格式
        'seconds_ago': '秒前',
        'minutes_ago': '分钟前',
        'hours_ago': '小时前',
        'just_now': '刚刚',
        
        // 人物
        'person': '人物',
        'track_id': '追踪ID',
        'detections': '检测次数',
        'last_seen': '最后出现',
        
        // 提示消息
        'loading': '加载中...',
        'no_data': '暂无数据',
        'error': '错误',
        'success': '成功',
        'confirm_delete': '确认删除此关键时刻？',
        
        // 音频上传
        'upload_audio': '上传音频文件',
        'drag_drop': '拖拽文件或点击选择',
        'file_selected': '已选择文件',
        
        // 其他
        'close': '关闭',
        'save': '保存',
        'cancel': '取消',
        'confirm': '确认',
        'settings': '设置',
        'help': '帮助',
        'about': '关于',
        
        // 控制栏
        'hide': '隐藏',
        'show': '显示',
        'expand': '展开',
        'collapse': '折叠',
        
        // 时间轴
        'timeline': '时间轴',
        'zoom_in': '放大',
        'zoom_out': '缩小',
        'reset_view': '重置视图',
        
        // 导出
        'export': '导出',
        'download': '下载',
        'share': '分享',
        
        // 语言切换
        'language': '语言',
        'chinese': '中文',
        'english': 'English'
    },
    en: {
        // Titles and Panels
        'title': 'Integrated System - Retro Style',
        'stats': 'Statistics',
        'people': 'People',
        'video_feed': 'Live Feed',
        'key_moments': 'Key Moments',
        'voice': 'Voice & AI',
        'linkography': 'Timeline Map',
        
        // Stats Labels
        'frames': 'Frames',
        'people_count': 'People Tracked',
        'fps': 'Real-time FPS',
        'known_people': 'Known People',
        
        // Buttons
        'start_asr': 'Start',
        'stop_asr': 'Stop',
        'pause_asr': 'Pause',
        'resume_asr': 'Resume',
        'clear_transcript': 'Clear',
        'start_notes': 'Generate Notes',
        'stop_notes': 'Stop Notes',
        'download_notes': 'Download',
        'transcribe_audio': 'Transcribe Audio',
        'generate_notes_btn': 'Generate Notes',
        'mark_moment': 'Mark Moment',
        
        // Status
        'recording': 'Recording',
        'not_recording': 'Not Recording',
        'paused': 'Paused',
        'available': 'Available',
        'not_available': 'Not Available',
        'running': 'Running',
        'stopped': 'Stopped',
        'ready': 'Ready',
        
        // Speech Recognition
        'realtime_asr': 'Real-time Speech Recognition',
        'transcript': 'Transcript',
        'no_transcript': 'No transcript yet',
        'asr_status': 'Status',
        'asr_model': 'Model',
        
        // AI Notes
        'ai_notes': 'AI Meeting Notes',
        'key_points': 'Key Points',
        'todo_items': 'To-Do Items',
        'no_notes': 'No notes yet',
        'generating': 'Generating...',
        
        // Key Moments
        'moment_user': 'User Marked',
        'moment_ai': 'AI Detected',
        'moment_delete': 'Delete',
        'no_moments': 'No key moments yet',
        'moment_at': 'At',
        
        // AI Live
        'ai_live': 'AI Live Room',
        'live_on': 'LIVE ON',
        'live_off': 'LIVE OFF',
        'send': 'Send',
        'chat_placeholder': 'Send a message...',
        
        // Time Format
        'seconds_ago': 's ago',
        'minutes_ago': 'm ago',
        'hours_ago': 'h ago',
        'just_now': 'just now',
        
        // People
        'person': 'Person',
        'track_id': 'Track ID',
        'detections': 'Detections',
        'last_seen': 'Last Seen',
        
        // Messages
        'loading': 'Loading...',
        'no_data': 'No data',
        'error': 'Error',
        'success': 'Success',
        'confirm_delete': 'Delete this moment?',
        
        // Audio Upload
        'upload_audio': 'Upload Audio File',
        'drag_drop': 'Drag & drop file or click to select',
        'file_selected': 'File selected',
        
        // Others
        'close': 'Close',
        'save': 'Save',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'settings': 'Settings',
        'help': 'Help',
        'about': 'About',
        
        // Control Bar
        'hide': 'Hide',
        'show': 'Show',
        'expand': 'Expand',
        'collapse': 'Collapse',
        
        // Timeline
        'timeline': 'Timeline',
        'zoom_in': 'Zoom In',
        'zoom_out': 'Zoom Out',
        'reset_view': 'Reset View',
        
        // Export
        'export': 'Export',
        'download': 'Download',
        'share': 'Share',
        
        // Language
        'language': 'Language',
        'chinese': '中文',
        'english': 'English'
    }
};

// i18n 核心类
class I18n {
    constructor() {
        this.currentLang = localStorage.getItem('app_language') || 'en';
        this.translations = translations;
    }
    
    // 获取翻译
    t(key) {
        return this.translations[this.currentLang][key] || key;
    }
    
    // 切换语言
    setLanguage(lang) {
        if (this.translations[lang]) {
            this.currentLang = lang;
            localStorage.setItem('app_language', lang);
            this.updateDOM();
        }
    }
    
    // 更新DOM中所有带 data-i18n 的元素
    updateDOM() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const translation = this.t(key);
            
            // 根据元素类型更新内容
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
                if (el.placeholder !== undefined) {
                    el.placeholder = translation;
                } else {
                    el.value = translation;
                }
            } else if (el.tagName === 'IMG') {
                el.alt = translation;
            } else if (el.hasAttribute('title')) {
                el.title = translation;
            } else {
                el.textContent = translation;
            }
        });
        
        // 更新HTML lang属性
        document.documentElement.lang = this.currentLang === 'zh' ? 'zh-CN' : 'en';
    }
    
    // 当前语言
    getCurrentLanguage() {
        return this.currentLang;
    }
}

// 全局i18n实例
window.i18n = new I18n();

// DOM加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    window.i18n.updateDOM();
});
