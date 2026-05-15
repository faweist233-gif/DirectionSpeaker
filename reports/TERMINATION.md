# 终止条件（用户确认 2026-04-24）

1. `MANUAL.md` 交付：覆盖 prompt.md §1–§9 全章节，无 `...` 省略，代码块完整可运行。
2. `directional_speaker/` 8 模块（config / audio_source / hrtf_renderer / modulator / beamformer / audio_adjuster / head_tracker / playback / calibration / main）+ `tests/` 可运行。
3. `python -m directional_speaker.main --mode virtual --angle 0` 无硬件时不崩（使用 dummy playback backend）。
4. `tests/` 仿真单测通过：array factor 形态、β 扫描、联合归一化 Monte Carlo、Δθ 告警触发、虚拟跟踪几何。
5. β 离线扫描实际跑通，最优值写入 `config.py`。
6. 校准图生成：`reports/images/af_theta0_0.png`、`beta_pareto.png`、`beam_scan.png`。

**预算**：1 天（24h 真实时间，从 2026-04-24 开始）。
**失败代价**：允许多轮重试。
**模型**：Opus 4.7[1m]。
**硬件存在性**：定制声卡 = LST（ASIO 设备名占位 `<LST ASIO>`）。CIPIC HRTF 本机未下载，手册给下载流程。
