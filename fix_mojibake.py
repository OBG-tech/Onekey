
import sys

filepath = 'integrated_system.py'

with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'Stopping services...' in line:
        print(f"Line {i+1}: {repr(line)}")
        if 'print("' in line and 'Stopping services' in line:
            lines[i] = '    print("🔌 Stopping services...", end="\\r")\n'
            print("Fixed Line", i+1)
    
    if 'except KeyboardInterrupt:' in line:
        # Check next line
        next_line = lines[i+1]
        if 'print(' in next_line and '73' in next_line: # 73 seen in read_file output
             print(f"Line {i+2}: {repr(next_line)}")
             lines[i+1] = '        print("\\n👋 用户退出")\n'
             print("Fixed Line", i+2)
        # Also check for other mojibake keys
        if 'print(' in next_line and 'û' in next_line:
             print(f"Line {i+2}: {repr(next_line)}")
             lines[i+1] = '        print("\\n👋 用户退出")\n'
             print("Fixed Line", i+2)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Done.")
