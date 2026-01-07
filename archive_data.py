#!/usr/bin/env python3
"""
智能视频分析系统 - 数据归档工具
按日期归档所有历史数据，包括视频、音频、关键时刻、对话、直播数据、人物信息和日志
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime
import argparse
import sys

class DataArchiver:
    def __init__(self, source_dir="integrated_data", archive_base="archives", dry_run=False):
        self.source_dir = Path(source_dir)
        self.archive_base = Path(archive_base)
        self.dry_run = dry_run
        self.stats = {
            "total_files": 0,
            "archived_files": 0,
            "skipped_files": 0,
            "errors": 0
        }
        
    def extract_date_from_timestamp(self, timestamp_str):
        """从文件名中的Unix时间戳提取日期"""
        try:
            timestamp = int(timestamp_str)
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None
    
    def extract_date_from_filename(self, filename):
        """从文件名提取日期"""
        # 处理各种文件名格式
        # 格式1: anchor_1765559797_1385.jpg
        # 格式2: ai_1765506604_4472.jpg
        # 格式3: multimodal_1765615706_3890.jpg
        parts = filename.split('_')
        for part in parts:
            if part.isdigit() and len(part) == 10:  # Unix时间戳
                return self.extract_date_from_timestamp(part)
        return None
    
    def get_file_date(self, file_path):
        """获取文件日期（优先从文件名，其次从修改时间）"""
        # 先尝试从文件名提取
        date = self.extract_date_from_filename(file_path.name)
        if date:
            return date
        
        # 如果文件名没有时间戳，使用文件修改时间
        try:
            mtime = file_path.stat().st_mtime
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
        except:
            return None
    
    def create_archive_structure(self, date, category):
        """创建归档目录结构: archives/YYYY-MM-DD/category/"""
        archive_dir = self.archive_base / date / category
        if not self.dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
        return archive_dir
    
    def archive_file(self, source_file, target_dir):
        """归档单个文件"""
        target_path = target_dir / source_file.name
        
        if self.dry_run:
            print(f"  [DRY RUN] 将归档: {source_file} -> {target_path}")
            return True
        
        try:
            # 复制文件（保留原文件）
            shutil.copy2(source_file, target_path)
            return True
        except Exception as e:
            print(f"  ❌ 错误: 无法归档 {source_file}: {e}")
            self.stats["errors"] += 1
            return False
    
    def archive_category(self, category_name, category_path):
        """归档一个数据类别"""
        print(f"\n📁 处理类别: {category_name}")
        
        if not category_path.exists():
            print(f"  ⚠️  目录不存在，跳过")
            return
        
        files_by_date = {}
        
        # 遍历所有文件
        for file_path in category_path.rglob('*'):
            if file_path.is_file():
                self.stats["total_files"] += 1
                
                # 获取文件日期
                date = self.get_file_date(file_path)
                if not date:
                    print(f"  ⚠️  无法确定日期: {file_path.name}")
                    self.stats["skipped_files"] += 1
                    continue
                
                # 按日期分组
                if date not in files_by_date:
                    files_by_date[date] = []
                
                # 保留子目录结构（如snapshots/person_1/）
                relative_path = file_path.relative_to(category_path)
                files_by_date[date].append((file_path, relative_path))
        
        # 归档每个日期的文件
        for date, files in sorted(files_by_date.items()):
            archive_dir = self.create_archive_structure(date, category_name)
            print(f"  📅 {date}: {len(files)} 个文件")
            
            for source_file, relative_path in files:
                # 保持子目录结构
                target_dir = archive_dir / relative_path.parent
                if not self.dry_run:
                    target_dir.mkdir(parents=True, exist_ok=True)
                
                if self.archive_file(source_file, target_dir):
                    self.stats["archived_files"] += 1
    
    def archive_logs(self):
        """归档日志文件"""
        print(f"\n📋 处理日志文件")
        
        log_files = [
            "button_log.txt",
            "debug_startup.log",
            "context.txt"
        ]
        
        base_dir = Path(".")
        for log_file in log_files:
            log_path = base_dir / log_file
            if not log_path.exists():
                continue
            
            self.stats["total_files"] += 1
            date = self.get_file_date(log_path)
            if date:
                archive_dir = self.create_archive_structure(date, "logs")
                print(f"  📅 {date}: {log_file}")
                if self.archive_file(log_path, archive_dir):
                    self.stats["archived_files"] += 1
            else:
                self.stats["skipped_files"] += 1
    
    def run(self):
        """执行归档"""
        print("=" * 60)
        print("智能视频分析系统 - 数据归档工具")
        print("=" * 60)
        
        if self.dry_run:
            print("\n⚠️  试运行模式（不会实际复制文件）\n")
        
        # 归档各个数据类别
        categories = {
            "key_moments": "关键时刻",
            "audio": "音频",
            "transcripts": "转录",
            "meeting_notes": "会议笔记",
            "snapshots": "人物快照",
            "face_database": "人脸数据库",
            "key_frames": "关键帧",
            "analysis_results": "分析结果"
        }
        
        for cat_dir, cat_name_cn in categories.items():
            self.archive_category(cat_dir, self.source_dir / cat_dir)
        
        # 归档日志文件
        self.archive_logs()
        
        # 打印统计
        print("\n" + "=" * 60)
        print("归档完成统计")
        print("=" * 60)
        print(f"总文件数: {self.stats['total_files']}")
        print(f"已归档: {self.stats['archived_files']}")
        print(f"跳过: {self.stats['skipped_files']}")
        print(f"错误: {self.stats['errors']}")
        
        if not self.dry_run:
            print(f"\n✅ 归档保存在: {self.archive_base.absolute()}")
        
        return self.stats["errors"] == 0


def main():
    parser = argparse.ArgumentParser(
        description="按日期归档智能视频分析系统的所有历史数据"
    )
    parser.add_argument(
        "--source",
        default="integrated_data",
        help="源数据目录（默认: integrated_data）"
    )
    parser.add_argument(
        "--output",
        default="archives",
        help="归档输出目录（默认: archives）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式，仅显示将要执行的操作"
    )
    parser.add_argument(
        "--date",
        help="仅归档指定日期的数据（格式: YYYY-MM-DD）"
    )
    
    args = parser.parse_args()
    
    archiver = DataArchiver(
        source_dir=args.source,
        archive_base=args.output,
        dry_run=args.dry_run
    )
    
    success = archiver.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
