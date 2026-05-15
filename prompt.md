# 目标

基于 `MIMSAVI24_MUDIS_HRTF.pdf`（MuSa 系统）搭建实验平台，生成一份**详细实验手册**（中文，单 markdown 文件，含章节编号、图位占位、命令块）。手册读者：具备 Python 基础的研究生。要求可直接按章节照做完成搭建、联调、实验。

---

# 1. 硬件（已就绪，无需采购章节）

- 4×8 超声换能器阵列（8 声道，每声道 4 个振子纵向排列），中心频率 **40 kHz**，已贴合 metasurface。
- 功放：**8 片 OPA541**，每片驱动一个声道。
- 声卡：**8 通道定制版声卡**，ASIO 协议，最高采样率 192 kHz。
- 深度相机：**Intel RealSense D435I**。
- 主机：笔记本 + 三脚架阵列支架。

手册需写：线路连接图（文字描述 + ASCII 或图位占位）、上电顺序、声卡 ASIO 驱动安装验证、OPA541 静态检查。

---

# 2. 操作系统与软件栈

- **首选 Windows 10/11**（ASIO 原生支持充分）。macOS 由于 ASIO 非原生（macOS 走 CoreAudio），若定制声卡未提供 CoreAudio 驱动则必须用 Windows。手册开头给出判断流程：先查声卡厂家是否提供 macOS 驱动，无则直接走 Windows。
- Python 3.10+。
- 依赖：`sounddevice`（ASIO 后端）、`numpy`、`scipy`、`pyrealsense2`、`opencv-python`、`mediapipe`、`soundfile`、`matplotlib`。
- 给出 `requirements.txt` + 安装验证脚本。

---

# 3. 信号参数（固定，照此写手册）

| 项 | 值 |
|---|---|
| 载波频率 | 40 kHz |
| 采样率 | 96 kHz |
| 调制方式 | DSB-AM（带载波，参数阵列标准做法） |
| 滑窗长度 | 50 ms |
| 滑窗跳步 | 25 ms（50% overlap） |
| 物理通道数 | 8（每声道 4 振子纵向） |
| 通道间距 s | **λ/2 ≈ 4.29 mm**（ULA 半波长，首次校准实测确认并写回 `config.py`） |
| 波束方案 | 8 通道连续复权重，在线 eigenfilter，无通道激活 mask |
| 主瓣区域宽度 W_main | 8°（eigenfilter 优化区域，`config.py` 可调） |
| 旁瓣电平目标 PSLL | 软目标 −30 dB，不可达回落 −20 dB（硬阈） |
| 旁瓣惩罚系数 β | 离线扫描得到，使 PSLL 命中目标的最小值，存 `config.py` |
| θ₀ 量化粒度 | 1°（用于 R_ML / R_SL 协方差缓存键）|
| 主瓣/旁瓣离散化步长 | 0.25°（协方差积分 grid） |
| HRTF 数据集 | CIPIC，subject 003（KEMAR） |
| 音频源 | 单声道语音（wav） |

**波束优化：在线 Eigenfilter（8 通道复权重）**

目标：给定左右耳方位 `(θ_L, θ_R)`，为每个波束在线求 8 维复权重 `w ∈ ℂ^8`，使主瓣区域内 array factor 积分能量最大，同时压低旁瓣到 PSLL ≤ −30 dB（不可达回落 −20 dB）。左右波束独立求解，再按单通道峰值做联合归一化。PDF 3.2 节基于 `Δθ_ear` 选 `n ∈ {4..8}` 的离散方案弃用，理由：(a) 8 通道等幅 rect window 主瓣能量占比低、PSLL 仅 −13 dB；(b) 复权重 + 主瓣能量最大化能在保持全孔径的同时联合优化主瓣宽度与旁瓣。

**数学形式**

阵列导向向量（ULA，阵中心为原点，s = λ/2）：

```
a(θ)_k = exp(j · π · (k − 3.5) · sin θ),   k = 0..7
```

对目标方位 `θ₀`，定义：
- 主瓣区 `Ω_ML(θ₀) = [θ₀ − W_main/2, θ₀ + W_main/2]`
- 旁瓣区 `Ω_SL(θ₀) = [−90°, 90°] \ Ω_ML(θ₀)`

协方差（0.25° grid 离散积分）：

```
R_ML(θ₀) = Σ_{θ ∈ grid(Ω_ML)}  a(θ) a(θ)ᴴ · Δθ
R_SL(θ₀) = Σ_{θ ∈ grid(Ω_SL)}  a(θ) a(θ)ᴴ · Δθ
```

权重求解（penalty 形式）：

```
M(θ₀) = R_ML(θ₀) − β · R_SL(θ₀)
w*(θ₀) = principal eigenvector of M(θ₀)   # scipy.linalg.eigh 最大特征值对应向量
w*(θ₀) ← w*(θ₀) / ‖w*(θ₀)‖₂
```

`β` 由离线扫描确定：从 0.1 起按 1.5× 递增扫到 PSLL 满足 −30 dB 的最小 β；若扫到 β=100 仍未达 −30 dB 则回落 −20 dB 重扫，写入 `config.py`。全 θ₀ 共用一个 β（仿真先验证 β 对 θ₀ 不敏感；若敏感改为 `β(θ₀)` 小 LUT，仍每 tick 在线求 eig）。

**联合归一化（L/R 共享 8 物理通道）**

双波束物理通道输出：

```
x[k, t] = α · (w_L[k] · s_L[t] + w_R[k] · s_R[t]),   k = 0..7
α       = 1 / max_k (|w_L[k]| + |w_R[k]|)           # 保守峰值上界
```

保证任意 `t` 下 `|x[k, t]| ≤ 1`（OPA541 饱和上界对应的数字域归一化），不依赖两路音频相关性假设。

**实时成本**

- `θ_L, θ_R` 先量化到 1°，以此为键缓存 `(R_ML, R_SL)`（首次计算 ≈ 1 ms，后续命中缓存）。
- 每 tick 两次 8×8 广义特征分解 ≈ 几十 μs，远小于 50 ms tick。
- `θ₀` 量化到 1° ⇒ `[−90°, 90°]` 共 181 个缓存桶。`main.py` 启动阶段预先扫满所有桶 ≈ 181 × 1 ms ≈ 180 ms 预热，之后稳态仅 eig，无 cache miss。预热同时计算并缓存每 θ₀ 的 `−3 dB` 宽度供 `Δθ_ear` 告警查询。

**`Δθ_ear` 角色调整**

新方案下 `Δθ_ear` 不再驱动权重选择，但 `head_tracker` 仍输出以供：
- 日志告警：查预热期缓存的 `θ₀ → −3 dB 宽度` 表，若 `beam_width(θ_i) < Δθ_i`，打印 `WARNING: beam narrower than ear opening, partial coverage (θ=..., beam=..., ear=...)`。
- 未来扩展：若改为 `Δθ_ear` 驱动 `W_main`（动态主瓣区），可直接替换 `W_main` 常量为 `max(W_main_min, Δθ_ear)`。

**手册单元测试**

- 单波束 `θ₀ = 0°`：画 array factor，验证 `−3 dB` 宽度、PSLL、主瓣能量占比。
- `θ₀` 扫 `−60°` ~ `60°` 步长 10°：主瓣指向偏差 < 0.5°，PSLL 稳定。
- `β` 扫描：画 `β` 对 `(PSLL, −3dB 宽度, 主瓣能量占比)` 的帕累托前沿，截图存档并选最优。
- 联合归一化：左右同时激活任意 `θ_L, θ_R` 组合，蒙特卡洛验证 `max_{k,t} |x[k,t]| ≤ 1`。
- `Δθ_ear` 告警：模拟近距离 (d=0.3 m) 大耳张角，确认日志 WARNING 触发。

**运行模式**（CLI 开关）：
- `--mode live`：D435I 实时追踪真人耳道。
- `--mode virtual --angle {-60,0,60}`：虚拟人头固定方位，跳过相机，供无人调试/测试。

---

# 4. 头部定位：Live 模式（D435I）与 Virtual 模式

## 4.1 Live 模式（真人）

**用途**：定位用户左右耳道在阵列坐标系中的 3D 位置，输出给 beamformer 与 audio adjuster。

**算法链（手册要给完整步骤）**：
1. D435I 启动：RGB 1280×720 @ 30 fps，Depth 848×480 @ 30 fps，对齐到 RGB。
2. MediaPipe Face Mesh 提取 468 landmark，取左耳屏蔽点（landmark 234）与右耳屏蔽点（landmark 454）作为耳道代理点。
3. 用对齐后的深度图读 landmark 像素对应深度，反投影到相机坐标系 → 3D。
4. 相机 → 阵列的外参标定：手册中给 **棋盘格 + 阵列几何中心手动对齐** 的一次性标定流程，输出 4×4 变换矩阵，保存 `extrinsic.json`。
5. 输出：`ear_left_xyz`, `ear_right_xyz`（阵列坐标系）、`θ_left`, `θ_right`（相对阵列法线的方位角，驱动 beamformer）、`d_left`, `d_right`（距离，驱动 audio_adjuster）、`Δθ_left`, `Δθ_right`（耳朵接收角宽度，仅供日志告警比对波束 −3 dB 宽度）。
6. `Δθ_i` 计算：取耳廓物理宽度常量 `W_ear = 0.06 m`（耳廓 helix→tragus 水平跨度，成人均值），`Δθ_i = 2·atan(W_ear/2 / d_i)`。若未来需要更精细，可替换为 MediaPipe 耳朵周边 landmark（左耳 234、447、366；右耳 454、227、137）反投影后求跨度。
7. 追踪帧率 30 fps，低通滤波（α=0.5 EMA）抑制 `θ_i`、`d_i`、`Δθ_i` 抖动。`θ_i` 抖动经 `θ₀` 1° 量化后自动去毛刺，不需额外滞回；`Δθ_i` 仅用于日志告警，抖动不影响权重。

## 4.2 Virtual 模式（无人测试）

**用途**：无人调试、波束测量、算法回归，跳过相机与 MediaPipe。

**参数**：
- 方位角固定三档：`-60°`、`0°`、`+60°`（头部中心相对阵列法线）。
- 头部到阵列距离默认 1.0 m，可 `--distance` 覆盖。
- 双耳间距 17 cm（固定，人体平均值）。

**几何推导**（手册给公式 + 代码）：
- 头部中心 `C = (d·sinθ, 0, d·cosθ)`。
- 左右耳位置 = 头部中心沿头部朝向法线的垂直方向 ±8.5 cm。
- 假设头部朝向阵列（yaw 与方位角相同），耳道方位角 `θ_L`、`θ_R` 与距离 `d_L`、`d_R` 由几何直接解。
- 耳朵接收宽度 `Δθ_i = 2·atan(W_ear/2 / d_i)`，`W_ear = 0.06 m`（与 Live 模式同一常量）。
- 输出格式与 Live 模式一致（含 `Δθ_L`、`Δθ_R`），beamformer 与 adjuster 无感知模式切换。

**CLI**：
```
python -m directional_speaker.main --mode virtual --angle 0
python -m directional_speaker.main --mode virtual --angle -60 --distance 1.2
python -m directional_speaker.main --mode virtual --angle 60
```

非法 `--angle` 值（非 -60/0/60）报错退出。

---

# 5. Python 模块解耦（手册需按此结构给完整代码）

```
directional_speaker/
├── config.py              # 全局常量：fs=96000, fc=40000, c=343, lam=c/fc,
│                           # s=lam/2, N=8, window_ms=50, hop_ms=25,
│                           # W_main_deg=8, theta0_quant_deg=1, grid_step_deg=0.25,
│                           # PSLL_soft_db=-30, PSLL_hard_db=-20, beta=<离线标定>,
│                           # W_ear_m=0.06, ...
├── audio_source.py        # 加载 wav、重采样到 192k、mono 输出迭代器
├── hrtf_renderer.py       # CIPIC HRIR 加载 + 卷积 → 双声道
├── modulator.py           # DSB-AM 调制到 40 kHz 载波
├── beamformer.py          # 输入 (θ_L, θ_R)，在线 eigenfilter 解 8 维复权重 w_L, w_R
│                           # (max wᴴR_ML w − β·wᴴR_SL w)，按 α=1/max_k(|w_L[k]|+|w_R[k]|) 联合归一化
├── audio_adjuster.py      # 振幅补偿（指数衰减）+ 相位对齐，基于 d_left/d_right
├── head_tracker.py        # 抽象接口 get_ear_pose() → (θ_L, θ_R, d_L, d_R, Δθ_L, Δθ_R)
│                           # Δθ_* 仅供日志告警（beamformer 不再使用）
│                           # 两个实现：LiveTracker (D435I+MediaPipe), VirtualTracker (固定角度)
├── playback.py            # sounddevice ASIO 8 通道流式输出
├── calibration.py         # 相机-阵列外参标定脚本
├── main.py                # 主循环：滑窗 × (tracker → render → modulate → beam → play)
└── tests/                 # 单元测试：各模块独立验证
```

每个模块：
- 顶部写职责、输入输出、依赖。
- 函数签名带类型标注。
- 可独立 `python -m directional_speaker.<module>` 自测。
- `main.py` 仅做编排，不放业务逻辑。

---

# 6. 实时流水线

- 主循环 50 ms tick。每 tick：
  1. `head_tracker` 读最新帧（非阻塞，拿上一帧 cache 若无新帧）。
  2. `audio_source` 取 50 ms mono 片段。
  3. `hrtf_renderer` 卷积 HRIR → 左右双声道。
  4. `audio_adjuster` 按距离差补振幅/相位。
  5. `modulator` 上变频到 40 kHz。
  6. `beamformer` 对 `θ_L`、`θ_R` 各自求在线 eigenfilter 最优权重 `w_L, w_R ∈ ℂ^8`（θ₀ 量化 1° 命中 `(R_ML, R_SL)` 缓存后解 8×8 广义特征值），按 `α = 1 / max_k (|w_L[k]| + |w_R[k]|)` 联合归一化输出 `x[k,t] = α·(w_L[k]·s_L + w_R[k]·s_R)`。
  7. `playback` 推入 ASIO 环形缓冲。
- 缓冲深度 ≥ 3 帧（150 ms）防欠载。
- 日志：每秒打印一次 tracker 延迟、音频欠载次数。

---

# 7. 校准与验证（手册单独一章）

1. **声卡通道映射核验**：依次给单通道发 40 kHz sine 5 秒，麦克风或示波器确认物理通道顺序。
2. **载波纯度核验**：全通道同相位发 40 kHz，FFT 检查主瓣。
3. **调制效果核验**：发 1 kHz tone AM 调制到 40 kHz，经参数阵列解调后麦克风录到 1 kHz。
4. **波束方向核验**：θ 扫 -30°~+30°，沿弧线移动麦克风测 SPL，画主瓣方向图。
5. **波束优化核验**：
   - 离线仿真先标定 `β`：扫 `β ∈ {0.1, 0.15, ..., 100}`（1.5× 递增），对每个 β 计算 PSLL / −3 dB 宽度 / 主瓣能量占比，取满足 PSLL ≤ −30 dB 的最小 β，失败回落 −20 dB，写入 `config.py`。
   - 实测：固定 `θ₀ ∈ {−60°, −30°, 0°, 30°, 60°}` 各发 40 kHz tone，沿弧线（半径 1 m）移动麦克风测 SPL → 得 `−3 dB` 宽度与 PSLL，对比仿真 eigenfilter AF 预测，偏差 >20% 回查 `s` 实测值与 `β`。
   - 记表：θ₀ × (仿真 vs 实测) × (−3 dB 宽度, PSLL, 主瓣能量占比)。
6. **HRTF 渲染核验**：离线生成双声道 wav，用普通耳机听空间感，确认方向正确。
7. **端到端**：用户入座，播放白噪声，询问主观左右感。

---

# 8. 实验场景

- 用户坐姿，头部允许轻微转动（±15° yaw，±10° pitch）。
- 播放素材：中文/英文**语音**（单声道 wav）。
- 阵列距用户约 0.8–1.2 m，阵列正对用户头部高度。
- 每次实验 30–60 秒，记录主观评价。

---

# 9. 手册交付格式

- **单文件** `MANUAL.md`，中文。
- 章节：环境准备 → 硬件连接 → 软件安装 → 模块代码 → 校准 → 运行 → 实验流程 → 常见故障。
- 代码块完整可运行，不得省略 `...`。
- 关键步骤配图位占位（`![示意图](images/xxx.png)`）。
- 末尾附 `requirements.txt`、`config.py` 完整清单。

---

# 10. 约束

- 不考虑超声暴露安全限值。
- 不做 machine learning 预测。
- 波束权重方案固定为全 8 通道复权重在线 eigenfilter，不探索稀疏激活、离线 LUT、SDP、MVDR、Dolph-Chebyshev 等替代方案（若 eigenfilter 无法达 PSLL −20 dB 硬阈再议）。
- 旁瓣电平：软目标 PSLL ≤ −30 dB，硬阈 ≤ −20 dB。
- `β` 全 `θ₀` 共用一个值（若仿真显示对 `θ₀` 敏感则改 `β(θ₀)` 小 LUT，但不引入离线权重 LUT）。
- HRTF subject 固定 003，不做个性化。
- Virtual 模式仅支持 -60° / 0° / +60° 三档，其他角度不考虑。
