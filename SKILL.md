---
name: 复刻拉片工坊
description: use when given a reference video to remake — extract depth video, frame-by-frame breakdown, and Seedance-ready prompts (Hermes/any agent; local tools bundled)
id: remake-depth-breakdown
version: 1.0.0
license: MIT
---

# 复刻拉片工坊 · Agent 操作手册

本技能把「参考视频 → 深度片 + 拉片 + Seedance 提示词骨架」做成**本地、可开箱**的工具包。  
**运行时无关**：Hermes / Cursor / 其他 Agent 均可；**不依赖** Grok Bot、LibTV MCP、或特定云账号。

## 诚实边界（必须遵守并告知用户）

1. **本地脚本即可、任意聊天模型都能跑**：深度视频、抽音轨、镜头切点、缩略图拼图、时间轴骨架。这些步骤**不需要**大模型。
2. **填写中英 Seedance 提示词**（对着拼图写动作/服装/转场）**必须**使用**能看图的模型**。若当前是纯文本模型：停止，用明确句子告诉用户「需要切换视觉模型」，禁止瞎编画面。
3. **付费出片（LibTV / Seedance）不在本技能范围**。只交付参考与提示词；需要出片时引导用户看 `docs/libtv-manual.md` 手工上传，或由用户另行批准付费流程。

## 前置

- 系统已安装 `ffmpeg`（或 `pip install imageio-ffmpeg`）
- Python 3.10+
- 技能根目录：本仓库克隆路径（下文称 `$SKILL`）

## 步骤（按顺序）

### 1. 安装（首次或依赖缺失时）

```bash
cd "$SKILL"
python3 install.py
# 可选：python3 install.py --venv
# 离线轻量：python3 install.py --force-demo-only
python3 selfcheck.py
```

### 2. 一键产物

```bash
python3 scripts/run_all.py --input /path/to/ref.mp4
# 可选：--start 0 --end 12 --max-side 720 --device auto --split-max 15
# 离线强制 DEMO 深度：加 --force-demo
```

默认输出：`$SKILL/out/<stem>/`，含 `depth.mp4`、`ref_audio.m4a`、`breakdown.md`、`timeline.csv`、`sheets/`、`prompt_zh.txt`、`prompt_en.txt`、`manifest.json`。

读取 `manifest.json` 与 `depth.json`：若 `backend` 为 `demo-luminosity-proxy`，告知用户这是 DEMO 水印片，正式复刻需能下载 Depth Anything V2。

### 3. 填写提示词（仅视觉模型）

- 打开 `sheets/*.png` + `breakdown.md` + `per_second.csv`
- 编辑 `prompt_zh.txt` / `prompt_en.txt`：从 **0.0s** 连续写到片尾
- **禁止**跳过开场（例如漏掉「从沙发掉下」只写「拿遥控器」）
- 纯文本模型：到此停止并提示切换

### 4. 校验

```bash
python3 scripts/validate_prompt.py --prompt out/<stem>/prompt_zh.txt --duration <秒>
python3 scripts/validate_prompt.py --prompt out/<stem>/prompt_en.txt --duration <秒>
```

失败则按缺口补写，尤其是从 t=0 开始的 opening beat。

### 5. 交付用户

返回这些路径（不要自动扣积分出片）：

- 深度视频、音轨、拼图目录、填好的提示词、`manifest.json`
- 若用户要去 LibTV：附上 `docs/libtv-manual.md` 要点

## 单独脚本

| 脚本 | 用途 |
|------|------|
| `scripts/extract_depth.py` | 深度片（真模型或 DEMO） |
| `scripts/extract_audio.py` | m4a 音轨 |
| `scripts/breakdown.py` | 切点 + 骨架 + sheets |
| `scripts/validate_prompt.py` | 时间轴连续性 |
| `scripts/run_all.py` | 编排以上全部 |

## 禁止

- 不要把人脸参考图、API Key、账号 cookie 写进仓库或技能输出
- 不要在未获用户明确批准时触发任何付费生成
- 不要用 DEMO 深度片冒充正式 Depth Anything 结果（须展示 `depth.json` 的 backend 字段）
