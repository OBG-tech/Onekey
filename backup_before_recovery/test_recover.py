
import sys

def try_recover(text):
    try:
        # Hypothesis: text is mojibake from UTF-8 bytes interpreted as GB18030
        # So we encode back to GB18030 to get original bytes
        b = text.encode('gb18030')
        # Then decode those bytes as UTF-8
        return b.decode('utf-8')
    except Exception as e:
        return f"ERROR: {e}"

def check_file(filename, line_num):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    if line_num > len(lines):
        print("Line number out of range")
        return

    line = lines[line_num - 1] # 1-based index
    print(f"Original line {line_num}: {line.strip()}")
    
    recovered = try_recover(line)
    print(f"Recovered line {line_num}: {recovered.strip()}")

if __name__ == "__main__":
    check_file("/home/artinx/onekey/key_moments_manager.py", 3907) # system = ... 
    check_file("/home/artinx/onekey/key_moments_manager.py", 3917) # SyntaxError line
