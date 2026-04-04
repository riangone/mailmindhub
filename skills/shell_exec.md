---
name: shell_exec
description: 执行 shell 命令并返回输出
description_ja: シェルコマンドを実行して出力を返す
description_en: Execute shell commands and return output
category: automation
keywords:
  - shell
  - bash
  - 执行命令
  - run command
  - コマンド実行
  - terminal
params:
  command:
    type: string
    required: true
    description: 要执行的 shell 命令
  cwd:
    type: string
    required: false
    description: 工作目录（可选）
---

# Shell 命令执行

## 任务
执行以下 shell 命令并返回输出：

```bash
{{command}}
```

{% if cwd %}
工作目录：`{{cwd}}`
{% endif %}

## 要求
1. 直接使用 CLI 工具能力执行命令
2. 返回完整的 stdout 和 stderr 输出
3. 返回退出码（exit code）
4. 如果命令执行失败，说明错误原因
5. 危险命令（如 `rm -rf /`、`sudo` 等）请先确认
