import sys, os

target_path = sys.argv[1]
os.makedirs(os.path.dirname(target_path), exist_ok=True)
content = sys.stdin.read()
with open(target_path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'Wrote {target_path}')
