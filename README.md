# 复刻拉片工坊 · remake-depth-breakdown

**版本 1.0.0 · MIT · 给工作室小伙伴开箱即用**

给你一条参考视频，本技能一次交出：

1. **深度视频**（可挂到 Seedance 当动作参考）
2. **原片音轨**（m4a）
3. **逐帧 / 逐秒拉片骨架** + 缩略图拼图
4. **中英提示词草稿骨架**（时间轴从 0 秒写起，留给视觉模型填写）

---

## 产品边界（请先读）

| 能力 | 谁来做 | Hermes / 任意模型？ |
|------|--------|-------------------|
| 深度视频、抽音轨、镜头切点、拼图、时间轴骨架 | **本地脚本**（本仓库） | ✅ 通用，**不需要**大模型 |
| 看着拼图，把中英 Seedance 提示词写满 | **能看图的模型** | ⚠️ 必须视觉模型；纯文本模型应停止并提示切换 |
| 去 LibTV / Seedance **付费出片** | **不在本技能范围** | ❌ 只准备参考与提示词；见 `docs/libtv-manual.md` 手工上传说明 |

本技能**不依赖** Grok Bot、LibTV MCP、或任何特定云账号。  
在 Hermes、Cursor、或其他 Agent 运行时均可使用。

---

## 一分钟上手（Hermes / 任意环境）

```bash
# 1) 系统需已安装 ffmpeg（macOS: brew install ffmpeg / Ubuntu: sudo apt install ffmpeg）
git clone https://github.com/masonmosen/remake-depth-breakdown.git
cd remake-depth-breakdown

# 2) 安装 Python 依赖（系统 Python 受限时会自动建 .venv）
python3 install.py
# 或显式：python3 install.py --venv
# Linux 无 N 卡建议加 --cpu（装 CPU 版 torch，约 200MB；否则会拉几 GB 的 CUDA 包）
# python3 install.py --venv --cpu
# 装完后照常用 python3 运行即可：脚本检测到 .venv 会自动切换进去
# 离线自检轻量安装：
# python3 install.py --force-demo-only

# 3) 自检（默认用 DEMO 深度代理，不下载模型；要试真模型：SELFCHECK_FORCE_DEMO=0 python3 selfcheck.py）
python3 selfcheck.py

# 4) 对真实参考片一键跑通
python3 scripts/run_all.py --input /path/to/ref.mp4 --require-real
# --require-real：真模型加载失败就直接报错，不会悄悄退回 DEMO 深度
# 首次运行会从 HuggingFace 下载 Depth Anything V2 Small（约 100MB）
# 实测：12.6s 竖屏 2160×3840 参考片，8 核 CPU 约 2 分钟；GPU / Apple MPS 更快
# 输出目录：out/<视频名>/
```

输出物：

```
out/<stem>/
  depth.mp4          # 近白远黑，无音轨；真模型或 DEMO 代理
  depth.json         # 记录用了 Depth Anything 还是 DEMO
  depth_seg01.mp4…   # 片长 >15s 时自动切的 ≤15s 分段（Seedance 单条上限）
  manifest.json      # 全部产物路径 + depth_segments
  ref_audio.m4a
  breakdown.md       # 拉片骨架（描述列为空）
  timeline.csv
  per_second.csv
  sheets/*.png       # 缩略图拼图 ← 视觉模型看这些填提示词
  prompt_zh.txt      # 中文提示词骨架 + 填写说明
  prompt_en.txt
  manifest.json
```

---

## 视觉模型怎么填提示词

1. 打开 `sheets/*.png` 和 `breakdown.md`
2. 从 **0.0 秒**写起（含掉沙发、起身等开场动作，禁止直接从拿遥控器等中段开始）
3. 填满 `prompt_zh.txt` / `prompt_en.txt` 里每个时间段
4. 校验：

```bash
python3 scripts/validate_prompt.py --prompt out/<stem>/prompt_zh.txt --duration 12.0
```

若当前是**纯文本模型**、看不到图片：请停止，明确告诉用户「需要切换视觉模型」，不要编造画面。

---

## 深度模型说明

- **首选**：Depth Anything V2 Small（`depth-anything/Depth-Anything-V2-Small-hf`，经 `transformers`）
- **回退**：若模型下载失败或离线，自动使用 OpenCV 亮度代理，画面会打上 **「DEMO ONLY」** 水印，仅供流程自检，**不要当正式动作参考**
- 深度图约定：**近 = 白，远 = 黑**；无音轨；默认长边 ≤ 720；可用 `--split-max 15` 切成 ≤15s 分段（方便 Seedance 时长限制）

常用参数：

```bash
python3 scripts/extract_depth.py --input ref.mp4 --output depth.mp4 \
  --start 0 --end 12 --max-side 720 --device auto --split-max 15
```

---

## 目录

```
install.py / selfcheck.py / requirements.txt / VERSION / LICENSE / SKILL.md
scripts/
  run_all.py
  extract_depth.py
  extract_audio.py
  breakdown.py
  validate_prompt.py
docs/
  libtv-manual.md   # 可选：手工挂到 LibTV 的说明（不扣本技能的积分）
```

---

## 给 Agent 的短指令

> 用户给了参考视频要复刻。按 SKILL.md：先 `install.py`（若未装），再 `scripts/run_all.py --input …`，返回 `manifest.json` 路径。若你能看见 `sheets/`，填写并 `validate_prompt.py`；若不能看见图片，停止并要求视觉模型。不要自动去 LibTV 扣积分。

---

Maintainer: masonmosen · Skill id: `remake-depth-breakdown` · 中文名：**复刻拉片工坊**
