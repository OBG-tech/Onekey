#!/usr/bin/env python3
"""camera_utils.py

Ubuntu/Linux camera helpers.

Goals:
- Find usable V4L2 cameras on Ubuntu 22.04.
- Optionally filter by USB VID:PID (e.g. 05a3:9230 ARC International Camera).
- Return indices suitable for OpenCV (cv2.VideoCapture).

Notes:
- On Linux, OpenCV generally maps indices to /dev/videoN (V4L2).
- USB mapping is not guaranteed to be stable across reboots; prefer using
  /dev/v4l/by-id or /dev/v4l/by-path for persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import os
import re
import subprocess

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore


@dataclass(frozen=True)
class CameraCandidate:
    index: int
    devnode: str
    backend: str = ""


def _list_video_devnodes() -> List[str]:
    devs = sorted(Path("/dev").glob("video*"))
    # Keep only /dev/videoN
    out: List[str] = []
    for p in devs:
        m = re.fullmatch(r"video(\d+)", p.name)
        if m:
            out.append(f"/dev/{p.name}")
    return out


def _v4l2_usb_id_map() -> dict[str, str]:
    """Return {"/dev/videoN": "vvvv:pppp"} using v4l2-ctl if available."""
    mapping: dict[str, str] = {}
    try:
        proc = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return mapping

    # Typical output:
    #   USB2.0 HD UVC WebCam: USB2.0 HD (usb-0000:00:14.0-1):
    #	/dev/video0
    #	/dev/video1
    block = proc.stdout.splitlines()

    # We can't reliably parse VID:PID from v4l2-ctl output alone.
    # Best-effort: read udev properties for each /dev/video*.
    for dev in _list_video_devnodes():
        vidpid = get_usb_vidpid_for_devnode(dev)
        if vidpid:
            mapping[dev] = vidpid
    return mapping


def get_usb_vidpid_for_devnode(devnode: str) -> Optional[str]:
    """Get USB VID:PID for a /dev/videoN device via udevadm.

    Returns lowercase "vvvv:pppp" or None.
    """
    try:
        proc = subprocess.run(
            ["udevadm", "info", "--query=property", f"--name={devnode}"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    props = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()

    vid = props.get("ID_VENDOR_ID")
    pid = props.get("ID_MODEL_ID")
    if vid and pid:
        return f"{vid.lower()}:{pid.lower()}"

    return None


def _try_open(index: int, preferred_backends: Sequence[int]) -> Optional[CameraCandidate]:
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is not available in this environment")

    # Try preferred backends first (V4L2 first on Linux), then default.
    backends_to_try: List[Optional[int]] = list(preferred_backends) + [None]

    for api in backends_to_try:
        cap = cv2.VideoCapture(index) if api is None else cv2.VideoCapture(index, api)
        try:
            if not cap.isOpened():
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            try:
                backend = cap.getBackendName()
            except Exception:
                backend = ""

            devnode = f"/dev/video{index}" if os.path.exists(f"/dev/video{index}") else str(index)
            return CameraCandidate(index=index, devnode=devnode, backend=backend)
        finally:
            try:
                cap.release()
            except Exception:
                pass

    return None


def find_usable_cameras(
    max_index: int = 16,
    require_read_frame: bool = True,
    prefer_v4l2: bool = True,
    usb_vidpid_whitelist: Optional[Iterable[str]] = None,
    limit: Optional[int] = None,
) -> List[CameraCandidate]:
    """Scan OpenCV indices and return usable cameras.

    Args:
        max_index: scan indices [0, max_index).
        require_read_frame: must successfully read at least one frame.
        prefer_v4l2: try cv2.CAP_V4L2 first.
        usb_vidpid_whitelist: if provided, only return cameras whose udev
            VID:PID matches one of these strings (case-insensitive).
            Example: ["05a3:9230"].
        limit: if provided, stop after finding this many cameras.

    Returns:
        List of candidates in increasing index order.
    """
    if cv2 is None:
        raise RuntimeError("OpenCV (cv2) is not available in this environment")

    preferred_backends: List[int] = []
    if prefer_v4l2 and hasattr(cv2, "CAP_V4L2"):
        preferred_backends.append(int(cv2.CAP_V4L2))

    allowed: Optional[set[str]] = None
    if usb_vidpid_whitelist is not None:
        allowed = {x.strip().lower() for x in usb_vidpid_whitelist if str(x).strip()}

    found: List[CameraCandidate] = []
    for idx in range(max_index):
        cand = _try_open(idx, preferred_backends)
        if not cand:
            continue

        if not require_read_frame:
            # If not requiring a frame, still keep it (already opened ok).
            pass

        if allowed is not None:
            devnode = cand.devnode
            if devnode.startswith("/dev/"):
                vidpid = get_usb_vidpid_for_devnode(devnode)
            else:
                vidpid = None
            if vidpid is None or vidpid.lower() not in allowed:
                continue

        found.append(cand)
        if limit is not None and len(found) >= limit:
            break

    return found


def auto_select_camera_index(
    prefer_usb_vidpid: Optional[str] = None,
    max_index: int = 16,
) -> int:
    """Return a single best camera index.

    If prefer_usb_vidpid is provided (e.g. "05a3:9230"), pick the first usable
    camera matching that VID:PID. Otherwise pick the first usable camera.
    """
    whitelist = [prefer_usb_vidpid] if prefer_usb_vidpid else None
    cams = find_usable_cameras(max_index=max_index, usb_vidpid_whitelist=whitelist, limit=1)
    if cams:
        return cams[0].index

    # fallback: any camera
    cams2 = find_usable_cameras(max_index=max_index, limit=1)
    if cams2:
        return cams2[0].index

    raise RuntimeError("No usable camera found (no /dev/video* device opens and returns frames)")
