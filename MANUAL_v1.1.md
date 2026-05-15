# MUSA 式 8 通道超声方向性扬声器 — 实验手册 v1.1

> 目标读者：具备信号处理与 Python 基础的研究生。  
> 本手册覆盖：零陷波束形成（Null-Steering）原理、频域逐频点加权、与参考代码的对照、以及实际硬件播放验证。  
> 旧版 eigenfilter 方案见 `MANUAL.md`（v1.0），已废弃。

---

## 目录

1. [核心原理变更](#1-核心原理变更)
   - [1.1 旧方案处理流程](#11-旧方案处理流程)
   - [1.2 单主瓣成因的详细数学推导](#12-单主瓣成因的详细数学推导)
   - [1.3 新方案处理流程](#13-新方案处理流程)
   - [1.4 新方案数学原理的详细推导](#14-新方案数学原理的详细推导)
2. [信号处理 Pipeline](#2-信号处理-pipeline)
3. [与参考代码的对照](#3-与参考代码的对照)
4. [LUT 离线生成](#4-lut-离线生成)
5. [实时运行](#5-实时运行)
6. [参数表](#6-参数表)
7. [关键代码片段](#7-关键代码片段)
8. [故障排除](#8-故障排除)

---

## 1. 核心原理变更

### 1.1 旧方案处理流程

v1.0 采用的处理顺序（基带波束形成 + 统一上变频）：

```
单声道音频 x(t)
    |
HRTF 渲染 -> (s_L(t), s_R(t))     [基带，|s| <= 1]
    |
基带波束形成: z_n(t) = alpha * [w_L,n * s_L(t) + w_R,n * s_R(t)]
    其中 w_L,n = exp(j*pi*n*sin(theta_L))   [复常数，与频率无关]
    |
统一 DSB-AM 上变频:
    x_n(t) = 0.5 * Re{ (1 + z_n(t)) * exp(j*2*pi*f_c*t) }
    |
8 通道输出
```

**关键特征**：波束权重 `w_L,n` 和 `w_R,n` 是**复常数**（与频率无关），基于单一设计频率（隐含为载波频率 `f_c = 40 kHz`）计算。

### 1.2 单主瓣成因的详细数学推导

#### 步骤 1：基带信号的频谱结构

设基带音频 `s(t)` 的带宽为 `B`（约 4 kHz），其频谱 `S(f_b)` 分布在 `|f_b| <= B`。

经 DSB-AM 调制后（调制指数 m=1）：

```
x_n(t) = 0.5 * cos(2*pi*f_c*t) + 0.5 * Re{ z_n(t) * exp(j*2*pi*f_c*t) }
```

其中第二项（含信息部分）的频谱为：

```
X_n(f) = 0.25 * [Z_n(f - f_c) + Z_n*(f + f_c)]
```

即基带频谱 `Z_n(f_b)` 被对称搬移到 `f_c +/- f_b`。

因此，**调制后的信号是一个宽带信号**，频率成分分布在 `[f_c - B, f_c + B]`（即 36 kHz ~ 44 kHz）。

#### 步骤 2：理想波束形成的频率依赖性

物理上，均匀线阵（ULA）的导向向量**必须依赖频率**。对于频率 `f`、波长 `lambda(f) = c/f`，指向角度 `theta` 的导向向量为：

```
a_n(f, theta) = exp( -j * 2*pi * n * d / lambda(f) * sin(theta) )
              = exp( -j * 2*pi * n * d * f / c * sin(theta) )
```

其中 `d = lambda_c/2 = c/(2*f_c)` 为阵元间距。

在理想情况下，若要在角度 `theta_0` 形成主瓣，通道 `n` 对频率 `f` 应施加的相位为：

```
phi_ideal(n, f, theta_0) = -2*pi * n * d * f / c * sin(theta_0)
                         = -pi * n * (f/f_c) * sin(theta_0)        [因为 d = c/(2*f_c)]
```

#### 步骤 3：旧方案实际施加的相位

在旧方案中，基带波束形成器对**所有频率**施加**相同的复权重**：

```
w_n(theta_0) = exp( -j * pi * n * sin(theta_0) )
```

这个权重隐含对应于**设计频率 `f_c`** 的理想相位：

```
phi_old(n, f, theta_0) = -pi * n * sin(theta_0)       [对所有频率 f 都一样]
```

#### 步骤 4：频率相关的指向偏差

对比理想相位和实际相位：

```
Delta_phi(n, f) = phi_old(n, f, theta_0) - phi_ideal(n, f, theta_0)
                = -pi*n*sin(theta_0) - [ -pi*n*(f/f_c)*sin(theta_0) ]
                = -pi*n*sin(theta_0) * [1 - f/f_c]
```

对于调制后的频率 `f = f_c + f_b`（上边带）：

```
Delta_phi(n, f_c + f_b) = -pi*n*sin(theta_0) * [1 - (f_c + f_b)/f_c]
                        = +pi*n*sin(theta_0) * (f_b / f_c)
```

对于下边带 `f = f_c - f_b`：

```
Delta_phi(n, f_c - f_b) = -pi*n*sin(theta_0) * [1 - (f_c - f_b)/f_c]
                        = -pi*n*sin(theta_0) * (f_b / f_c)
```

这个额外的相位误差 `Delta_phi` 导致不同频率的波束指向了**不同的角度**。

#### 步骤 5：波束指向偏差的计算

波束实际指向角度 `theta'` 满足：施加的相位等于频率 `f` 在角度 `theta'` 处所需的相位：

```
-pi * n * sin(theta_0) = -2*pi * n * d * f / c * sin(theta')
-pi * n * sin(theta_0) = -pi * n * (f/f_c) * sin(theta')
```

解得：

```
sin(theta') = (f_c / f) * sin(theta_0)
```

**这是核心公式。**

对于上边带 `f = f_c + f_b`：

```
sin(theta'_upper) = f_c / (f_c + f_b) * sin(theta_0)  <  sin(theta_0)
```

对于下边带 `f = f_c - f_b`：

```
sin(theta'_lower) = f_c / (f_c - f_b) * sin(theta_0)  >  sin(theta_0)
```

#### 步骤 6：数值示例（波束色散量）

取 `f_c = 40 kHz`，`B = 4 kHz`，`theta_0 = 30 deg`：

| 频率成分 | f (kHz) | sin(theta') | theta' (度) |
|---------|---------|-------------|-------------|
| 下边带 | 36 | (40/36)*0.5 = 0.556 | **33.8** |
| 载波 | 40 | (40/40)*0.5 = 0.500 | **30.0** |
| 上边带 | 44 | (40/44)*0.5 = 0.455 | **27.0** |

**结论**：同一基带信号经调制后，下边带指向 33.8deg，上边带指向 27.0deg。基带中所有频率成分在空间中形成了一个**展宽的扇形**，而不是一个锐利的单方向主瓣。

#### 步骤 7：左右耳波束重叠导致单主瓣

在虚拟模式中，人头位于阵列前方 1 m 处：

- 左耳角度 `theta_L ~ theta_0 - 4 deg`
- 右耳角度 `theta_R ~ theta_0 + 4 deg`

假设系统试图在 `theta_L = 0 deg` 和 `theta_R = 40 deg` 形成两个独立声像：

- `theta_L = 0 deg` 的波束：无色散（sin(0deg)=0），保持锐利
- `theta_R = 40 deg` 的波束：上边带指向 35.3deg，下边带指向 44.3deg，展宽约 9deg

由于人头左右耳间距仅约 17 cm，在 1 m 距离处两耳角度差约 10deg。而 `theta_R = 40 deg` 的波束已展宽约 9deg，两束严重重叠。加上旁瓣泄漏，听者感受到的是一个**合并的宽主瓣**，而非两个独立声像。

这就是"只有一个主瓣"的根本原因：**宽带基带信号经频率无关权重调制后产生不可忽略的波束色散（Beam Squinting），两路展宽波束在空间中重叠。**

---

### 1.3 新方案处理流程

参考 `音频生成` 文件夹中经过验证的代码，改为**先调制、后频域逐频点加权**：

```
单声道音频 x(t)
    |
HRTF 渲染 -> (s_L(t), s_R(t))
    |
分别 DSB-AM 调制:
    mod_L(t) = 0.5 * Re{ (1 + s_L(t)) * exp(j*2*pi*f_c*t) }
    mod_R(t) = 0.5 * Re{ (1 + s_R(t)) * exp(j*2*pi*f_c*t) }
    |
频域逐频点零陷加权（以 mod_L 为例）:
    X_L(f) = FFT(mod_L(t))
    对每个频率 bin f:
        查找 LUT 中对应 f 的权重 (a_n(f), psi_n(f))
        W_n(f) = a_n(f) * exp(j*psi_n(f))
        Y_n(f) = X_L(f) * W_n(f)    [n = 0..7]
    y_n(t) = IFFT(Y_n(f))
    |
8 通道输出
```

**关键特征**：每个频率 `f` 都获得了**与该频率精确匹配**的幅相权重，消除了波束色散。

### 1.4 新方案数学原理的详细推导

#### 步骤 1：已调制信号的频域表示

对 mod_L(t) 做 FFT：

```
X_L(f) = integral mod_L(t) * exp(-j*2*pi*f*t) dt
```

由于 mod_L(t) 是 DSB-AM 信号，其频谱分布在 `[f_c - B, f_c + B]` 范围内。

#### 步骤 2：频域逐频点加权

设 LUT 为每个目标-零陷对 `(theta_t, theta_n)` 存储了频率网格 `{f_m}` 上的权重：

```
W_n(f_m) = a_{m,n} * exp(j * psi_{m,n})
```

其中 `m = 1..M`（M=81，对应 36kHz~44kHz，步长 100Hz），`n = 0..7`（通道）。

对于 FFT 输出的任意频率 bin `f`，找到最近的 LUT 频率 `f_m`，施加权重：

```
Y_n(f) = X_L(f) * W_n(f_m)    当 |f - f_m| < Delta_f/2
```

其中 `Delta_f = 100 Hz` 为 LUT 频率步长。

#### 步骤 3：加权后信号的方向图

对通道 `n` 的加权后信号做 IFFT，得到时域输出 `y_n(t)`。

考虑空间中角度 `theta` 处的接收响应。阵列接收方向图由所有通道的相干叠加决定：

```
P(f, theta) = (1/N) * sum_{n=0}^{N-1} W_n(f) * exp( j * 2*pi * n * d * f / c * sin(theta) )
            = (1/N) * sum_{n=0}^{N-1} a_n(f) * exp( j * [psi_n(f) + 2*pi*n*d*f/c*sin(theta)] )
```

#### 步骤 4：零陷优化的目标

优化器（`calibrate_nullsteering.py` 中的 L-BFGS-B）调整 `{a_n(f_m), psi_n(f_m)}`，使得：

**主瓣区** `theta in [theta_t - W_main/2, theta_t + W_main/2]`：
```
P(f_m, theta) ~ 1    （最大化主瓣能量）
```

**零陷区** `theta in [theta_n - W_null/2, theta_n + W_null/2]`：
```
|P(f_m, theta)| ~ 0   （最小化零陷能量）
```

**旁瓣区** `theta in [-90deg, 90deg] \\ (主瓣区 并 零陷区)`：
```
|P(f_m, theta)| 尽可能小
```

**频率一致性**：
```
Var_{f_m}( sum_{theta in 主瓣} |P(f_m, theta)| ) 尽可能小
```
（确保不同频率的主瓣能量一致，避免某些频率过强/过弱）

#### 步骤 5：为何消除波束色散

在新方案中，相位权重 `psi_n(f_m)` 是**频率相关的**。优化器以理论相位为初始化：

```
psi_n^0(f_m) = -2*pi * n * d * f_m / c * sin(theta_t)
```

然后在此基础上微调，以满足零陷和旁瓣约束。

由于 `psi_n(f_m) 正比于 f_m`，对于任意频率 `f`，施加的相位都与该频率的波长 `lambda(f) = c/f` 精确匹配。因此：

```
P(f, theta_t) = (1/N) * sum_{n=0}^{N-1} a_n(f) * exp( j * [psi_n(f) + 2*pi*n*d*f/c*sin(theta_t)] )
              ~ (1/N) * sum_{n=0}^{N-1} a_n(f)           [理想情况下相位抵消为0]
              ~ 1
```

所有频率在 `theta_t` 处相干叠加，形成**无色散的锐利的频率无关主瓣**。

#### 步骤 6：两路信号的分离

对左耳信号 mod_L：
- 主瓣指向 `theta_L`
- 零陷指向 `theta_R`（右耳方向）

对右耳信号 mod_R：
- 主瓣指向 `theta_R`
- 零陷指向 `theta_L`（左耳方向）

两路 8 通道信号在时域平均后输出：

```
y_n(t) = [y_L,n(t) + y_R,n(t)] / 2
```

由于零陷优化，在 `theta_L` 处：
- `y_L` 的主瓣能量最大
- `y_R` 的零陷深度可达 -20 dB 以下（取决于 LUT 质量）

因此两路信号在空间中**独立可辨**，听者感受到两个分离的声像。

---

## 2. 信号处理 Pipeline

每 25 ms（HOP）一次 tick：

```
+-------------------------------------------------------------+
| 1 tracker.get_ear_pose() -> (theta_L, theta_R, d_L, d_R)   |
| 2 audio_source.frames() -> mono 50 ms @ 96 kHz              |
| 3 hrtf_renderer.render_stereo(mono, theta_L, theta_R) -> (s_L, s_R) |
| 4 audio_adjuster.adjust(s_L, s_R, d_L, d_R) -> 距离补偿     |
| 5 np.clip(s_L/s_R, -1, 1) -> 限幅                           |
| 6 modulator.modulate_multi(s_L, s_R) -> (mod_L, mod_R)      |
|     DSB-AM: 0.5*Re{(1+s)*exp(j*2*pi*f_c*t)}                 |
|     左右耳共享同一载波相位                                   |
| 7 beamformer.combine(theta_L, theta_R, mod_L, mod_R) -> 8 通道      |
|     apply_passband(mod_L, theta_L, theta_R): 频域逐频点零陷加权     |
|     apply_passband(mod_R, theta_R, theta_L): 对向零陷               |
|     两路 8 通道时域平均                                      |
| 8 playback.push(block) -> ASIO 环形缓冲                      |
+-------------------------------------------------------------+
```

与 v1.0 的关键差异：
- **步骤 6 提前**：先调制，后波束形成（与参考代码顺序一致）
- **步骤 7 改为频域操作**：不再是基带复常数权重，而是 FFT -> 逐频点幅相加权 -> IFFT

---

## 3. 与参考代码的对照

### 3.1 功能映射表

| 功能 | 参考代码（音频生成） | 现有代码（directional_speaker） |
|------|---------------------|-------------------------------|
| DSB-AM 调制 | `beamforming_pattern_gen.py:1118` | `modulator.py:DSBAMModulator.modulate()` |
| 单音频频域相位偏移 | `beamforming_pattern_gen.py:get_wideband_phaseshift_wav()` | `beamformer.py:NullSteeringBeamformer.apply_passband()` |
| 多音频 8 通道合成 | `beamforming_pattern_gen.py:get_sdm_plus_wav_with8channelwavs()` | `beamformer.py:NullSteeringBeamformer.combine()` |
| 宽频零陷优化 | `optimization_difffreq_widenullsteering.py:optimize_cone()` | `scripts/calibrate_nullsteering.py:_optimize_one()` |
| 仿真接收验证 | `simu_beamforming.py:Simu_Receive()` | （未移植，可用参考代码验证） |
| 预失真优化 | `optimization_predistortion.py:optimize_input_audio()` | （未集成，可选） |

### 3.2 关键差异

| 差异点 | 参考代码 | 现有代码 | 原因 |
|--------|---------|---------|------|
| 优化器 | PyTorch Adam | SciPy L-BFGS-B | 避免 PyTorch 依赖 |
| 处理粒度 | 整段音频一次性 FFT | 50 ms 帧实时处理 | 实时流水线要求 |
| 载波频率 | 21 kHz | 40 kHz | 硬件换能器中心频率 |
| 阵元间距 | 8 mm | lambda/2 ~ 4.287 mm | 40 kHz 半波长 |
| LUT 格式 | 每对角度一个 JSON | 所有角度一个 JSON | 减少文件数量 |
| **处理顺序** | 先调制后波束形成 | 先调制后波束形成 | **已对齐** |

### 3.3 如何与参考代码结合使用

**场景 A：用参考代码验证 LUT 质量**

```bash
cd 音频生成
python simu_beamforming.py \
  --channel8_wavpath ../DirectionalSpeaker/data/recorded_8ch.wav \
  --directions_phis 0,40
```

生成仿真接收音频后，用 `simu_lowfreq_audios/` 中的低通检波文件分析零陷深度。

**场景 B：用参考代码生成离线测试音频**

```bash
cd 音频生成
python beamforming_pattern_gen.py --directions_phis 0,40
python optimization_predistortion.py --syned_wavpath ...
```

生成的 `modulated_audios_disopt/*.wav` 可作为 golden reference，与实时系统输出的录音做对比。

**场景 C：参数调优**

如需更激进的零陷深度，可在参考代码的 `optimization_difffreq_widenullsteering.py` 中调整损失系数，再将优化后的 `parameters.json` 转换为 LUT 格式。

---

## 4. LUT 离线生成

### 4.1 运行

```bash
cd DirectionalSpeaker
python scripts/calibrate_nullsteering.py
```

参数：
- `--workers N`：并行进程数（默认 CPU-1）
- `--dry-run`：只打印网格大小
- `--out path`：输出路径（默认 `data/beam_weights/nullsteering_lut.json`）

### 4.2 预期输出

```
Grid: 41 angles x 41 pairs = 1681 combos
Freqs: 81 bins  (36000.0 .. 44000.0 Hz)
Vars per combo: 1296
...
[calibrate] 0_40  loss=-123.456  iters=342  time=12.3s
...
Wrote LUT (1681 entries) to data/beam_weights/nullsteering_lut.json
```

### 4.3 耗时与体积

| 配置 | 单核 | 8 核 |
|------|------|------|
| 1681 combos x 2000 iter | ~4-6 小时 | ~30-60 分钟 |

JSON 格式约 60 MB，运行时全量载入内存。

---

## 5. 实时运行

### 5.1 虚拟模式（固定角度）

```bash
# dummy 后端（不出声，验逻辑）
python -m directional_speaker.main --mode virtual --angle 0 --backend dummy --duration 3

# ASIO 硬件播放
python -m directional_speaker.main --mode virtual --angle 0 --distance 1.0
```

### 5.2 Live 模式（摄像头追踪）

```bash
python -m directional_speaker.main --mode live --camera-height -0.20
```

### 5.3 验证清单

| 检查项 | 方法 |
|--------|------|
| LUT 已生成 | `ls data/beam_weights/nullsteering_lut.json` |
| 依赖完整 | `python scripts/verify_env.py` |
| 单元测试 | `python -m pytest directional_speaker/tests/ -v` |
| 虚拟模式冒烟 | `python -m directional_speaker.main --mode virtual --angle 0 --backend dummy --duration 3` |

---

## 6. 参数表

| 参数 | 值 | 说明 |
|------|-----|------|
| `FC_HZ` | 40_000 | 载波频率 |
| `FS_HZ` | 96_000 | DAC 采样率 |
| `N_CHANNELS` | 8 | 通道数 |
| `ELEMENT_SPACING_M` | lambda/2 ~ 4.287 mm | 阵元间距 |
| `THETA_STEP_DEG` | 3.0 | LUT 角度量化步长 |
| `PASSBAND_BW_HZ` | 4000.0 | 边带带宽 +/-4 kHz |
| `FREQ_STEP_HZ` | 100.0 | LUT 频率步长 |
| `W_MAIN` | 10.0deg | 主瓣区半宽 |
| `W_NULL` | 10.0deg | 零陷区半宽 |
| `COEF_MAIN` | -1.0 | 主瓣最大化系数 |
| `COEF_SIDE` | 0.5 | 旁瓣最小化系数 |
| `COEF_NULL` | 10.0 | 零陷最小化系数 |
| `COEF_VAR` | 1000.0 | 频率方差最小化系数 |

---

## 7. 关键代码片段

### 7.1 频域逐频点加权

```python
def apply_passband(self, x, target_deg, null_deg):
    T = x.shape[0]
    X = np.fft.rfft(x)           # (n_fft,)
    freqs_fft = np.fft.rfftfreq(T, 1.0 / cfg.FS_HZ)
    amp, phase = self._get_weights(target_deg, null_deg)  # (81, 8)

    W = np.ones((len(X), cfg.N_CHANNELS), dtype=complex)
    half_step = cfg.FREQ_STEP_HZ / 2.0
    for j in range(len(self.lut_freqs)):
        f_c = self.lut_freqs[j]
        mask = (freqs_fft >= f_c - half_step) & (freqs_fft < f_c + half_step)
        w = amp[j, :] * np.exp(1j * phase[j, :])
        W[mask, :] = w

    X_weighted = X[:, None] * W   # (n_fft, 8)
    out = np.fft.irfft(X_weighted, axis=0, n=T)
    return out.T.astype(np.float32)  # (8, T)
```

### 7.2 左右耳对向零陷合成

```python
def combine(self, theta_L_deg, theta_R_deg, mod_L, mod_R):
    out_L = self.apply_passband(mod_L, theta_L_deg, theta_R_deg)
    out_R = self.apply_passband(mod_R, theta_R_deg, theta_L_deg)
    out = (out_L + out_R) / 2.0
    if np.max(np.abs(out)) > 1.0:
        out = out / np.max(np.abs(out))
    return out.astype(np.float32)
```

### 7.3 共享载波相位调制

```python
def modulate_multi(self, *signals):
    T = signals[0].shape[0]
    t_idx = np.arange(self._n_emitted, self._n_emitted + T)
    carrier = np.exp(2j * np.pi * self.fc * t_idx / self.fs)
    outs = []
    for z in signals:
        out = 0.5 * np.real((1.0 + z) * carrier)
        outs.append(out.astype(np.float32))
    self._n_emitted += T
    return outs
```

---

## 8. 故障排除

| 现象 | 原因 | 解决 |
|------|------|------|
| `LUT not found` | 未运行 `calibrate_nullsteering.py` | 运行脚本生成 LUT |
| `KeyError: target=0 null=39` | 角度未量化到 3deg 网格 | 自动量化到最近网格；如缺失则重跑脚本 |
| 只有一个主瓣 | 零陷深度不足 / 波束色散未消除 | 确认 LUT 已加载；增大距离测试 |
| 全方向都有声音 | 扬声器接线错误 / 通道映射不对 | 检查 ASIO 通道 0~7 映射 |
| 有爆裂声 | 输出幅度 >1 | 降低 input 音量或 adjuster 增益 |
| `underruns` 很多 | 计算跟不上 | 关闭 HRTF（`--no-hrtf`） |

---

*v1.1 基于 `音频生成` 参考代码重构，采用频域逐频点零陷波束形成。旧版 eigenfilter 方案见 `MANUAL.md`（v1.0）。*
