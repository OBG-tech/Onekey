# ===== 文件2：Ubuntu / Python 服务端 esp32_server.py（无 emoji，可直接运行）=====
# -*- coding: utf-8 -*-
import socket
import select
import time
import os
import requests
from datetime import datetime

HOST = ''
PORT = 5000

TCP_KEEPIDLE = getattr(socket, "TCP_KEEPIDLE", 4)
TCP_KEEPINTVL = getattr(socket, "TCP_KEEPINTVL", 5)
TCP_KEEPCNT = getattr(socket, "TCP_KEEPCNT", 6)
TCP_USER_TIMEOUT = getattr(socket, "TCP_USER_TIMEOUT", 18)  # Linux 常见；不支持则跳过

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "button_log.txt")
API_BASE_URL = "http://localhost:8082"


def trigger_key_moment(button_number):
    """触发创建关键时刻（带重试机制）"""
    max_retries = 3
    retry_delay = 0.5

    for attempt in range(max_retries):
        try:
            url = f"{API_BASE_URL}/api/mark_moment"
            payload = {"note": f"button {button_number}"}
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                print(f"Moment created: button {button_number} (try {attempt + 1}/{max_retries})")
                return True
            else:
                print(f"Moment create failed: {response.status_code} (try {attempt + 1}/{max_retries})")

        except requests.exceptions.Timeout:
            if attempt == max_retries - 1:
                print(f"API timeout, button {button_number} recorded but moment may be delayed")
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"API call failed: {e}")

        if attempt < max_retries - 1:
            time.sleep(retry_delay)

    return False


def save_button_press(button_number):
    """保存按钮消息和时间到文件，并触发创建关键时刻"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{timestamp} - button: {button_number}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)
    print(f"Recorded: {log_line.strip()}")

    trigger_key_moment(button_number)


def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    server.setblocking(False)

    print(f"Server started, listening on {PORT} ...")
    print("Waiting for ESP32 connection...")

    # clients: {sock: {"addr": (ip,port), "last": ts, "buf": bytes}}
    clients = {}

    def close_client(sock, reason=""):
        if sock in clients:
            addr = clients[sock]["addr"]
            try:
                sock.close()
            except Exception:
                pass
            del clients[sock]
            print(f"Connection closed [{addr}]: {reason}")
            print(f"Current connections: {len(clients)}")

    def close_old_connections_from_ip(new_ip):
        to_close = []
        for s, info in clients.items():
            if info["addr"][0] == new_ip:
                to_close.append(s)
        for s in to_close:
            close_client(s, "New connection from same IP, closing old one")

    def tune_socket(conn: socket.socket):
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPIDLE, 5)
            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPINTVL, 2)
            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPCNT, 3)
        except Exception:
            pass

        # 可选：更快识别死链（不支持就忽略）
        try:
            conn.setsockopt(socket.IPPROTO_TCP, TCP_USER_TIMEOUT, 15000)  # ms
        except Exception:
            pass

    try:
        while True:
            readable = [server] + list(clients.keys())
            try:
                ready, _, _ = select.select(readable, [], [], 1.0)
            except Exception:
                continue

            for sock in ready:
                if sock is server:
                    try:
                        conn, addr = server.accept()
                        close_old_connections_from_ip(addr[0])

                        conn.setblocking(False)
                        tune_socket(conn)

                        clients[conn] = {"addr": addr, "last": time.time(), "buf": b""}
                        print(f"ESP32 connected: {addr}")
                        print(f"Current connections: {len(clients)}")
                    except Exception as e:
                        print(f"Accept error: {e}")
                else:
                    if sock not in clients:
                        continue
                    addr = clients[sock]["addr"]
                    try:
                        data = sock.recv(1024)
                        if data:
                            clients[sock]["last"] = time.time()
                            clients[sock]["buf"] += data

                            # ESP32 println -> line based
                            while b"\n" in clients[sock]["buf"]:
                                line, rest = clients[sock]["buf"].split(b"\n", 1)
                                clients[sock]["buf"] = rest

                                msg = line.decode(errors="ignore").strip()
                                if not msg:
                                    continue

                                if msg == "PING":
                                    continue

                                print(f"Recv [{addr}]: {msg}")

                                if msg.isdigit() and 1 <= int(msg) <= 10:
                                    save_button_press(msg)
                        else:
                            close_client(sock, "Peer closed")
                    except ConnectionResetError:
                        close_client(sock, "Connection reset")
                    except BlockingIOError:
                        pass
                    except Exception as e:
                        close_client(sock, f"Error: {e}")

    except KeyboardInterrupt:
        print("Server stopped")
    finally:
        for s in list(clients.keys()):
            try:
                s.close()
            except Exception:
                pass
        server.close()


if __name__ == "__main__":
    start_server()
