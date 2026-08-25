import re

with open('app.py', 'r') as f:
    lines = f.readlines()

new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    new_lines.append(line)

    # 在 for row in rows: 后插入一行，补上 credit_score 默认值
    if line.strip().startswith('for row in rows:'):
        indent = len(line) - len(line.lstrip(' '))
        new_lines.append(' ' * (indent + 4) + 'd["credit_score"] = d["credit_score"] or 0\n')

    # 在 for p in posts: 后插入一行，补上 credit_score 默认值
    if line.strip().startswith('for p in posts:'):
        indent = len(line) - len(line.lstrip(' '))
        new_lines.append(' ' * (indent + 4) + 'p["credit_score"] = p["credit_score"] or 0\n')

    i += 1

with open('app.py', 'w') as f:
    f.writelines(new_lines)

# 替换点赞 SQL（直接替换，不影响缩进）
with open('app.py', 'r') as f:
    content = f.read()
content = content.replace('credit_score = credit_score + 2', 'credit_score = COALESCE(credit_score, 0) + 2')
with open('app.py', 'w') as f:
    f.write(content)

print("✅ 修复完成！")
