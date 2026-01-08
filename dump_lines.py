
with open('key_moments_manager.py', 'rb') as f:
    lines = f.readlines()
    
start = 2600
end = 2700
if len(lines) < start:
    print("File too short")
else:
    for i in range(start, min(end, len(lines))):
        print(f"{i}: {lines[i]}")
