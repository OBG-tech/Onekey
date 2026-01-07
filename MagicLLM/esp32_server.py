import socket
import select
import time
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

HOST = ''        
PORT = 5000      

# TCP Keepalive 参数（Linux）
TCP_KEEPIDLE = 4   # socket.TCP_KEEPIDLE
TCP_KEEPINTVL = 5  # socket.TCP_KEEPINTVL  
TCP_KEEPCNT = 6    # socket.TCP_KEEPCNT

# 日志文件路径
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "button_log.txt")

def trigger_key_moment(button_number):
    """通过 HTTP API 触发关键时刻"""
    ports = [8082, 8080]  # Try 8082 (multicam) first, then 8080 (default)
    data = {
        "note": f"Button {button_number} Pressed"
    }
    json_data = json.dumps(data).encode('utf-8')
    
    for port in ports:
        url = f"http://localhost:{port}/api/mark_moment"
        try:
            req = urllib.request.Request(
                url, 
                data=json_data, 
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    print(f"✅ 已触发关键时刻 ({url}): 按钮 {button_number}")
                    return  # Success
        except urllib.error.URLError as e:
            print(f"   [Port {port}] Connection failed: {e.reason}")
        except Exception as e:
            print(f"   [Port {port}] Error: {e}")

    print(f"⚠️ 触发关键时刻失败 (尝试端口 {ports}): 请确保 integrated_system.py 正运行在 8080 或 8082 端口")

def save_button_press(button_number):
    """保存按钮消息和时间到文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{timestamp} - 按钮: {button_number}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)
    print(f"已记录: {log_line.strip()}")
    
    # 触发关键时刻
    trigger_key_moment(button_number)

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # 允许端口重用，避免 "Address already in use" 错误
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)  # 增加 backlog
    server.setblocking(False)  # 非阻塞模式
    
    print(f"服务器启动，监听端口 {PORT} ...")
    print("等待 ESP32 连接（可以先启动服务器，ESP32 连接 WiFi 后会自动连接）...")
    
    clients = {}  # {socket: (addr, last_activity_time)}
    
    def close_client(sock, reason=""):
        """安全关闭客户端连接"""
        if sock in clients:
            addr = clients[sock][0]
            try:
                sock.close()
            except:
                pass
            del clients[sock]
            print(f"连接已关闭 [{addr}]: {reason}")
            print(f"当前连接数: {len(clients)}")
    
    def close_old_connections_from_ip(new_ip):
        """关闭来自同一 IP 的旧连接（ESP32 重启时）"""
        to_close = []
        for sock, (addr, _) in clients.items():
            if addr[0] == new_ip:
                to_close.append(sock)
        for sock in to_close:
            close_client(sock, "同 IP 新连接，关闭旧连接")
    
    def check_dead_connections():
        """检测并关闭死连接"""
        now = time.time()
        to_close = []
        for sock, (addr, last_time) in clients.items():
            # 如果超过 30 秒没有活动，尝试发送心跳检测
            if now - last_time > 30:
                try:
                    # 发送一个心跳包检测连接
                    sock.send(b'\x00')
                except (ConnectionResetError, BrokenPipeError, OSError):
                    to_close.append((sock, "心跳检测失败"))
                except BlockingIOError:
                    pass  # 发送缓冲区满，连接可能还活着
        for sock, reason in to_close:
            close_client(sock, reason)
    
    last_check_time = time.time()
    
    try:
        while True:
            # 使用 select 同时监听服务器和所有客户端
            readable = [server] + list(clients.keys())
            try:
                ready, _, _ = select.select(readable, [], [], 1.0)
            except select.error:
                continue
            
            # 每 5 秒检测一次死连接
            now = time.time()
            if now - last_check_time > 5:
                check_dead_connections()
                last_check_time = now
            
            for sock in ready:
                if sock is server:
                    # 新连接
                    try:
                        conn, addr = server.accept()
                        
                        # 关闭来自同一 IP 的旧连接
                        close_old_connections_from_ip(addr[0])
                        
                        conn.setblocking(False)
                        # 启用 TCP keepalive 并设置激进的参数
                        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                        try:
                            # 5秒后开始发送 keepalive
                            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPIDLE, 5)
                            # 每 2 秒发送一次
                            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPINTVL, 2)
                            # 3 次失败后断开
                            conn.setsockopt(socket.IPPROTO_TCP, TCP_KEEPCNT, 3)
                        except:
                            pass  # 某些系统可能不支持这些选项
                        
                        clients[conn] = (addr, time.time())
                        print(f'\nESP32 已连接: {addr}')
                        print(f"当前连接数: {len(clients)}")
                    except Exception as e:
                        print(f"接受连接时出错: {e}")
                else:
                    # 现有连接有数据
                    if sock not in clients:
                        continue
                    addr = clients[sock][0]
                    try:
                        data = sock.recv(1024)
                        if data:
                            # 过滤掉心跳包
                            if data != b'\x00':
                                msg = data.decode(errors='ignore').strip()
                                print(f"收到数据 [{addr}]: {msg}")
                                # 如果是 1-10 的数字，保存到文件
                                if msg.isdigit() and 1 <= int(msg) <= 10:
                                    save_button_press(msg)
                            # 更新活动时间
                            clients[sock] = (addr, time.time())
                        else:
                            # 连接正常关闭
                            close_client(sock, "对方关闭连接")
                    except ConnectionResetError:
                        close_client(sock, "连接被重置")
                    except BlockingIOError:
                        pass
                    except Exception as e:
                        close_client(sock, f"错误: {e}")
                            
    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        for sock in list(clients.keys()):
            try:
                sock.close()
            except:
                pass
        server.close()

if __name__ == "__main__":
    start_server()
