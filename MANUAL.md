# 8 通道超声方向性扬声器 — 新手上路手册 v1.2

> **v1.2 目标**：让第一次接触本项目的人，不需要看代码，只靠这份手册就能跑通所有测试和实验。  
> **v1.1 的已知补充**：v1.2 新增"各脚本逐步执行流程"专章，并以更口语化的方式重写全部操作步骤。  
> 如需深入理解物理原理、模块架构、D435I 外参推导，请查阅 `MANUAL_OVERVIEW_v1.1.md`。

---

## 整体流程图（先看这里）

```
你拿到代码后，按顺序做这 5 件事：

┌─────────────────────────────────────────────────────────┐
│  第 1 步  装依赖 + 环境自检                              │  verify_env.py
│  第 2 步  跑单元测试（纯软件，不需要任何硬件）           │  pytest
│  第 3 步  虚拟模式快跑（假设用户固定在某个方向）         │  main.py --mode virtual
│  第 4 步  摄像头 live 模式（摄像头实时追踪用户位置）     │  main.py --mode live
│  第 5 步  离线工具脚本（看图、重新校准 β）               │  scripts/
└─────────────────────────────────────────────────────────┘

没有 ASIO 声卡？第 3、4 步加 --backend dummy，只验 Python 逻辑，不出声。
没有 D435I？第 4 步跳过，做第 3 步就够了。
```

---

## 目录

- [第 1 步：装依赖 + 环境自检](#第-1-步装依赖--环境自检)
- [第 2 步：跑单元测试](#第-2-步跑单元测试)
- [第 3 步：虚拟模式（预设方向）](#第-3-步虚拟模式预设方向)
- [第 4 步：摄像头 live 模式](#第-4-步摄像头-live-模式)
- [第 5 步：离线工具脚本](#第-5-步离线工具脚本)
- [附录：常见报错速查](#附录常见报错速查)

---

## 第 1 步：装依赖 + 环境自检

### 1.1 进入项目目录，建虚拟环境

> 打开 **命令提示符（cmd）或 PowerShell**，把工作目录切换到 `DirectionalSpeaker/`。

```bat
cd DirectionalSpeaker
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements.txt
```

**什么是虚拟环境？** 就是一个隔离的 Python 小盒子，安装的包只在这个项目里生效，不污染系统环境。每次新开终端都要重新激活（`.\.venv\Scripts\activate`）。

### 1.2 运行环境自检脚本

```bat
python scripts/verify_env.py
```

**这个脚本做了什么：**
1. 逐个尝试 `import` 所有依赖包（numpy、scipy、sounddevice 等）
2. 列出系统里能用的所有音频设备，帮你找 ASIO 声卡的名字
3. 把可选包（pyrealsense2、mediapipe、opencv）标注为 WARN 而不是 FAIL——没装也能继续

**正常输出长这样：**

```
  OK  numpy                1.26.4
  OK  scipy                1.13.0
  OK  matplotlib           3.9.0
  OK  soundfile            0.12.1
  OK  sounddevice          0.4.7
  WARN cv2                 No module named 'cv2'       ← 可选，不影响虚拟模式
  WARN pyrealsense2        No module named 'pyrealsense2'  ← 可选，live模式才需要
  WARN mediapipe           No module named 'mediapipe'     ← 可选，live模式才需要

Audio hostapis:
  - MME
  - Windows DirectSound
  - ASIO                        ← 看到 ASIO 说明驱动已装

Audio devices (output >=8 channels):
  [  3] LST 8ch ASIO  (hostapi=ASIO, out=8, fs=96000)   ← 记下这个名字
```

**没看到 ASIO？** 声卡驱动没装，或者换了个插口。暂时不影响做第 2、3 步（用 `--backend dummy`）。

---

## 第 2 步：跑单元测试

> **不需要任何硬件**，纯 Python 计算验证。这一步通了才说明代码本身没问题。

```bat
python -m pytest directional_speaker/tests/ -v
```

**这个命令做了什么：** 找 `tests/` 目录下所有以 `test_` 开头的文件，逐一执行里面的测试函数，最后汇报通过/失败。

**期望输出（61 个测试全绿）：**

```
collected 61 items

tests/test_beam_width_warning.py ...          [  4%]
tests/test_beamformer.py ............         [ 23%]
tests/test_beta_scan.py ..                    [ 27%]
tests/test_head_tracker.py ........           [ 40%]
tests/test_joint_norm.py .........................  [ 82%]
tests/test_modulator.py ...                   [100%]

============================== 61 passed in 0.74s ==============================
```

### 各测试文件测了什么

| 测试文件 | 测试内容 | 一句话说明 |
|---|---|---|
| `test_beamformer.py` | 波束赋形权重求解 + 阵列方向图指标 | 验证主瓣方向对、旁瓣压制够、主瓣宽度合理 |
| `test_modulator.py` | DSB-AM 调制器 | 验证 40 kHz 上变频后幅度不超过 1（不会让 DAC 饱和）|
| `test_joint_norm.py` | 联合归一化（L/R 联合限幅） | 2000 次随机信号，每次确认 \|x\| ≤ 1 |
| `test_head_tracker.py` | 虚拟位置追踪器几何计算 | 验证 0°/±60° 下耳道坐标、距离、张角公式正确 |
| `test_beam_width_warning.py` | 主瓣窄于耳道张角时的告警 | 用户靠太近时确认日志能触发 `beam narrower` 警告 |
| `test_beta_scan.py` | β 参数扫描框架 | 验证 β LUT 能给每个方向挑到合格的旁瓣抑制值 |

**某个测试失败了怎么办？**

```bat
:: 只跑失败的测试，打印详细日志
python -m pytest directional_speaker/tests/test_beamformer.py -v --tb=long
```

最常见原因：包版本不对。解决方法：

```bat
pip install -r requirements.txt -U
```

---

## 第 3 步：虚拟模式（预设方向）

> **虚拟模式** = 声音方向提前写死，不用摄像头。适合：没有 D435I、测试某个固定角度的效果、或者只想先听一听系统有没有出声。

### 3.1 最快的验证（无需 ASIO，不出声，只验 Python 逻辑）

```bat
python -m directional_speaker.main --mode virtual --angle 0 --backend dummy --duration 3
```

**各参数说明：**

| 参数 | 含义 |
|---|---|
| `--mode virtual` | 用预设方向，不用摄像头 |
| `--angle 0` | 声束方向：正前方（0°） |
| `--backend dummy` | 假声卡，不真实播放，只走 Python 计算 |
| `--duration 3` | 跑 3 秒自动停止（不加此参数则需要 Ctrl-C 停止）|

**期望输出：**

```
INFO  directional_speaker.main: prewarming beamformer...
INFO  directional_speaker.main: prewarm 138.2 ms
INFO  directional_speaker.playback: DummyPlayback started
INFO  directional_speaker.main: ticks=40  underruns=0  pose theta=(L-4.0, R4.0) d=(L1.00, R1.00)
INFO  directional_speaker.main: stopped. ticks=120 underruns=0 duration=3.00s
```

看到 `underruns=0` 且 `stopped` 就说明整条流水线跑通了。

### 3.2 三个方向依次测试

```bat
:: 正前方 0°（声束指向用户正脸）
python -m directional_speaker.main --mode virtual --angle 0 --backend dummy --duration 3

:: 左 60°（假设用户在左边）
python -m directional_speaker.main --mode virtual --angle -60 --backend dummy --duration 3

:: 右 60°（假设用户在右边）
python -m directional_speaker.main --mode virtual --angle 60 --backend dummy --duration 3
```

三条命令都跑完、都没有报错，说明三个方向的波束权重计算全部正常。

### 3.3 接真实声卡实际出声

**前提：** `verify_env.py` 已经看到 ASIO 设备名（比如 `LST 8ch ASIO`）。

```bat
:: 正前方，实际播放，按 Ctrl-C 停止
python -m directional_speaker.main --mode virtual --angle 0

:: 左 60°，距离 1.2 m
python -m directional_speaker.main --mode virtual --angle -60 --distance 1.2

:: 不用 CIPIC HRTF（没下载 subject_003.mat 时用这个）
python -m directional_speaker.main --mode virtual --angle 0 --no-hrtf
```

**如果没有 `data/audio/` 里的 wav 文件**，程序会自动生成合成语音，打印一行：

```
WARNING: data/audio/speech.wav missing; writing synthetic speech
```

这是正常的，不影响运行。

### 3.4 整条流水线内部发生了什么（每 25 ms 一次）

```
┌──────────────────────────────────────────────────────────────────┐
│ 每 25 ms（一次 tick）的处理顺序                                   │
│                                                                   │
│  ① 获取耳道位置                                                   │
│     virtual 模式：直接返回写死的 (θ_L, θ_R, d_L, d_R)            │
│     θ_L ≈ θ_写死 − 4°，θ_R ≈ θ_写死 + 4°（两耳间距产生的偏差）  │
│                                                                   │
│  ② 读下一帧 50 ms 单声道音频（96 kHz，4800 个采样点）            │
│                                                                   │
│  ③ HRTF 渲染：单声道 → 双耳 (s_L, s_R)                          │
│     模拟耳廓对声音的频率响应差（让声音有"方向感"）                │
│                                                                   │
│  ④ 距离补偿：远的人声音小一点                                     │
│                                                                   │
│  ⑤ 限幅：把 s_L, s_R 压到 [-1, 1]，防止后续溢出                  │
│                                                                   │
│  ⑥ 波束赋形：8 路复数权重，把双耳信号合成为 8 通道               │
│     效果：40 kHz 超声在空中"相干叠加"后只在目标方向产生可听声    │
│                                                                   │
│  ⑦ DSB-AM 调制：把 20 kHz 以内的音频搬到 40 kHz 载波上          │
│                                                                   │
│  ⑧ 推入声卡 ASIO 环形缓冲，等待硬件取走                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 第 4 步：摄像头 live 模式

> **live 模式** = D435I 摄像头实时拍用户脸，MediaPipe 找到耳朵在哪，程序自动把声束对准用户的耳朵。**用户动头，声束跟着动。**

### 4.1 前提检查清单（逐项打钩再继续）

```
□ 1. D435I 摄像头用 USB 3.0 数据线连到电脑（蓝色口）
     → 打开 Intel RealSense Viewer，看到深度图、RGB 图 = 连接正常

□ 2. 安装 live 模式专用依赖
     pip install opencv-python pyrealsense2 mediapipe

□ 3. 再次运行环境自检，确认三个库都 OK
     python scripts/verify_env.py
     → OK cv2 / OK pyrealsense2 / OK mediapipe 三行

□ 4. 确认相机安装位置
     - 摄像头固定在阵列正下方（你的实际安装方式）
     - 量一下：阵列几何中心到摄像头镜头中心的垂直距离（单位：米）
     - 例：量到 0.18 m

□ 5. 把带符号的高度写入 config.py（下方或正下方用负值）
     CAMERA_HEIGHT_M: float = -0.18   ← 改成你量到的值（负号不能丢！）
     
□ 6. CIPIC HRTF 文件（如果要听真实空间感）
     data/hrtf/subject_003.mat 文件已存在
     （没有就加 --no-hrtf，用合成 ITD 代替，空间感稍差但能跑）
```

**为什么高度是负数？** 相机在阵列下方，在程序的坐标系里意味着相机中心低于阵列中心，所以是负值。搞错符号会导致耳道高度计算差 40 cm 以上，声束方向明显偏。

### 4.2 首次试跑（dummy 声卡，只验摄像头追踪）

```bat
python -m directional_speaker.main --mode live --backend dummy --duration 5
```

**期望输出：**

```
INFO  directional_speaker.main: prewarming beamformer...
WARNING  directional_speaker.head_tracker: extrinsic data/extrinsic.json missing,
         building from camera_height=-0.180 m          ← 看到负值说明配置正确
INFO  directional_speaker.main: prewarm 141.3 ms
INFO  directional_speaker.main: ticks=12  underruns=0
         pose theta=(L-7.2, R1.1) d=(L0.93, R0.91)    ← 看到实时角度/距离在变化
INFO  directional_speaker.main: stopped. ticks=200 underruns=0 duration=5.00s
```

**用手遮住脸、再移开**，观察 `theta` 和 `d` 数字的变化。数字跟着你的头部运动变化 = 追踪正常。

### 4.3 接真实声卡出声

```bat
:: 完整 live 模式，有 CIPIC HRTF
python -m directional_speaker.main --mode live

:: live 模式，不用 CIPIC（更快启动）
python -m directional_speaker.main --mode live --no-hrtf

:: live 模式，指定相机高度（不改 config.py 也行）
python -m directional_speaker.main --mode live --camera-height -0.18
```

按 **Ctrl-C** 停止，程序会打印最终统计：

```
INFO  stopped. ticks=1847 underruns=2 duration=46.17s
```

`underruns` 是声卡缓冲空了的次数，偶尔 1-2 次正常；超过 5 次/分钟说明计算跟不上，尝试加 `--no-hrtf`。

### 4.4 摄像头追踪内部发生了什么（live 模式专属部分）

```
┌──────────────────────────────────────────────────────────────┐
│ live 模式下，步骤①（获取耳道位置）的详细过程：              │
│                                                              │
│  a. D435I 每秒产生 30 帧 RGB（1280×720）+ 深度（848×480）   │
│                                                              │
│  b. 深度对齐到 RGB：让每个 RGB 像素都能查到对应的距离值      │
│                                                              │
│  c. MediaPipe Face Mesh：在 RGB 图上找到 468 个人脸特征点   │
│     → 取 #234（左耳）、#454（右耳）两个点的像素坐标 (u, v)  │
│                                                              │
│  d. 深度反投影：用 (u, v) + 深度值 + 摄像头内参             │
│     → 得到耳道在相机坐标系里的三维坐标 (x_c, y_c, z_c)     │
│                                                              │
│  e. 坐标变换：相机坐标 → 阵列坐标                           │
│     用 _build_extrinsic(-0.18) 或 data/extrinsic.json       │
│     → 得到 (x_arr, y_arr, z_arr)                            │
│                                                              │
│  f. 计算方位角：θ = atan2(x_arr, z_arr)（单位：度）          │
│     计算距离：d = sqrt(x²+y²+z²)                            │
│                                                              │
│  g. EMA 平滑（α=0.5）：混合当前帧和上一帧，减少抖动         │
│     如果某帧脸没被检测到，返回上一帧的值                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 第 5 步：离线工具脚本

这些脚本不是每次都要跑，只有在特定情况下才用。

### 5.1 `scripts/verify_env.py` — 环境自检

```bat
python scripts/verify_env.py
```

**什么时候用：** 每次装完依赖、换了环境、或排查"为什么 live 模式报 ImportError"时用。

**输出含义：**
- `OK` = 包已装，版本号在后面
- `WARN` = 可选包没装，只影响 live 模式或图形功能
- `FAIL` = 必装包没装，所有模式都会出错

---

### 5.2 `scripts/calibrate_beta.py` — 重新校准 β 参数

```bat
python scripts/calibrate_beta.py
```

**什么时候用：** 一般情况**不需要跑**，仓库里的 `config.py` 已经有校准好的 `BETA_LUT`。只有在以下情况才重跑：
- 修改了物理参数（`N_ELEMENTS`、`ELEMENT_SPACING_M`、`FC_HZ` 等）
- 想验证 PSLL 指标是否符合目标
- 仓库的 BETA_LUT 被意外清空

**这个脚本做了什么（约 30–60 秒）：**

```
步骤 1: 对每个方向角（-60° 到 +60°，每度一个）
        扫描 ~35 个 β 值（0.1 到 100，等比数列）
        → 计算每种组合的旁瓣抑制 + 主瓣误差

步骤 2: 给每个方向选最小的 β，条件：
        a) 主瓣峰值误差 ≤ 1°
        b) 旁瓣抑制 ≤ 软目标（-13 dB）
        退而求其次：满足硬目标（-10 dB）
        再退：在合理范围里找最好的

步骤 3: 把结果写入三个地方：
        - reports/beta_scan.json（完整数据）
        - reports/images/beta_pareto.png（β vs PSLL 图）
        - reports/images/beta_lut.png（β(θ₀) 曲线图）
        - directional_speaker/config.py（直接改 BETA_LUT 和 BETA 两行）
```

**正常输出：**

```
LUT built: 121 theta0 buckets.
  soft (-13 dB): 104
  hard (-10 dB): 17
  best-effort:   0
  bartlett:      0
  default beta (median) = 2.3819
patched directional_speaker/config.py
```

---

### 5.3 `scripts/make_figures.py` — 生成校准图

```bat
python scripts/make_figures.py
```

**什么时候用：** 查看当前参数下的波束方向图，或者给报告/论文出图。

**这个脚本做了什么（约 10–20 秒）：**

```
生成 5 张图，保存到 reports/images/：

① af_theta0_0.png
   θ₀=0° 时的阵列方向图（纵轴 dB，横轴方位角）
   标注了主瓣宽度、旁瓣电平、PSLL

② beam_scan.png
   5 个方向（-60°/-30°/0°/+30°/+60°）叠在一张图上
   看各方向的波束形状对不对

③ joint_norm_mc.png
   2000 次随机测试：验证 |x[k,t]| ≤ 1 从未溢出
   这是保证 DAC 不饱和的关键指标

④⑤ beta_pareto.png / beta_lut.png
   已由 calibrate_beta.py 生成；这里跳过（复用旧图）
```

**正常输出：**

```json
{
  "files": ["af_theta0_0.png", "beam_scan.png", "beta_lut.png", "beta_pareto.png", "joint_norm_mc.png"],
  "joint_norm_max_peak": 0.9987
}
```

`joint_norm_max_peak < 1.0` 就说明归一化正确。

---

### 5.4 `python -m directional_speaker.calibration` — 摄像头外参标定（可选）

```bat
python -m directional_speaker.calibration
```

**什么时候用：** 相机安装位置不满足"正下方、未倾斜、可量距离"三个条件时（例如侧置、倾斜）。绝大多数情况下**不需要跑**，用 §4.1 的高度法即可。

**前提：** 已装 `opencv-python` + `pyrealsense2`。

**这个脚本做了什么：**

```
打开 D435I 摄像头，显示 RGB 预览窗口。

你需要做的：
  - 把一张 9×6 棋盘格（20 mm 方格）对准阵列面
  - 按 SPACE 键采集 5 帧（可以换角度多拍几张）
  - 按 ESC 完成

脚本自动：
  - 找棋盘格角点 → solvePnP → 得到摄像头到棋盘格的变换
  - 假设棋盘格与阵列面重合，得到摄像头到阵列的变换
  - 把 4×4 矩阵写入 data/extrinsic.json

写入后，主程序优先读这个文件（不再用高度法）。
删掉文件即恢复高度法。
```

---

## 第 6 步：实验场景操作指南

> 以下是两种主要实验场景的完整操作流程。

### 场景 A：预设方向测试（virtual 模式）

**适用情况：** 验证某个固定角度的主观效果、做旁听泄露测试、没有 D435I。

**完整操作步骤：**

```
① 物理布置：
   - 阵列放在桌/三脚架上，距用户正前方 0.8–1.2 m
   - 阵列中心齐用户头部高度

② 确定测试角度：
   - 0°  = 用户在阵列正前方
   - -60° = 用户在阵列左前方 60°
   - +60° = 用户在阵列右前方 60°

③ 启动播放：
```

```bat
:: 0° 正前方，1.0 m
python -m directional_speaker.main --mode virtual --angle 0 --distance 1.0

:: -60° 左侧，1.2 m
python -m directional_speaker.main --mode virtual --angle -60 --distance 1.2

:: +60° 右侧，0.8 m
python -m directional_speaker.main --mode virtual --angle 60 --distance 0.8
```

```
④ 主观记录（表格见下方）：
   - 用户报告声音方向（左/右/前）
   - 旁听者（在主方向旁 30°）报告能否听清
   - 改变距离（0.8 / 1.0 / 1.2 m）重复

⑤ 按 Ctrl-C 停止
```

---

### 场景 B：摄像头实时追踪（live 模式）

**适用情况：** 用户自由移动头部，测试声束跟踪效果。

**完整操作步骤：**

```
① 物理布置（与场景 A 相同）

② 检查 config.py 里 CAMERA_HEIGHT_M 是你的实测负值
   例：CAMERA_HEIGHT_M: float = -0.18

③ 开启摄像头，确认 D435I 已被 RealSense Viewer 识别

④ 启动 live 模式：
```

```bat
python -m directional_speaker.main --mode live
```

```
⑤ 测试项目：

   测试 F：头部追踪延迟
   - 用户以约 30°/秒的速度左右摆头
   - 主观感受：声像是否跟得上头部运动（目标：延迟 < 100 ms）

   测试 G：遮挡恢复
   - 用手遮住脸不超过 1 秒，再移开
   - 确认声像在 2 秒内恢复正确方位

   测试 E：近距离告警
   - 用户靠近到距阵列 0.3 m
   - 查看终端日志，确认出现：
     WARNING: beam narrower than ear opening ...

⑥ 按 Ctrl-C 停止，记录最终 underruns 数
```

---

### 实验记录表

复制到 `reports/experiment_log.csv`：

```
timestamp,mode,angle_deg,distance_m,subject_id,perceived_side,underruns,notes
2026-05-12 10:00,virtual,0,1.0,S01,front,0,"clear localization"
2026-05-12 10:05,virtual,-60,1.2,S01,left,0,"correct"
2026-05-12 10:10,live,auto,auto,S01,correct,2,"slight delay when fast turn"
```

---

## 附录：常见报错速查

| 报错信息 | 原因 | 解决 |
|---|---|---|
| `ImportError: DLL load failed while importing pyrealsense2` | Intel RealSense SDK 未装 | 装 SDK → 重启电脑 → 再 pip install pyrealsense2 |
| `RuntimeError: Couldn't resolve requests` | USB 2.0 或线缆问题 | 换 USB 3.0 蓝色口 + 高质量数据线 |
| `ValueError: --angle must be one of (-60, 0, 60)` | virtual 模式角度必须是这三个值 | 改用 live 模式，或选 -60/0/60 |
| `FileNotFoundError: CIPIC HRTF` | subject_003.mat 没下载 | 加 `--no-hrtf` 参数 |
| `PortAudioError: No ASIO device` | ASIO 驱动没装或设备名不对 | 先跑 verify_env.py 确认；暂时用 --backend dummy |
| `no face detected` (live 模式) | 光太暗 / 太远 / 脸被遮挡 | 加光照；保持 0.5–1.5 m；摘口罩/墨镜 |
| `underruns` 很多（> 5/分钟）| 计算跟不上实时要求 | 加 `--no-hrtf`；关闭其他程序 |
| `beam narrower than ear opening`（频繁出现）| 用户离阵列太近 | 拉远到 ≥ 0.8 m |
| 日志里 `camera_height=0.200` 但你设的是 −0.18 | 没重新激活 venv，读了旧 config | `.\.venv\Scripts\activate` 后重启 |
| 所有单测失败 | 依赖版本冲突 | `pip install -r requirements.txt -U` |

---

*v1.2 基于 v1.1 编写，侧重执行流程。深入原理请查阅 `MANUAL_OVERVIEW_v1.1.md`。*
