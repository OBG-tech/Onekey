#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多摄像头录制系统
独立运行，不依赖OBS，使用纯Python实现多摄像头拼接和录制
"""

import cv2
import numpy as np
import argparse
from datetime import datetime
import os
import sys
import time
from pathlib import Path


class MultiCameraRecorder:
    def __init__(self, camera_indices, layout='horizontal', output_dir='recordings', 
                 fps=30, resolution=None, show_preview=True, auto_start=False):
        """
        初始化多摄像头录制器
        
        Args:
            camera_indices: 摄像头索引列表，如 [0, 1, 2]
            layout: 拼接布局 - 'horizontal', 'vertical', 'grid'
            output_dir: 录制文件保存目录
            fps: 录制帧率
            resolution: 输出分辨率 (width, height)，None为自动
            show_preview: 是否显示预览窗口
            auto_start: 是否自动开始录制
        """
        self.camera_indices = camera_indices
        self.layout = layout
        self.output_dir = Path(output_dir)
        self.fps = fps
        self.target_resolution = resolution
        self.show_preview = show_preview
        self.auto_start = auto_start
        
        self.cameras = []
        self.video_writer = None
        self.is_recording = False
        self.frame_count = 0
        self.start_time = None
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def open_cameras(self):
        """打开所有摄像头"""
        print(f"\n📹 正在打开摄像头: {self.camera_indices}")
        
        for idx in self.camera_indices:
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                # 获取摄像头信息
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps = cap.get(cv2.CAP_PROP_FPS)
                
                self.cameras.append(cap)
                print(f"  ✅ 摄像头 #{idx}: {width}x{height} @ {actual_fps:.1f} FPS")
            else:
                print(f"  ❌ 无法打开摄像头 #{idx}")
        
        if not self.cameras:
            print("❌ 没有可用的摄像头")
            return False
        
        print(f"✅ 成功打开 {len(self.cameras)}/{len(self.camera_indices)} 个摄像头\n")
        return True
    
    def stitch_frames(self, frames):
        """
        拼接多个摄像头画面
        
        Args:
            frames: 帧列表
            
        Returns:
            拼接后的帧
        """
        if not frames:
            return None
        
        if len(frames) == 1:
            return frames[0]
        
        if self.layout == 'horizontal':
            return self._stitch_horizontal(frames)
        elif self.layout == 'vertical':
            return self._stitch_vertical(frames)
        elif self.layout == 'grid':
            return self._stitch_grid(frames)
        else:
            print(f"⚠️  未知布局: {self.layout}，使用横向拼接")
            return self._stitch_horizontal(frames)
    
    def _stitch_horizontal(self, frames):
        """横向拼接"""
        # 找到最大高度
        max_height = max(f.shape[0] for f in frames)
        
        # 调整所有帧为相同高度
        resized = []
        for frame in frames:
            h, w = frame.shape[:2]
            new_width = int(w * max_height / h)
            resized_frame = cv2.resize(frame, (new_width, max_height))
            resized.append(resized_frame)
        
        # 横向拼接
        return np.hstack(resized)
    
    def _stitch_vertical(self, frames):
        """纵向拼接"""
        # 找到最大宽度
        max_width = max(f.shape[1] for f in frames)
        
        # 调整所有帧为相同宽度
        resized = []
        for frame in frames:
            h, w = frame.shape[:2]
            new_height = int(h * max_width / w)
            resized_frame = cv2.resize(frame, (max_width, new_height))
            resized.append(resized_frame)
        
        # 纵向拼接
        return np.vstack(resized)
    
    def _stitch_grid(self, frames):
        """网格拼接"""
        num_frames = len(frames)
        
        # 计算网格大小
        cols = int(np.ceil(np.sqrt(num_frames)))
        rows = int(np.ceil(num_frames / cols))
        
        # 找到统一的帧大小（使用第一个帧的大小）
        target_h, target_w = frames[0].shape[:2]
        
        # 调整所有帧为相同大小
        resized = [cv2.resize(f, (target_w, target_h)) for f in frames]
        
        # 填充空白帧（如果需要）
        while len(resized) < rows * cols:
            blank = np.zeros((target_h, target_w, 3), dtype=np.uint8)
            resized.append(blank)
        
        # 创建网格
        grid_rows = []
        for r in range(rows):
            row_frames = resized[r * cols:(r + 1) * cols]
            grid_row = np.hstack(row_frames)
            grid_rows.append(grid_row)
        
        return np.vstack(grid_rows)
    
    def start_recording(self, stitched_frame):
        """开始录制"""
        if self.is_recording:
            return
        
        h, w = stitched_frame.shape[:2]
        
        # 如果指定了目标分辨率，调整
        if self.target_resolution:
            w, h = self.target_resolution
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.output_dir / f"multi_camera_{timestamp}.mp4"
        
        # 创建视频写入器
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.video_writer = cv2.VideoWriter(str(filename), fourcc, self.fps, (w, h))
        
        if self.video_writer.isOpened():
            self.is_recording = True
            self.start_time = time.time()
            self.frame_count = 0
            print(f"\n🔴 开始录制: {filename}")
            print(f"   分辨率: {w}x{h} @ {self.fps} FPS\n")
        else:
            print(f"❌ 无法创建视频文件: {filename}")
    
    def stop_recording(self):
        """停止录制"""
        if not self.is_recording:
            return
        
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        duration = time.time() - self.start_time
        print(f"\n⏹️  停止录制")
        print(f"   时长: {duration:.1f} 秒")
        print(f"   帧数: {self.frame_count}\n")
        
        self.is_recording = False
    
    def run(self):
        """主循环：捕获、拼接、显示、录制"""
        if not self.open_cameras():
            return
        
        print("🎬 多摄像头录制系统已启动")
        print("\n控制键:")
        print("  [Space] - 开始/停止录制")
        print("  [q] - 退出")
        print("  [s] - 截图\n")
        
        try:
            while True:
                # 读取所有摄像头的帧
                frames = []
                for cap in self.cameras:
                    ret, frame = cap.read()
                    if ret:
                        frames.append(frame)
                
                if not frames:
                    print("⚠️  无法读取摄像头画面")
                    break
                
                # 拼接画面
                stitched = self.stitch_frames(frames)
                
                if stitched is None:
                    continue
                
                # 如果指定了目标分辨率，调整
                if self.target_resolution:
                    stitched = cv2.resize(stitched, self.target_resolution)
                
                # 自动开始录制（仅首次）
                if self.auto_start and not self.is_recording and self.frame_count == 0:
                    self.start_recording(stitched)
                
                # 写入视频
                if self.is_recording:
                    self.video_writer.write(stitched)
                    self.frame_count += 1
                    
                    # 显示录制状态
                    elapsed = time.time() - self.start_time
                    status_text = f"REC {elapsed:.1f}s | {self.frame_count} frames"
                    cv2.putText(stitched, status_text, (10, 30), 
                              cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                # 显示预览
                if self.show_preview:
                    cv2.imshow('Multi-Camera Recording', stitched)
                    
                    # 处理按键
                    key = cv2.waitKey(1) & 0xFF
                    
                    if key == ord('q'):
                        print("\n👋 用户退出")
                        break
                    elif key == ord(' '):  # 空格键
                        if self.is_recording:
                            self.stop_recording()
                        else:
                            self.start_recording(stitched)
                    elif key == ord('s'):  # 截图
                        screenshot_path = self.output_dir / f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                        cv2.imwrite(str(screenshot_path), stitched)
                        print(f"📸 截图保存: {screenshot_path}")
        
        except KeyboardInterrupt:
            print("\n⚠️  键盘中断 (Ctrl+C)")
        
        finally:
            # 清理
            if self.is_recording:
                self.stop_recording()
            
            for cap in self.cameras:
                cap.release()
            
            if self.show_preview:
                cv2.destroyAllWindows()
            
            print("✅ 系统已关闭")


def main():
    parser = argparse.ArgumentParser(
        description='多摄像头录制系统 - 独立运行，不依赖OBS',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 横向拼接摄像头0和1
  %(prog)s --cameras 0,1 --layout horizontal
  
  # 网格布局，三个摄像头
  %(prog)s --cameras 0,1,2 --layout grid
  
  # 自动开始录制
  %(prog)s --cameras 0,1 --auto-start
  
  # 指定输出分辨率
  %(prog)s --cameras 0,1 --resolution 1920x1080
        """
    )
    
    parser.add_argument('--cameras', type=str, required=True,
                       help='摄像头索引列表，逗号分隔，如: 0,1,2')
    parser.add_argument('--layout', type=str, default='horizontal',
                       choices=['horizontal', 'vertical', 'grid'],
                       help='拼接布局 (默认: horizontal)')
    parser.add_argument('--output-dir', type=str, default='recordings',
                       help='录制文件保存目录 (默认: recordings)')
    parser.add_argument('--fps', type=int, default=30,
                       help='录制帧率 (默认: 30)')
    parser.add_argument('--resolution', type=str,
                       help='输出分辨率，格式: WIDTHxHEIGHT，如: 1920x1080')
    parser.add_argument('--show-preview', action='store_true', default=True,
                       help='显示预览窗口 (默认: 启用)')
    parser.add_argument('--no-preview', action='store_true',
                       help='不显示预览窗口')
    parser.add_argument('--auto-start', action='store_true',
                       help='自动开始录制')
    
    args = parser.parse_args()
    
    # 解析摄像头索引
    try:
        camera_indices = [int(x.strip()) for x in args.cameras.split(',')]
    except ValueError:
        print("❌ 错误: 摄像头索引必须是数字，用逗号分隔")
        sys.exit(1)
    
    # 解析分辨率
    resolution = None
    if args.resolution:
        try:
            w, h = args.resolution.lower().split('x')
            resolution = (int(w), int(h))
        except ValueError:
            print("❌ 错误: 分辨率格式应为 WIDTHxHEIGHT，如: 1920x1080")
            sys.exit(1)
    
    # 显示预览选项
    show_preview = not args.no_preview
    
    # 创建录制器
    recorder = MultiCameraRecorder(
        camera_indices=camera_indices,
        layout=args.layout,
        output_dir=args.output_dir,
        fps=args.fps,
        resolution=resolution,
        show_preview=show_preview,
        auto_start=args.auto_start
    )
    
    # 运行
    recorder.run()


if __name__ == '__main__':
    main()
