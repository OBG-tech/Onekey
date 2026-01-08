#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 智能视频分析整合系统 - 图形化启动器
GUI Launcher for Integrated Video Analysis System
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import sys
import os
from pathlib import Path
import threading
import webbrowser
import time

class IntegratedSystemLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("🎬 智能视频分析整合系统")
        self.root.geometry("700x600")
        self.root.configure(bg='#f0f0f0')
        
        # 设置工作目录
        self.base_dir = Path(__file__).parent.absolute()
        os.chdir(self.base_dir)
        
        self.process = None
        self.create_widgets()
        
    def create_widgets(self):
        # 标题
        title_frame = tk.Frame(self.root, bg='#2c3e50', height=80)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🎬 智能视频分析整合系统",
            font=("Arial", 24, "bold"),
            bg='#2c3e50',
            fg='white'
        )
        title_label.pack(pady=20)
        
        subtitle_label = tk.Label(
            title_frame,
            text="Integrated Video Analysis System",
            font=("Arial", 10),
            bg='#2c3e50',
            fg='#bdc3c7'
        )
        subtitle_label.pack()
        
        # 主内容区
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 模式选择
        mode_label = tk.Label(
            main_frame,
            text="选择模式 (Select Mode):",
            font=("Arial", 14, "bold"),
            bg='#f0f0f0'
        )
        mode_label.pack(anchor='w', pady=(0, 10))
        
        # 按钮容器
        buttons_frame = tk.Frame(main_frame, bg='#f0f0f0')
        buttons_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建大按钮
        button_configs = [
            {
                'text': '📹 摄像头模式\nCamera Mode',
                'command': self.launch_camera,
                'color': '#3498db'
            },
            {
                'text': '📁 视频文件模式\nVideo File Mode',
                'command': self.launch_video,
                'color': '#2ecc71'
            },
            {
                'text': '🔴 OBS实时流模式\nOBS Stream Mode',
                'command': self.launch_obs,
                'color': '#e74c3c'
            },
            {
                'text': '🎯 多人追踪(旧版)\nMulti-person Tracker',
                'command': self.launch_old_tracker,
                'color': '#9b59b6'
            },
            {
                'text': '🤖 ONE_KEY分析\nAI Analysis',
                'command': self.launch_onekey,
                'color': '#f39c12'
            }
        ]
        
        for i, config in enumerate(button_configs):
            row = i // 2
            col = i % 2
            
            btn = tk.Button(
                buttons_frame,
                text=config['text'],
                command=config['command'],
                font=("Arial", 14, "bold"),
                bg=config['color'],
                fg='white',
                relief=tk.RAISED,
                bd=3,
                cursor='hand2',
                height=4,
                width=20
            )
            btn.grid(row=row, column=col, padx=10, pady=10, sticky='nsew')
            
            # 悬停效果
            btn.bind('<Enter>', lambda e, b=btn: b.config(relief=tk.SUNKEN))
            btn.bind('<Leave>', lambda e, b=btn: b.config(relief=tk.RAISED))
        
        # 配置网格权重
        for i in range(3):
            buttons_frame.grid_rowconfigure(i, weight=1)
        for i in range(2):
            buttons_frame.grid_columnconfigure(i, weight=1)
        
        # 选项区
        options_frame = tk.LabelFrame(
            main_frame,
            text="高级选项 (Advanced Options)",
            font=("Arial", 11, "bold"),
            bg='#f0f0f0',
            padx=10,
            pady=10
        )
        options_frame.pack(fill=tk.X, pady=(20, 0))
        
        # AI分析选项
        self.enable_ai = tk.BooleanVar(value=False)
        ai_check = tk.Checkbutton(
            options_frame,
            text="🤖 启用AI分析 (Enable AI Analysis)",
            variable=self.enable_ai,
            font=("Arial", 10),
            bg='#f0f0f0'
        )
        ai_check.pack(anchor='w', pady=2)
        
        # 人脸识别选项
        self.enable_face = tk.BooleanVar(value=True)
        face_check = tk.Checkbutton(
            options_frame,
            text="👤 启用人脸识别 (Enable Face Recognition)",
            variable=self.enable_face,
            font=("Arial", 10),
            bg='#f0f0f0'
        )
        face_check.pack(anchor='w', pady=2)
        
        # 状态栏
        status_frame = tk.Frame(self.root, bg='#34495e', height=40)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(
            status_frame,
            text="就绪 (Ready)",
            font=("Arial", 10),
            bg='#34495e',
            fg='white'
        )
        self.status_label.pack(pady=10)
        
    def get_base_command(self):
        """获取基础命令"""
        venv_python = self.base_dir / ".venv" / "bin" / "python3"
        if venv_python.exists():
            cmd = [str(venv_python)]
        else:
            cmd = [sys.executable]
        
        cmd.append(str(self.base_dir / "integrated_system.py"))
        
        # 添加选项
        if self.enable_ai.get():
            cmd.append("--ai")
        if not self.enable_face.get():
            cmd.append("--no-face")
            
        return cmd
    
    def launch_process(self, cmd):
        """启动后端进程"""
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.base_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 等待服务器启动
            time.sleep(3)
            
            # 打开Web界面
            # web_path = self.base_dir / "web" / "integrated.html"
            # if web_path.exists():
            #    webbrowser.open(f"file://{web_path}")
            # else:
            #    webbrowser.open("http://localhost:8080")
            
            # 强制打开服务端页面 (integrated final.html)
            webbrowser.open("http://localhost:8080/integrated%20final.html")
            
            self.status_label.config(
                text="✅ 系统运行中 | Web界面: http://localhost:8080/integrated%20final.html | 按窗口关闭按钮停止",
                fg='#2ecc71'
            )
            
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动系统:\n{str(e)}")
            self.status_label.config(text=f"❌ 启动失败: {str(e)}", fg='#e74c3c')
    
    def launch_camera(self):
        """启动摄像头模式"""
        cmd = self.get_base_command()
        cmd.extend(["--camera", "0"])
        
        self.status_label.config(text="🎥 启动摄像头模式...", fg='#3498db')
        threading.Thread(target=self.launch_process, args=(cmd,), daemon=True).start()
    
    def launch_video(self):
        """启动视频文件模式"""
        video_path = filedialog.askopenfilename(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv"),
                ("所有文件", "*.*")
            ]
        )
        
        if not video_path:
            return
        
        cmd = self.get_base_command()
        cmd.extend(["--video", video_path])
        
        self.status_label.config(text=f"🎬 启动视频分析: {Path(video_path).name}", fg='#2ecc71')
        threading.Thread(target=self.launch_process, args=(cmd,), daemon=True).start()
    
    def launch_obs(self):
        """启动OBS流模式"""
        response = messagebox.askquestion(
            "OBS虚拟相机",
            "请确保已在OBS中启动虚拟相机:\n\n"
            "工具(Tools) → 虚拟相机(Virtual Camera) → 启动(Start)\n\n"
            "是否已准备好?"
        )
        
        if response != 'yes':
            return
        
        cmd = self.get_base_command()
        cmd.append("--obs")
        
        self.status_label.config(text="🔴 启动OBS流分析...", fg='#e74c3c')
        threading.Thread(target=self.launch_process, args=(cmd,), daemon=True).start()
    
    def launch_old_tracker(self):
        """启动旧版多人追踪系统"""
        tracker_dir = self.base_dir / "multi_person_tracker"
        gui_launcher = tracker_dir / "gui_launcher.py"
        
        if not gui_launcher.exists():
            messagebox.showerror(
                "文件不存在",
                f"找不到文件:\n{gui_launcher}"
            )
            return
        
        try:
            venv_python = self.base_dir / ".venv" / "bin" / "python3"
            if venv_python.exists():
                cmd = [str(venv_python), str(gui_launcher)]
            else:
                cmd = [sys.executable, str(gui_launcher)]
            
            subprocess.Popen(cmd, cwd=str(tracker_dir))
            self.status_label.config(text="🎯 已启动多人追踪系统", fg='#9b59b6')
            
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动:\n{str(e)}")
    
    def launch_onekey(self):
        """启动ONE_KEY分析系统"""
        onekey_dir = self.base_dir / "ONE_KEY"
        onekey_app = onekey_dir / "onekey_app.py"
        
        if not onekey_app.exists():
            messagebox.showerror(
                "文件不存在",
                f"找不到文件:\n{onekey_app}"
            )
            return
        
        try:
            venv_python = self.base_dir / ".venv" / "bin" / "python3"
            if venv_python.exists():
                cmd = [str(venv_python), str(onekey_app)]
            else:
                cmd = [sys.executable, str(onekey_app)]
            
            subprocess.Popen(cmd, cwd=str(onekey_dir))
            self.status_label.config(text="🤖 已启动ONE_KEY分析系统", fg='#f39c12')
            
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动:\n{str(e)}")

def main():
    root = tk.Tk()
    app = IntegratedSystemLauncher(root)
    
    # 窗口关闭时清理
    def on_closing():
        if app.process and app.process.poll() is None:
            response = messagebox.askquestion(
                "确认退出",
                "系统正在运行，是否停止并退出?"
            )
            if response == 'yes':
                try:
                    app.process.terminate()
                    app.process.wait(timeout=5)
                except:
                    app.process.kill()
                root.destroy()
        else:
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
