---
name: translate
description: 将文本翻译为指定语言
description_ja: テキストを指定言語に翻訳
description_en: Translate text to a specified language
category: communication
auto_execute: true
chainable: true
keywords:
  - 翻译
  - translate
  - 翻訳
  - 번역
  - translation
params:
  text:
    type: string
    required: true
    description: 要翻译的文本
  target_lang:
    type: string
    required: true
    description: 目标语言（如 English, 中文, 日本語）
  source_lang:
    type: string
    required: false
    description: 源语言（可选）
---

# 翻译技能

## 执行指令

请将以下文本翻译为 **{{target_lang}}**：

```
{{text}}
```

**要求**：
1. 保持原文的语气、风格和格式
2. 翻译要准确、地道、符合目标语言习惯
3. 仅返回译文，不加任何解释或额外内容
4. 如遇到专业术语，可在译文中保留原文并在括号中加注
5. 如果文本包含代码或技术术语，保持原样不翻译
