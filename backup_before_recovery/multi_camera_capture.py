#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多摄像头捕获模块
支持4摄像头2x2拼接，高画质，高帧率
"""

import cv2
import numpy as np
import threading
import queue
import time
from typing import List, Tuple, Optional
from pathlib import Path


class MultiCameraCapture:
    """
    多摄像头捕获和拼接
    支持2x2网格布局，高质量输出
    """
    
    def __init__(self, camera_indices: List[int] = [0, 1, 2, 3], 
                 target_fps: int = 60,
                 resolution_per_camera: Tuple[int, int] = (1920, 1080),
                 enable_recording: bool = False,
                 recording_dir: str = 'recordings'):
        """
        初�?�化多摄像头捕获
        
        Args:
            camera_indices: 摄像头索引列�?
            target_fps: �?标帧�?
            resolution_per_camera: 每个摄像头的�?标分辨率 (width, height)
            enable_recording: �?否启用全程录�?
            recording_dir: 录制文件保存�?�?
        """
        self.camera_indices = camera_indices
        self.target_fps = target_fps
        self.resolution = resolution_per_camera
        
        self.cameras = []
        self.frame_queues = []
        self.capture_threads = []
        self.is_running = False
        
        # 输出参数
        self.stitched_width = resolution_per_camera[0] * 2  # 3840
        self.stitched_height = resolution_per_camera[1] * 2  # 2160
        
        # 录制参数 - 使用更小的分辨率
        self.enable_recording = enable_recording
        self.recording_dir = Path(recording_dir)
        self.video_writer = None
        self.recording_filename = None
        self.audio_filename = None
        self.audio_process = None
        
        # �?立录制线程支�?
        self.latest_frames = [None] * len(camera_indices)
        self.frame_lock = threading.Lock()
        
        # 录制时缩小到720p以节省空�?
        self.recording_width = 1280
        self.recording_height = 720
        
        # 帧率追踪（用于�?�算实际FPS�?
        self.frame_count = 0
        self.recording_start_time = None
        
        if self.enable_recording:
            self.recording_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n📹 初�?�化多摄像头系统")
        print(f"   摄像�?: {camera_indices}")
        print(f"   每个摄像�?: {resolution_per_camera[0]}x{resolution_per_camera[1]}")
        print(f"   拼接�?: {self.stitched_width}x{self.stitched_height}")
        print(f"   �?标FPS: {target_fps}")
        if self.enable_recording:
            print(f"   🔴 录制: �?�? (缩放到{self.recording_width}x{self.recording_height} + 音�??)")
        print()
        
    def open_cameras(self) -> bool:
        """
        打开所有摄像头并�?�置高质量参�?
        
        Returns:
            True if at least one camera opened successfully
        """
        print("🔌 正在打开摄像�?...")
        
        for idx in self.camera_indices:
            cap = cv2.VideoCapture(idx)
            
            if cap.isOpened():
                # MJPEG编码�?高分辨率高帧率的关键
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
                
                # 设置分辨率和帧率
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                
                # Double Check MJPG
                fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
                codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                
                # 尝试设置缓冲区大小为1（减少延迟）
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                # 获取实际设置
                actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                actual_fps = cap.get(cv2.CAP_PROP_FPS)
                
                self.cameras.append(cap)
                self.frame_queues.append(queue.Queue(maxsize=2))
                
                print(f"  �? 摄像�? #{idx}: {actual_width}x{actual_height} @ {actual_fps:.1f} FPS (Codec: {codec})")
                
                if actual_width == 0 or actual_height == 0:
                     print(f"  ⚠️ Warning: Camera #{idx} reports 0x0 resolution. Re-trying...")
                     # Retry logic or fallback could go here
            else:
                print(f"  �? 无法打开摄像�? #{idx}")
                self.frame_queues.append(None)
        
        success_count = len(self.cameras)
        total_count = len(self.camera_indices)
        
        if success_count == 0:
            print("�? 没有�?用的摄像�?")
            return False
        
        if success_count < total_count:
            print(f"⚠️  �?�? {success_count}/{total_count} �?摄像头可�?")
        else:
            print(f"�? 所�? {success_count} �?摄像头已就绪\n")
        
        return True
    
    def _capture_thread(self, camera_idx: int, queue_obj: queue.Queue):
        """
        单个摄像头的捕获线程
        
        Args:
            camera_idx: 摄像头索引（在self.cameras�?的索引）
            queue_obj: 该摄像头的帧队列
        """
        cap = self.cameras[camera_idx]
        
        while self.is_running:
            ret, frame = cap.read()
            if ret:
                # �?保尺寸一�?
                if frame.shape[1] != self.resolution[0] or frame.shape[0] != self.resolution[1]:
                    frame = cv2.resize(frame, self.resolution)
                
                # 更新最新帧（用于录制线程）
                with self.frame_lock:
                    self.latest_frames[camera_idx] = frame
                
                # 非阻塞放入队�? (用于Main App / Read)
                try:
                    queue_obj.put(frame, block=False)
                except queue.Full:
                    # 如果队列满了，丢弃旧�?
                    try:
                        queue_obj.get_nowait()
                        queue_obj.put(frame, block=False)
                    except:
                        pass
            
            # 移除sleep以获得最大帧�? (cap.read�?�?�?阻�?�的)
            # time.sleep(1.0 / self.target_fps / 2)
    
    def start_capture_threads(self):
        """�?动所有摄像头的捕获线�?"""
        self.is_running = True
        
        for idx, queue_obj in enumerate(self.frame_queues):
            if queue_obj is not None:
                thread = threading.Thread(
                    target=self._capture_thread, 
                    args=(idx, queue_obj),
                    daemon=True
                )
                thread.start()
                self.capture_threads.append(thread)
        
        print(f"🎬 �?动了 {len(self.capture_threads)} �?捕获线程\n")
        
        # �?动录�?
        if self.enable_recording:
            self._start_recording()
            
            # �?动独立录制线�?
            self.recording_thread = threading.Thread(
                target=self._recording_worker,
                daemon=True
            )
            self.recording_thread.start()
    
    def get_frames(self) -> List[np.ndarray]:
        """
        获取所有摄像头的当前帧
        
        Returns:
            帧列�?，�?�果某个摄像头不�?用则该位�?为None
        """
        frames = []
        
        for idx, queue_obj in enumerate(self.frame_queues):
            if queue_obj is not None:
                try:
                    frame = queue_obj.get(timeout=0.1)
                    frames.append(frame)
                except queue.Empty:
                    # 使用上一帧或黑屏
                    if frames:
                        frames.append(frames[-1].copy())
                    else:
                        blank = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
                        frames.append(blank)
            else:
                # 摄像头不�?�?，使用黑屏占�?
                blank = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
                cv2.putText(blank, f"Camera {self.camera_indices[idx]} Not Available", 
                           (50, self.resolution[1]//2), 
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                frames.append(blank)
        
        return frames
    
    def stitch_2x2(self, frames: List[np.ndarray]) -> np.ndarray:
        """
        2x2网格拼接
        
        Args:
            frames: 4�?帧的列表 (按索�?0,1,2,3 �? 左上,右上,左下,右下)
        
        Returns:
            拼接后的�?
        """
        if len(frames) < 4:
            # 不足4�?摄像头，�?充黑�?
            while len(frames) < 4:
                blank = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
                frames.append(blank)
        
        # �?保所有帧尺�?�一�?
        for i in range(4):
            if frames[i].shape[1] != self.resolution[0] or frames[i].shape[0] != self.resolution[1]:
                frames[i] = cv2.resize(frames[i], self.resolution)
        
        # 拼接: 0,1在上; 2,3在下
        top_row = np.hstack([frames[0], frames[1]])
        bottom_row = np.hstack([frames[2], frames[3]])
        stitched = np.vstack([top_row, bottom_row])
        
        return stitched
    
    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        读取拼接后的�? (兼�?�cv2.VideoCapture接口)
        
        Returns:
            (success, frame) 元组
        """
        frames = self.get_frames()
        
        if len(frames) == 0:
            return False, None
        
        stitched = self.stitch_2x2(frames)
        
        # 录制逻辑已移至独立线�? _recording_worker
        
        return True, stitched
    
    def _recording_worker(self):
        """独立录制线程，确保固定帧率"""
        # 录制帧率: 如果目标FPS>=60，则录制60，否则30
        rec_fps = 60.0 if self.target_fps >= 60 else 30.0
        target_interval = 1.0 / rec_fps
        print(f"📼 独立录制线程启动 (Target: {rec_fps:.1f} FPS)")
        
        while self.is_running:
            start_time = time.time()
            
            # Use local reference to avoid race condition with stop_recording setting it to None
            writer = self.video_writer
            if writer is not None:
                # 获取最新帧数据
                current_frames = []
                with self.frame_lock:
                    # 深拷贝或直接引用(如果仅仅读取拼接)
                    # 这里为了速度我们引用，stitch函数会handle shape
                    for f in self.latest_frames:
                        if f is not None:
                            current_frames.append(f)
                        else:
                            # 占位符
                            blank = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)
                            current_frames.append(blank)
                
                # 拼接
                stitched = self.stitch_2x2(current_frames)
                
                # 缩放并写入
                recording_frame = cv2.resize(stitched, (self.recording_width, self.recording_height))
                try:
                    writer.write(recording_frame)
                except Exception as e:
                    pass # Ignore if writer is closed during write
                
                # 记录开始时间（第一帧）
                if self.recording_start_time is None:
                    self.recording_start_time = time.time()
                self.frame_count += 1
            
            # 精确控制帧率
            elapsed = time.time() - start_time
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def _start_recording(self):
        """开始录制（视�??+音�?�）"""
        from datetime import datetime
        import subprocess
        import os
        
        # 重置帧�?�数
        self.frame_count = 0
        self.recording_start_time = None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 临时视�?�文件（无音频，�?能FPS不准�?�?
        self.video_only_filename = self.recording_dir / f"multicam_{timestamp}_raw.avi"
        # 临时音�?�文�?
        self.audio_filename = self.recording_dir / f"multicam_{timestamp}_audio.wav"
        # 最终输出文件（视�??+音�?�合并，FPS已校正）
        self.recording_filename = self.recording_dir / f"multicam_{timestamp}.mp4"
        
        # 使用MJPG编码�?速写入（不压缩），后�?用ffmpeg重新编码
        # 这样�?以确保每帧都�?写入，不会因编码延迟丢帧
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        self.video_writer = cv2.VideoWriter(
            str(self.video_only_filename),
            fourcc,
            30.0,  # 占位�?FPS，实际FPS在release时通过ffmpeg校�??
            (self.recording_width, self.recording_height)
        )
        
        if self.video_writer.isOpened():
            print(f"🔴 视�?�录制已开�?: {self.video_only_filename}")
            print(f"   编码: MJPG (临时), 分辨�?: {self.recording_width}x{self.recording_height}")
        else:
            print(f"�? 无法创建视�?�录制文�?: {self.video_only_filename}\n")
            self.video_writer = None
            return
        
        # 2. �?动音频录制（使用ffmpeg录制系统默�?�麦克�?�）
        try:
            import platform
            system_name = platform.system()
            audio_cmd = []

            if system_name == 'Darwin':
                # macOS使用avfoundation，�?��??":0"通常�?默�?�麦克�??
                # �?以通过 ffmpeg -f avfoundation -list_devices true -i "" 查看设�?�列�?
                audio_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'avfoundation',
                    '-i', ':0',  # 默�?�音频输入�?��??
                    '-acodec', 'pcm_s16le',
                    '-ar', '44100',
                    '-ac', '2',
                    str(self.audio_filename)
                ]
            elif system_name == 'Linux':
                # Linux使用pulse (PulseAudio) �? alsa
                # 优先使用pulse，因为它�?持与其他应用共享录音
                audio_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'pulse',
                    '-i', 'default',
                    '-acodec', 'pcm_s16le',
                    '-ar', '44100',
                    '-ac', '2',
                    str(self.audio_filename)
                ]
            
            if audio_cmd:
                # 后台�?动ffmpeg录音
                self.audio_process = subprocess.Popen(
                    audio_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.PIPE
                )
                print(f"🎤 音�?�录制已开�?: {self.audio_filename}")
                print(f"   设�??: 系统默�?�麦克�?? ({'PulseAudio' if system_name == 'Linux' else 'AVFoundation'})\n")
            else:
                print(f"⚠️  不支持的操作系统用于音�?�录�?: {system_name}")
                print(f"   将只录制视�?�（无音频）\n")
                self.audio_process = None
            
        except Exception as e:
            print(f"⚠️ 音�?�录制启动失�?: {e}")
            print(f"   将只录制视�?�（无音频）\n")
            self.audio_process = None
    
    def release(self):
        """释放所有摄像头资源，校正�?��?�FPS并合并音�?"""
        import subprocess
        
        print("\n🛑 正在释放摄像�?...")
        
        # 计算实际FPS
        recording_end_time = time.time()
        actual_fps = 30.0  # 默�?��?
        recording_duration = 0
        
        if self.recording_start_time and self.frame_count > 0:
            recording_duration = recording_end_time - self.recording_start_time
            if recording_duration > 0:
                actual_fps = self.frame_count / recording_duration
                print(f"📊 录制统�??: {self.frame_count} �?, {recording_duration:.1f} �?, 实际FPS: {actual_fps:.1f}")
        
        # 1. 停�?��?��?�录�?
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
        
        # 2. 停�?�音频录�?
        if self.audio_process is not None:
            try:
                self.audio_process.communicate(input=b'q', timeout=2)
            except:
                try:
                    self.audio_process.terminate()
                    self.audio_process.wait(timeout=2)
                except:
                    self.audio_process.kill()
            self.audio_process = None
            print("🎤 音�?�录制已停�??")
        
        # 3. 使用ffmpeg校�?��?��?�FPS并合并音�?
        video_raw_path = getattr(self, 'video_only_filename', None)
        audio_path = getattr(self, 'audio_filename', None)
        final_path = getattr(self, 'recording_filename', None)
        
        if video_raw_path and video_raw_path.exists() and self.frame_count > 0:
            print("🔄 正在处理视�?�（校�??FPS + 合并音�?�）...")
            
            try:
                if audio_path and audio_path.exists() and recording_duration > 0:
                    # ��ȡ������Ƶ��ʵ��ʱ��
                    merge_cmd = [
                        'ffmpeg', '-y', '-loglevel', 'error',
                        '-r', str(actual_fps),  # 设置输入视�?�的实际帧率
                        '-i', str(video_raw_path),
                        '-i', str(audio_path),
                        '-c:v', 'libx264',
                        '-preset', 'fast',
                        '-crf', '23',
                        '-r', '30',  # 输出30fps
                        '-c:a', 'aac',
                        '-b:a', '128k',
                        '-t', str(recording_duration),  # 限制输出时长为录制时�?
                        '-movflags', '+faststart',
                        str(final_path)
                    ]
                    
                    try:
                        # ��ִ�� ffmpeg ʱ���� SIGINT (Ctrl+C)������ϲ����жϵ����ļ���
                        # ����� Python 3.7+�������� Popen/run ��ʹ�� preexec_fn ���� start_new_session
                        # ������򵥵ز��� KeyboardInterrupt �����Ը�ֱ��
                        
                        # ��ʱ�Ƴ� SIGINT ��������
                        import signal
                        original_handler = signal.getsignal(signal.SIGINT)
                        signal.signal(signal.SIGINT, signal.SIG_IGN)
                        
                        try:
                            # ���ӳ�ʱʱ�䵽 600�� (10����)
                            result = subprocess.run(merge_cmd, capture_output=True, timeout=600)
                        finally:
                            # �ָ��źŴ���
                            signal.signal(signal.SIGINT, original_handler)
                            
                    except subprocess.TimeoutExpired:
                        print(f"?? ��Ƶ�ϲ���ʱ")
                        result = subprocess.CompletedProcess(args=merge_cmd, returncode=1, stderr=b"Timeout")
                    except Exception as e:
                         print(f"?? ��Ƶ�ϲ�ʱ�����쳣: {e}")
                         # ����һ��ģ���ʧ�ܽ��
                         result = subprocess.CompletedProcess(args=merge_cmd, returncode=1, stderr=str(e).encode())

                    # ��ʹffmpeg���ط�0�����룬ֻҪ������ļ��Ҵ�С������Ҳ��Ϊ�ɹ�
                    success = final_path.exists() and final_path.stat().st_size > 1024
                    
                    if success:
                        file_size = final_path.stat().st_size / (1024 * 1024)
                        print(f"�? 录制已保存（视�??+音�?�同步）: {final_path}")
                        print(f"   时长: {recording_duration:.1f}�?, 大小: {file_size:.1f} MB")
                        if result.returncode != 0:
                            print(f"   ⚠️ FFmpeg警告: {result.stderr.decode() if result.stderr else 'Unknown'}")
                        
                        # 删除临时文件
                        try:
                            video_raw_path.unlink()
                            audio_path.unlink()
                        except:
                            pass
                    else:
                        # 合并失败，尝试只处理视�??
                        print(f"⚠️ 音�?�合并失�?: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                        self._save_video_only(video_raw_path, final_path, actual_fps, recording_duration)
                else:
                    # 没有音�?�，�?校�?��?��?�FPS
                    self._save_video_only(video_raw_path, final_path, actual_fps, recording_duration)
                    
            except Exception as e:
                print(f"⚠️ 视�?��?�理出错: {e}")
                # 保留原�?�文�?
                if video_raw_path.exists():
                    try:
                        video_raw_path.rename(final_path)
                        print(f"�? 保留原�?�录�?: {final_path}")
                    except:
                        pass
        
        # 4. 停�?�捕获线�?
        self.is_running = False
        time.sleep(0.2)
        
        # 5. 释放所有摄像头
        for cap in self.cameras:
            cap.release()
        
        self.cameras = []
        self.frame_queues = []
        self.capture_threads = []
        
        print("�? 所有摄像头已释放\n")
    
    def _save_video_only(self, raw_path, final_path, actual_fps, duration):
        """�?保存视�?�（校�??FPS�?"""
        import subprocess
        
        try:
            cmd = [
                'ffmpeg', '-y', '-loglevel', 'error',
                '-r', str(actual_fps),
                '-i', str(raw_path),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-crf', '23',
                '-r', '30',
                '-movflags', '+faststart',
                str(final_path)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            
            if result.returncode == 0 and final_path.exists():
                file_size = final_path.stat().st_size / (1024 * 1024)
                print(f"�? 录制已保存（仅�?��?�）: {final_path}")
                print(f"   时长: {duration:.1f}�?, 大小: {file_size:.1f} MB")
                try:
                    raw_path.unlink()
                except:
                    pass
            else:
                # �?换失败，重命名原始文�?
                raw_path.rename(final_path)
                print(f"�? 保留原�?�录�?: {final_path}")
        except:
            raw_path.rename(final_path)
            print(f"�? 保留原�?�录�?: {final_path}")
    
    def isOpened(self) -> bool:
        """检查是否有�?用的摄像�?"""
        return len(self.cameras) > 0
    
    def get(self, prop_id: int):
        """获取属性（兼�?�cv2.VideoCapture接口�?"""
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return self.stitched_width
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return self.stitched_height
        elif prop_id == cv2.CAP_PROP_FPS:
            return self.target_fps
        elif prop_id == cv2.CAP_PROP_FOURCC:
            return cv2.VideoWriter_fourcc('M','J','P','G')
        return 0
    
    def set(self, prop_id: int, value):
        """设置属性（兼�?�cv2.VideoCapture接口�?- 多摄像头模式下忽略�?�置"""
        # 多摄像头模式下，分辨率等参数在初始化时已设定
        # 这里�?返回True表示"设置成功"，但实际不做任何改变
        return True


# 测试代码
if __name__ == "__main__":
    print("🧪 测试多摄像头捕获模块\n")
    
    # 创建捕获�?
    multicam = MultiCameraCapture(
        camera_indices=[0, 1, 2, 3],
        target_fps=60,
        resolution_per_camera=(1920, 1080)
    )
    
    # 打开摄像�?
    if not multicam.open_cameras():
        print("�? 无法打开摄像头，退�?")
        exit(1)
    
    # �?动捕获线�?
    multicam.start_capture_threads()
    
    print("🎬 预�?�拼接画�? (�? 'q' 退�?)...\n")
    
    try:
        frame_count = 0
        start_time = time.time()
        
        while True:
            ret, frame = multicam.read()
            
            if not ret:
                print("⚠️  读取帧失�?")
                break
            
            # 显示FPS
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
                cv2.putText(frame, f"FPS: {fps:.1f}", (30, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            
            # 缩小显示�?4K�?大）
            display_frame = cv2.resize(frame, (1920, 1080))
            cv2.imshow('Multi-Camera 2x2 Grid', display_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  用户�?�?")
    
    finally:
        multicam.release()
        cv2.destroyAllWindows()
        
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"📊 平均 FPS: {avg_fps:.1f}")
        print("�? 测试完成")
