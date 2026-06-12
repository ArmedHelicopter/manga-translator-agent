# 灵感记录：知识蒸馏

> 记录日期：2026-06-11  
> 状态：待讨论

---

## 核心灵感

manga-translator-agent 翻译过程中积累的 memory（角色档案、术语库、场景上下文）可以**蒸馏**为社区标准格式，方便分享和复用。

---

## 目标输出

### 1. Character Card（角色卡）
- 用途：导入 TavernAI / SillyTavern 等角色扮演平台
- 内容：角色名、性格、说话风格、对话示例

### 2. Lorebook（世界书）
- 用途：导入 NovelAI / AI Dungeon
- 内容：key-value 条目（角色、术语、场景），带触发词

### 3. Hermes Agent Skill
- 用途：让 Hermes agent 扮演特定角色
- 内容：待定（格式需要 web search 确认）

---

## 使用场景

- 翻译完一部作品后，导出角色知识分享给社区
- 用蒸馏的 skill 让 agent 以角色身份对话
- 用 lorebook 在 NovelAI 中保持世界观一致性

---

## 触发方式

手动命令（非自动）

---

## 反向流程

通过 memory 导入实现，不走世界书格式。

---

## 待确认

- [ ] Hermes Agent 的 skill 文件格式是什么？
