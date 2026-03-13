#!/usr/bin/env python3
"""
Gemini API 키 환경변수 업데이트 스크립트
사용법: python3 update_gemini_key.py <새_API_키>

이 스크립트는:
1. PM2 ecosystem.config.js의 GEMINI_API_KEY 업데이트
2. ~/.bashrc의 환경변수 업데이트
3. PM2 재시작 (--update-env)

n8n 워크플로우는 {{ $env.GEMINI_API_KEY }}를 사용하므로
코드 변경 없이 키만 교체됩니다.
"""
import sys, os, re, subprocess

if len(sys.argv) < 2:
    print("Usage: python3 update_gemini_key.py <NEW_GEMINI_API_KEY>")
    sys.exit(1)

new_key = sys.argv[1]

# Validate key format
if not new_key.startswith('AIzaSy') or len(new_key) < 35:
    print(f"ERROR: Invalid Gemini API key format: {new_key[:10]}...")
    sys.exit(1)

# 1. Update ecosystem.config.js
eco_path = os.path.expanduser("~/ecosystem.config.js")
with open(eco_path, 'r') as f:
    content = f.read()

content = re.sub(
    r'GEMINI_API_KEY:\s*"[^"]*"',
    f'GEMINI_API_KEY: "{new_key}"',
    content
)

with open(eco_path, 'w') as f:
    f.write(content)
print(f"[1/3] ecosystem.config.js updated")

# 2. Update .bashrc
bashrc = os.path.expanduser("~/.bashrc")
with open(bashrc, 'r') as f:
    lines = f.readlines()

found = False
with open(bashrc, 'w') as f:
    for line in lines:
        if 'GEMINI_API_KEY' in line:
            f.write(f'export GEMINI_API_KEY="{new_key}"\n')
            found = True
        else:
            f.write(line)
    if not found:
        f.write(f'export GEMINI_API_KEY="{new_key}"\n')
print(f"[2/3] .bashrc updated")

# 3. Restart PM2 with --update-env
result = subprocess.run(
    ['pm2', 'restart', eco_path, '--update-env'],
    capture_output=True, text=True
)
print(f"[3/3] PM2 restarted")
print(result.stdout[-200:] if result.stdout else result.stderr[-200:])

print(f"\nDone! New key: {new_key[:10]}...{new_key[-4:]}")
print("n8n 워크플로우는 $env.GEMINI_API_KEY를 참조하므로 자동 적용됩니다.")
