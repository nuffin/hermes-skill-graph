---
name: intent-router
description: "意图路由器 — 用户输入进来后先分类、消歧、映射到正确框架，再执行操作"
author: Hauzer S. Lee
license: MIT
category: hermes
platforms:
  - linux
  - macos
version: 1.0.0-standalone
metadata:
  hermes:
    relations:
      - type: complemented_by
        target: skill-graph
        properties:
          reason: 意图路由后通过图谱精准匹配技能，二者配合能覆盖更多场景
          strength: medium
    tags:
      - hermes
      - 意图路由器
      - intent-router
      - 用户输入进来后先分类
      - 映射到正确框架
---

# 意图路由器 (Intent Router)

## 职责边界

intent-router 只回答「执行什么」，不回答「怎么执行」：

```
用户输入 → Phase 1-3 分类 → Phase 4 路由 → 加载 skill 执行 → quality-gate
```

| 组件 | 职责 |
|------|------|
| **intent-router** | 分类 → 路由 → 决定用哪个 skill |
| **skill-graph** | 按意图搜索 skill → 返回匹配结果 |
| **quality-gate** | 收尾验证 |

每次收到用户输入后，先做语义预处理，最后用 `skill_load("quality-gate")` 收尾。

## 🔴 铁律 — 加载顺序

**intent-router 必须永远第一个加载。** 即使直觉告诉你输入直接映射到某个 skill，
也**必须先走完 Phase 1-3 的分类流程**，再进入 Phase 4 路由。

⭐ **正确模式：**
1. 收到用户输入
2. 加载 intent-router → 分类(Phase 1) → 消歧(Phase 2) → 预检(Phase 3) → 路由(Phase 4)
3. `skill_graph_search()` 发现 skill → `skill_load()` 加载执行
4. `skill_load("quality-gate")` 收尾验证

## 🔴 铁律 2 — 每轮重新判断意图 (Phase 0)

每次收到用户消息，无论是否是同一 session 的第 2、3、N 句，都必须重新走完整流程。

```
收到用户输入
  ├── Step A: Intent Reset — 抛弃上一轮分类缓存
  ├── Step B: 读当前消息，判断新意图类别
  ├── Step C: Multi-Intent Split — 拆成 N 个独立操作
  └── Step D: 进入 Phase 1-4
```

Multi-Intent Split 判断：一段话里包含多个可独立执行的操作时要拆分。
```markdown
"看看项目结构，给 user 模块加上批量删除" → [信息查询, 功能开发]
```

## Phase 1: Input Classification

| 类别 | 说明 | 路由 |
|------|------|------|
| 1A 任务管理 | 提到任务名/路径/hash | skill_graph_search("task 任务管理") |
| 1B 执行/操作 | "跑吧"/"做一下"/"commit" | → Phase 2 |
| 1C 设计讨论 | "我觉得 xxx 可以改成"/提问 | 不执行，只参与讨论 |
| 1D 信息查询 | "这是什么"/"xxx 怎么工作的" | 直接回答 |
| 1E 元操作 | 改 config/skill/memory | 直接处理 |

## Phase 2: Intent Resolution (仅 1B 执行类)

| 信号 | 行为 |
|------|------|
| "commit" | 执行 git 工作流（commit 但不 push） |
| "push" / "推送" | 允许 push |
| "停" / "stop" / "等我" | 立刻停，安静等待 |
| 全部完成 | `skill_load("quality-gate")` |

## Phase 3: Pre-flight Check (执行前检查)

| 操作目标 | 工具 | 检查 |
|---------|------|------|
| task 目录 | task-framework 工具 | 先读 TASK_MEMORY.md |
| git 仓库 | git 命令 | pre-change sync |
| skill 文件 | skill_manage | — |
| 规则文件 | read_file / write_file | — |

## Phase 4: Routing

分类完成后用 `skill_graph_search(query)` 发现对应 skill。
输入 query 应该是自然语言描述，例如：

| 意图 | 搜索 query |
|------|-----------|
| 任务创建/管理 | `skill_graph_search("task management and workflow")` |
| Git 操作 | `skill_graph_search("git commit and push workflow")` |
| 代码审查 | `skill_graph_search("code review pull request")` |
| 写 PRD/需求 | `skill_graph_search("product requirements document")` |
| 调试程序 | `skill_graph_search("debug python systematic")` |
| 设计和原型 | `skill_graph_search("design prototype mockup")` |
| 部署服务 | `skill_graph_search("deploy service docker")` |
| 视频制作 | `skill_graph_search("video production screen recording")` |

找到后调用 `skill_load(name)` 加载内容，按 skill 指令执行。

## 收尾

所有操作完成后，始终调用 `skill_load("quality-gate")` 做最终验证。
不依赖 `post-flight` skill — quality-gate 是 pipeline 的收尾不变量。
