#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Camera auto-select helper for Ubuntu (V4L2).

Goal:
- Auto select cameras whose name contains a given substring (default: "ARC International Camera").
- Configure each selected camera to 1280x720 @ 30fps.

Why not use OpenCV for naming?
- OpenCV does not expose stable device names on Linux.
- We query /sys/class/video4linux for the card name and map it to /dev/videoN.

Usage:
  python3 camera_autoselect.py --name "ARC International Camera" --max 10 --limit 4

Outputs JSON to stdout:
  {"devices": [{"index": 0, "path": "/dev/video0", "name": "..."}, ...]}
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from typing import List, Optional

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None  # type: ignore


@dataclass
class VideoDevice:
    index: int
    path: str
    name: str


_NAME_CLEAN_RE = re.compile(r"\s+")


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except Exception:
        return ""


def _is_openable_capture_node(index: int) -> bool:
    """Return True if OpenCV can open this /dev/videoN as a capture stream."""
    if cv2 is None:
        # If opencv isn't installed, don't filter; behave like older version.
        return True
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    ok = bool(cap.isOpened())
    if ok:
        cap.release()
        return True
    cap.release()
    return False


def _matches_vidpid(index: int, vidpid: str) -> bool:
    """Match USB vendor:product from sysfs uevent PRODUCT=vvvv/pppp/...."""
    if not vidpid:
        return True

    def norm(x: str) -> str:
        x = (x or "").strip().lower()
        if x.startswith("0x"):
            x = x[2:]
        x = x.lstrip("0") or "0"
        return x

    needle = vidpid.strip().lower()
    if ":" in needle:
        n_vid, n_pid = needle.split(":", 1)
        n_vid, n_pid = norm(n_vid), norm(n_pid)
    else:
        return False

    uevent = _read_text(f"/sys/class/video4linux/video{index}/device/uevent")
    if not uevent:
        return False

    # Example: PRODUCT=5a3/9230/100
    for line in uevent.splitlines():
        if line.startswith("PRODUCT="):
            prod = line.split("=", 1)[1].strip().lower()
            parts = prod.split("/")
            if len(parts) >= 2:
                got_vid, got_pid = norm(parts[0]), norm(parts[1])
                return (got_vid == n_vid) and (got_pid == n_pid)
    return False


def list_video_devices(max_index: int = 20) -> List[VideoDevice]:
    devices: List[VideoDevice] = []
    for idx in range(max_index):
        dev_path = f"/dev/video{idx}"
        if not os.path.exists(dev_path):
            continue

        sys_name = f"/sys/class/video4linux/video{idx}/name"
        name = _read_text(sys_name)
        name = _NAME_CLEAN_RE.sub(" ", name).strip()
        if not name:
            name = dev_path

        devices.append(VideoDevice(index=idx, path=dev_path, name=name))
    return devices


def select_devices(
    name_contains: str = "ARC International Camera",
    max_index: int = 20,
    limit: Optional[int] = None,
    vidpid: str = "",
    require_openable: bool = True,
) -> List[VideoDevice]:
    needle = (name_contains or "").strip().lower()
    items = list_video_devices(max_index=max_index)

    matched = [d for d in items if needle and needle in (d.name or "").lower()]

    # Optional USB filter (useful when /sys name is generic)
    if vidpid:
        matched = [d for d in matched if _matches_vidpid(d.index, vidpid)]

    # Filter out non-capture nodes (many UVC devices expose multiple /dev/video* per camera)
    if require_openable:
        matched = [d for d in matched if _is_openable_capture_node(d.index)]

    if limit is not None:
        matched = matched[: max(0, int(limit))]
    return matched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--name",
        default="ARC International Camera",
        help="Substring to match in /sys/class/video4linux/*/name",
    )
    ap.add_argument("--max", type=int, default=20, help="Max /dev/video index to probe")
    ap.add_argument("--limit", type=int, default=4, help="Limit number of devices returned")
    ap.add_argument(
        "--vidpid",
        default="",
        help="Optional USB vendor:product filter, e.g. 05a3:9230",
    )
    ap.add_argument(
        "--no-openable-check",
        action="store_true",
        help="Do not filter by OpenCV-openable capture nodes",
    )
    args = ap.parse_args()

    devices = select_devices(
        name_contains=args.name,
        max_index=args.max,
        limit=args.limit,
        vidpid=args.vidpid,
        require_openable=not args.no_openable_check,
    )
    print(json.dumps({"devices": [d.__dict__ for d in devices]}, ensure_ascii=False, indent=2))

    return 0 if devices else 2


if __name__ == "__main__":
    raise SystemExit(main())
