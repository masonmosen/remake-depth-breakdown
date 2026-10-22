# v1.0.1 实测报告（2026-10-22，Linux 8 核 CPU，无 GPU）

参考片：吊扇换装原片 2160×3840 · 24fps · 302 帧 · 12.58s

| 步骤 | 结果 |
|---|---|
| `python3 install.py --venv --cpu` 全新安装 | 通过，32s，.venv 1.4GB（不加 --cpu 在 Linux 会装 CUDA torch，65s，数 GB） |
| `SELFCHECK_FORCE_DEMO=0 python3 selfcheck.py` | 通过，真 Depth Anything V2 Small |
| `run_all.py --input 原片 --require-real` | 通过，CPU 约 2m10s（720 长边，302 帧） |
| 25.17s 拼接片（>15s） | 通过，自动切出 depth_seg01 0–15s / depth_seg02 15–25.17s，约 4m05s |
| 断网+无缓存 + `--require-real` | 按预期报 FATAL 退出，不退回 DEMO |
| `validate_prompt.py` | 填写后从 0s 覆盖通过；未填 TODO / 从 2.5s 起写均判失败 |

## 与 LibTV 深度对比（test/compare_depth.py）

- 极性一致：近白远黑。
- LibTV 片为 608×1080、12.00s（截掉尾部 0.58s）；本工具 404×720、12.58s 全长。
- 同时刻灰度相关系数：0s 0.97 / 1s 0.98 / 3s 0.97 / 7s 0.95 / 11s 0.90。
- 帧间平均差：本工具 6.2，LibTV 9.0（本工具更稳、闪烁更少）。
- 差异：本工具全片统一拉伸，吊扇最亮，人物与地毯的对比度比 LibTV 低一些；LibTV 把吊扇顶到纯白，人物轮廓更清楚。

## 修复
1. 帧率：部分导出文件容器 avg_frame_rate 错误（24fps 报成 23.685），导致深度片变长到 12.75s、和原片不同步 → 改用 ffprobe r_frame_rate 校验。
2. 新增 `--require-real`（run_all / extract_depth；selfcheck 在 FORCE_DEMO=0 时自动加），真模型失败直接报错。
3. 吊扇擦除式换装不是硬切，镜头检测为 0 → breakdown 标明「1 秒网格不是真实镜头」，并新增软转场候选（本片检出 5.67/7.67/8.96/10.54/11.54s，与换装点吻合），候选帧加入拼图。
4. install.py 新增 `--cpu`；装进 .venv 后直接 `python3 …` 会自动切到 .venv（之前会因系统 Python 缺依赖报错）。
5. manifest.json 写入 depth_segments；DEMO 深度会在结尾醒目警告。
6. 深度缓存改 float16，长片内存减半。
