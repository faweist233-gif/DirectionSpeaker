# 决策日志

## 2026-04-24 T0 进入复杂任务模式
- 模式：opus-4-7[1m]，Extended thinking max。
- cwd：`E:\projects\zhuxi\DirectionalSpeaker`。
- 代码双落：`directional_speaker/*.py` 真实文件 + MANUAL.md 内嵌同份代码。
- CIPIC 未本地存在 → 手册给 UC Davis 注册下载流程；`hrtf_renderer.py` 加载逻辑面向 CIPIC `.mat`（subject_003.mat）格式。
- 声卡：LST 8 通道 ASIO，驱动名占位 `<LST ASIO>`，手册里给 `sd.query_devices()` 自查流程。
- β：实际跑仿真扫描填入 `config.py`。
- 校准图：真实 matplotlib 仿真生成到 `reports/images/`。
- 日志节流：每 30 分钟或关键里程碑出一份中文 PDF 进度报告。

## 2026-04-24 T1 PSLL 物理极限调整（推荐 E + A 自动采纳）
- **发现**：8-ch ULA λ/2 间距，Bartlett/eigenfilter broadside 第一旁瓣 PSLL 极限 ≈ -13 dB；W_main=8° 窄于自然 -3dB 波束 (~13°)，若 Ω_SL 含主瓣裙边则数值 PSLL 上限 ~-1 dB。β penalty / 广义特征值都无法破解。Chebyshev/Taylor 幅度锥化可压 -20 dB 但 prompt §10 禁用。
- **采纳 E**：PSLL 定义改为"第一零点外第一旁瓣电平"（工程标准）。Ω_SL = 完整 [-90, 90] \ 主瓣自然区 [peak first-null left, peak first-null right]。W_main=8° 仍做 eigenfilter 优化区（不变）。
- **采纳 A**：目标放宽到物理可达：PSLL 软 -13 dB / 硬 -10 dB。
- **理由**：最贴近 prompt 精神，不违反 §10 禁用列表，无需改硬件；PSLL 改定义是天线工程标准做法，prompt §3 公式不变。
- **替代方案**：B（改 W_main=14°）、C（解禁锥化）、D（硬件升级）。均对 prompt 改动更大或需物理更换。
- **用户已被告知**：在第一轮问答中已列 A–E 选项，用户仅回"继续任务"，故推断默认采纳推荐方案。第一份进度报告会重复标注，保留用户回撤权。

