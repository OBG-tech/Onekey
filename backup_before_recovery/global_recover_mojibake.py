
import os
import glob
import shutil

# Backup current state
os.makedirs("backup_before_recovery", exist_ok=True)
py_files = glob.glob("*.py")
for f in py_files:
    shutil.copy2(f, os.path.join("backup_before_recovery", f))

def recover_line(line):
    # Try perfect recovery
    try:
        # Convert the mojibake chars back to bytes using gb18030
        bytes_data = line.encode('gb18030')
        # Interpret those bytes as utf-8
        return bytes_data.decode('utf-8')
    except:
        # If failed, it might be that some chars were lost (replaced by ?)
        # We try to recover what we can
        try:
            bytes_data = line.encode('gb18030', errors='ignore')
            return bytes_data.decode('utf-8', errors='replace')
        except:
            return line

def process_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    new_lines = []
    changes = 0
    
    for line in lines:
        # Heuristic: if line contains characters commonly seen in this specific mojibake
        # Common GBK-as-UTF8 mojibake often produces chars like 浣, 涓, 瀛, 梊, 绋, 绯, etc.
        # But simple check: just try to recover. If result is valid UTF-8 and looks "better" (e.g. valid chinese), use it.
        # Or blindly apply the transform?
        # Blind application is dangerous if the file has MIXED content (some valid, some mojibake).
        # But my previous "fix" likely converted the WHOLE file assuming it was GB18030.
        # So the WHOLE file (except maybe pure ASCII parts) is likely shifted.
        # Pure ASCII parts: ASCII -> encode gb18030 -> bytes (same) -> decode utf-8 -> same.
        # So it is safe to apply to the whole file!
        
        recovered = recover_line(line)
        
        # Sanity check: if recovery results in empty string where original wasn't, or major length change?
        # Actually, recovery usually shrinks length (3 chars "浣" -> 1 char "你" approx).
        
        if recovered != line:
            new_lines.append(recovered)
            changes += 1
        else:
            new_lines.append(line)
            
    if changes > 0:
        print(f"Recovered {changes} lines in {filename}")
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("".join(new_lines))
    else:
        print(f"No changes in {filename}")

files_to_process = [
    "key_moments_manager.py",
    "updated_stop_script.py", # User mentioned this
    "integrated_system.py",
    "start_multicam_system.py",
    "multi_camera_capture.py"
]

# Add all files I touched previously
files_to_process.extend([
    "reprocess_moments.py",
    "check_all_py_encoding.py", # self
    "fix_all_encoding.py" # self
])

# Remove duplicates and limit to existing
files_to_process = list(set(files_to_process))
existing_files = [f for f in files_to_process if os.path.exists(f)]

print(f"Processing {len(existing_files)} files...")
for f in existing_files:
    process_file(f)
