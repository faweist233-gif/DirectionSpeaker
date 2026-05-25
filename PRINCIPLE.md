# DirectionalSpeaker — 原理与数学推导(新手向)

> 配套文档:`MANUAL.md`(操作)、`reports/DECISIONS.md`(设计取舍)。
> 本文给出**所有数学推导**与代码对应位置(`file:line`)。所有物理常量见
> `directional_speaker/config.py`,本文中出现的符号一律以那里的值为准。
>
> **阅读须知**:本文写给第一次接触参数阵 / 阵列处理 / HRTF 的读者。
> 每一节先用一段话讲"这一节解决什么、为什么需要它",再给数学;
> 所有缩写词、希腊字母、专业术语第一次出现时都会标注或解释。

---

## 0. 预备知识

### 0.1 一句话讲清楚这套系统在干什么

普通扬声器把声音"撒"到整个房间;**定向扬声器**只想让声音"沿一条窄
波束"射到指定的人耳里。本项目用 8 个**超声**换能器,把可闻信号
"贴"在 40 kHz 载波上发射出去,空气自身因为非线性会把超声"解调"
回可闻声,而 40 kHz 波长很短(8.6 mm),小尺寸阵列就能做出窄波束。
配合人脸追踪,我们能让左右耳分别听到不同的内容,做出"私人立体声"。

### 0.2 缩写词速查

| 缩写 | 全称 | 含义 |
|---|---|---|
| ULA | Uniform Linear Array | 阵元等距排列的直线阵列 |
| AF | Array Factor | 阵列因子,描述阵列的方向图 |
| DSB-AM | Double-Sideband Amplitude Modulation | 双边带幅度调制(传统 AM 广播的调制方式) |
| HRTF / HRIR | Head-Related Transfer Function / Impulse Response | 头相关传递函数 / 冲激响应,描述声音从空间某点传到耳道时被头与耳廓"染色"的效果 |
| ITD / ILD | Interaural Time / Level Difference | 双耳时间差 / 声压级差(人脑定位声源的两大线索) |
| FFT / IFFT | (Inverse) Fast Fourier Transform | (逆)快速傅里叶变换 |
| LUT | Look-Up Table | 查表,运行时不算只取 |
| FFT bin | FFT 的一个离散频率格 | 离散傅里叶变换输出的第 $k$ 个频率点,中心频率 $k f_s/T$ |
| ASIO | Audio Stream Input/Output | Steinberg 的低延迟音频驱动协议(Windows 专业音频用) |
| DAC | Digital-to-Analog Converter | 数模转换器(把 $[-1, 1]$ 浮点变成模拟电压) |
| THD | Total Harmonic Distortion | 总谐波失真,越小越好 |
| PSLL | Peak Side-Lobe Level | 峰值旁瓣电平,越低代表越"干净"的指向性 |
| EMA | Exponential Moving Average | 指数移动平均(一阶低通) |
| L-BFGS-B | Limited-memory BFGS with Bounds | 一种带变量上下界的拟牛顿优化算法 |
| KEMAR | Knowles Electronics Manikin for Acoustic Research | 标准声学假人头(测 HRTF 用) |
| CIPIC | UC Davis CIPIC Interface Lab | 公开 HRTF 数据库的提供方 |
| D435I | Intel RealSense D435i | 一款带 IMU 的深度相机 |
| Face Mesh | MediaPipe 的人脸 478 点稠密 landmark 模型 | landmark = 关键点 |
| tragus | 耳屏 | 耳道入口前方的小凸起,用作"耳的几何位置" |

### 0.3 数学记号约定

| 记号 | 含义 |
|---|---|
| $j$ | 虚数单位 $\sqrt{-1}$(电气工程惯例,不和指标 $j$ 混用时由上下文区分) |
| $\mathrm{Re}\{\cdot\}$ | 取复数实部 |
| $\Box^2 = \nabla^2$ | 拉普拉斯算子 $\partial_x^2+\partial_y^2+\partial_z^2$ |
| $\partial_t, \partial_t^2$ | 对时间的一阶、二阶偏导 |
| $\mathrm{Var}_j[\cdot]$ | 在指标 $j$ 上取方差 |
| $\mathbb{1}[\cdot]$ | 指示函数,条件为真取 1、否则取 0 |
| $\|\!|\mathbf{w}|\!|_1$ | 向量 $\mathbf{w}$ 的 1-范数 $\sum_n |w_n|$ |
| $\mathrm{atan2}(y, x)$ | 带象限信息的反正切,值域 $(-\pi, \pi]$ |
| $\propto$ | 正比于 |
| $\bar f$ | 量 $f$ 的均值 |
| 粗体 $\mathbf{x}$ | 向量或矩阵 |
| $a*b$ | 时域卷积 $\int a(\tau)b(t-\tau)\mathrm d\tau$ |

### 0.4 全局物理 / DSP 常量

| 符号 | 含义 | 代码常量 | 数值 |
|---|---|---|---|
| $c$ | 空气中声速 | `C_SOUND` | 343 m/s |
| $f_c$ | 超声**载波**频率 | `FC_HZ` | 40 000 Hz |
| $f_s$ | DAC **采样率** | `FS_HZ` | 96 000 Hz |
| $\lambda_c$ | 载波波长 $c/f_c$ | `LAMBDA_M` | 8.575 mm |
| $N$ | 阵列通道数 | `N_CHANNELS` | 8 |
| $d$ | 阵元间距 $\lambda_c/2$ | `ELEMENT_SPACING_M` | 4.287 mm |
| $T_w$ | 分析窗口长度 | `WINDOW_MS` | 50 ms (= $4800$ 样本) |
| $T_h$ | 帧间跳跃长度 | `HOP_MS` | 25 ms (= $2400$ 样本) |
| $B$ | 单边带带宽(载波两侧各 $B$ Hz) | `PASSBAND_BW_HZ` | 4000 Hz |
| $\Delta f$ | LUT 频率离散步长 | `FREQ_STEP_HZ` | 100 Hz |
| $\Delta\theta$ | LUT 角度离散步长 | `THETA_STEP_DEG` | 3° |
| $W_i$ | 双耳间距(interaural width) | `INTERAURAL_M` | 0.17 m |
| $W_\text{ear}$ | 单耳"收声口"横向尺度 | `EAR_APERTURE_M` | 60 mm |
| $h$ | 相机相对阵列的垂直偏移 | `CAMERA_HEIGHT_M` | 见 config |

### 0.5 坐标系

阵列固定在原点,8 个阵元沿 $x$ 轴排成一条直线:

```
   +y(上)
     ▲
     │
     │           ← 用户在这一侧 ($+z$)
     │
─────┼─────►  +x(右)
     │
     ▼ (+z 朝外,垂直纸面指向读者)
```

方位角定义:$\theta = \mathrm{atan2}(x, z)$。
$\theta = 0$ 表示正前方(主轴),$\theta > 0$ 表示用户偏右,$\theta < 0$ 偏左。

---

## 1. 系统总览

下图是每 25 ms 跑一次的完整流水线:

```
mono(t)  ── 1 路单声道音频 (Wav 文件或麦克输入)
   │
   ▼
HRTF(θ_L, θ_R)         ← 根据两只耳的方位卷上各自的耳廓滤波器
   │
   ▼
(s_L, s_R)             ← 左右耳的基带信号(可闻波段)
   │
AudioAdjuster          ← 根据距离 d_L, d_R 给两路加增益(远的放大)
   │
(s_L', s_R')
   │
DSB-AM 调制(共享 40 kHz 载波相位)
   │
(x_L(t), x_R(t))       ← 实通带信号,峰值≤1,可直接进 DAC
   │
Null-Steering 频域加权(每耳一组 8 通道复权)
   │
y[k, t], k = 1..8      ← 8 通道超声通带,峰值≤1
   │
ASIO ── 8 路超声换能器(40 kHz)
   │
空气中非线性自解调(Berktay 效应)
   │
可闻声波束 → 用户左/右耳
```

每 25 ms 跳跃执行一次完整流水线;见 `directional_speaker/main.py:114-160`。

**关键直觉**:可闻方向性**不是**靠"低频音波"做出来的(8 mm 间距下
低频根本指向不了),而是靠"40 kHz 超声"先做窄波束、再让空气在沿
波束的传播路径上"自己解调"出可闻声。所以这是一个**先把超声做成
窄束、再借空气非线性把超声变可闻**的两段式系统。

---

## 2. 参数阵原理 (Berktay 远场解)

> 这一节解释:为什么发出去的是 40 kHz 超声,空气里却能听到正常的
> 可闻声?答案是空气在大声压下不再是线性介质,会自己产生差频。

### 2.1 空气是非线性介质

线性声学假设波动方程
$$\Box^2 p - \frac{1}{c^2}\frac{\partial^2 p}{\partial t^2}=0$$
精确成立($p$ = 声压扰动,$\Box^2$ 已在 0.3 节定义)。但当 $p$ 很大,
空气密度随声压非线性变化,Westervelt 方程把误差项显式写出:

$$
\Box^2 p - \frac{1}{c^2}\frac{\partial^2 p}{\partial t^2}
= -\underbrace{\frac{\beta}{\rho_0 c^4}}_{\text{非线性强度系数}}
\frac{\partial^2 p^2}{\partial t^2}
\tag{2.1}
$$

新符号说明:

| 符号 | 含义 | 典型值 |
|---|---|---|
| $p$ | 声压扰动 (Pa) | — |
| $\rho_0$ | 空气静止密度 (kg/m³) | 1.21 |
| $\beta$ | 空气非线性参数 | 1.2 |
| $\partial^2 p^2/\partial t^2$ | 声压**平方**对时间的二阶导 | 非线性源 |

右端的 $p^2$ 才是关键 —— 若把 $p$ 写成 $\cos(2\pi f_c t)$,
那么 $p^2 = \tfrac12(1 + \cos(4\pi f_c t))$,出现了 $0$ Hz 和 $2f_c$。
对窄带超声而言,这意味着两个频率分量 $f_1, f_2$ 一起传播时会差出
$f_2 - f_1$ 来 —— 这就是 **差频** 的物理由来。

### 2.2 Berktay 远场近似

把一束高指向性超声写成 "载波 × 慢变包络":

$$
p(z, t) = P_0\, E(t)\,\cos(2\pi f_c t)
\tag{2.2}
$$

| 符号 | 含义 |
|---|---|
| $P_0$ | 声源峰值声压 (Pa),由换能器与驱动电压决定 |
| $E(t)$ | 慢变包络,$\|E(t)\|\le 1$,载有可闻信号 |
| $z$ | 沿波束方向到声源的距离 |

把 (2.2) 代入 (2.1),沿 $+z$ 方向做远场近似(轴上),
Berktay (1965) 推得到达远场的**可闻分量**为

$$
\boxed{\ p_\text{aud}(z, t) \;\propto\;
\frac{\beta P_0^2 a^2}{16\,\rho_0\, c^4\, \alpha\, z}
\cdot \frac{\partial^2}{\partial t^2}\!\bigl[E^2(t - z/c)\bigr]\ }
\tag{2.3}
$$

新符号:

| 符号 | 含义 |
|---|---|
| $a$ | 换能器有效半径 (m),约束波束宽度 |
| $\alpha$ | 高频(超声)在空气中的吸收系数 (Np/m) |
| $z$ | 到声源的距离 |
| $t - z/c$ | 传播延时(声波从 $0$ 走到 $z$ 用了 $z/c$ 秒) |
| $p_\text{aud}$ | 听得见的那部分声压 |

**两条关键结论**:

1. **听到的是 $\partial^2_t[E^2]$,不是 $E$ 本身。** 即"包络平方
   的二阶导"。这暗示我们想让用户听到 $s(t)$,就得让包络满足
   $\partial^2_t [E^2] \propto s$。
2. 工程上,我们直接令 $E(t) = 1 + m\, s(t)$($m$ 是**调制度**),
   展开 $E^2 = 1 + 2m s + m^2 s^2$:
   - 常数 $1$ 被 $\partial_t^2$ 滤掉。
   - $2m s$ 是想要的可闻线性项。
   - $m^2 s^2$ 是**失真项**(非线性产物)。要让失真小必须 $m\ll 1$,
     但能量也就小;工程上一般取 $m=1$,接受约 −10 dB 的 THD,
     再用预失真补偿(本项目暂不做)。

### 2.3 这一节对代码意味着什么

代码层面我们**只负责生成 $p(t)$**(即 8 通道通带电压);非线性自解调
在空气里自动发生,不需要写一行代码。
所有可闻方向性都来自:**8 通道超声场在阵列正前方按 $\theta$ 方向聚焦**,
而不是传统电声扬声器的低频指向性(8 mm 间距下做不到)。

---

## 3. DSB-AM 调制与归一化

> 这一节回答:把可闻信号 $s(t)$ 怎样"贴"到 40 kHz 载波上、又不让
> DAC 削顶、又不让帧边界出现"咔"。

### 3.1 调制公式

设第 $k$ 路通道的基带信号 $z[k, t]$(本项目里实际是实数,但形式
上写复数以保留通用性),载波 $\cos(2\pi f_c t)$,调制度 $m$:

$$
x[k, t] = \tfrac{1}{2}\,\mathrm{Re}\!\Bigl\{\bigl(1 + m\,z[k, t]\bigr)\,
e^{\,j\,2\pi f_c\, t}\Bigr\}
\tag{3.1}
$$

新符号:

| 符号 | 含义 |
|---|---|
| $k$ | 通道编号 $1..8$ |
| $m$ | 调制度,$0 < m \le 1$,代码取 1 |
| $e^{j 2\pi f_c t}$ | 复指数形式的载波,等价 $\cos+j\sin$ |
| $x[k, t]$ | 第 $k$ 通道送进 DAC 的实通带信号 |

对应 `modulator.py:44`:`out = 0.5 * np.real((1.0 + m*z) * carrier)`。
取 $m=1$、$|z|\le 1$ 时

$$
|1 + z| \le 2 \;\Rightarrow\; |x| \le 1
$$

刚好用满 DAC 满量程([-1, 1])而不削顶。**这就是为什么前面要乘 0.5**:
若不除以 2,$|x|$ 会上到 1.0 + 仍是 1.0(因为载波本身在 $[-1, 1]$),
但 $(1+z)$ 已经在 $[0, 2]$,再乘 $\cos$ 会到 $[-2, 2]$,必须 $/2$ 才合规。

### 3.2 载波相位连续性

帧与帧之间不能让 $\cos(2\pi f_c t)$ 跳变,否则 DAC 输出会有周期性
**click**(咔咔声)。做法:维护**全局绝对样本计数** $n_\text{emit}$
(代码 `modulator.py:29` 的 `self._n_emitted`),

$$
\phi_n = 2\pi f_c \cdot \frac{n}{f_s},
\qquad n = n_\text{emit},\, n_\text{emit}+1,\, \dots,\, n_\text{emit}+T-1
$$

| 符号 | 含义 |
|---|---|
| $n$ | 第 $n$ 个 DAC 样本(从启动以来计数) |
| $T$ | 当前帧长度(样本数) |
| $\phi_n$ | 第 $n$ 个样本对应的载波相位 (rad) |

每帧产出后做 $n_\text{emit} \mathrel{+}= T$。
顺带一提:$f_c/f_s = 40\,000/96\,000 = 5/12$ 是有理数,因此每 12 个
样本(125 µs)相位就回到 $2\pi$ 整数倍,理论上可以用"短周期缓存"
但代码不依赖这一点 —— 绝对样本计数对任意 $f_c/f_s$ 都正确。

### 3.3 双耳共享载波

左右两路必须用**同一组样本时刻**生成载波,否则两耳间出现固定相位差,
退化为人为 ITD,会扰乱定位。`modulator.py:58-77` 的 `modulate_multi`
一次构造 `carrier`、给所有输入复用,保证这一点。

### 3.4 联合归一化的数学保证

8 通道 DAC 最终送出的信号是

$$
y[k, t] = \tfrac{1}{2}\bigl(y_L[k, t] + y_R[k, t]\bigr)
\tag{3.2}
$$

| 符号 | 含义 |
|---|---|
| $y_L[k, t], y_R[k, t]$ | 左 / 右耳波束器输出的第 $k$ 通道信号,各自已满足 $\|y_L\|, \|y_R\|\le 1$ |
| $y[k, t]$ | 真正送入 DAC 的合成信号 |

但 $|(y_L + y_R)/2|$ 不一定 $\le 1$ —— 当 L/R 在某通道某瞬时同相同号,
峰值会到 $1$ 甚至略超过。代码 `beamformer.py:128-132`:

```python
out = (out_L + out_R) / 2.0
peak = np.max(np.abs(out))
if peak > 1.0:
    out = out / peak
```

数学上这是**后验软限**(post-hoc soft clipping)。严格做法应该在权重
层做联合归一化:

$$
\alpha = \frac{1}{\max_\theta\bigl(\|\!|\mathbf{w}_L(\theta)|\!|_1
+ \|\!|\mathbf{w}_R(\theta)|\!|_1\bigr)}
\tag{3.3}
$$

| 符号 | 含义 |
|---|---|
| $\alpha$ | 全局缩放因子,使两耳权重和的最大 1-范数为 1 |
| $\mathbf{w}_L, \mathbf{w}_R$ | 左/右耳的 8 维复权向量(每个频点一组) |

但 LUT 权已经分别归一化,且每帧仅 1 次峰值检查,实测开销可忽略,
工程上接受当前实现。Monte Carlo 验证:
`scripts/make_figures.py:fig_joint_norm_mc` 在 200 组随机
$(\theta_L, \theta_R)$ + 随机音频下,$\max|y| = 1.000$,
说明软限触发率高,但能量损失 $<$ 0.5 dB(实测)。

---

## 4. 均匀线阵 (ULA) 阵列因子

> 这一节回答:把同一个信号通过不同延时(或不同相位)送到 8 个等距
> 摆放的阵元,远场为什么会出现"窄波束"?这就是 phased-array 的基础。

### 4.1 几何推导

$N$ 个全向阵元,沿 $x$ 轴等距 $d$ 排列,第 $n$ 个阵元位于 $x_n = nd$
($n=0, \dots, N-1$)。远场一个观测方向 $\theta$(相对 $+z$ 轴,
定义见 0.5),则相对于阵元 $0$,阵元 $n$ 上的几何**程差**为
$nd\sin\theta$,对应**相位延迟**

$$
\Delta\phi_n(\theta, f) = \frac{2\pi f}{c}\,nd\sin\theta
\tag{4.1}
$$

| 符号 | 含义 |
|---|---|
| $\theta$ | 远场观察方向(rad 或°,正负见 0.5) |
| $f$ | 当前考察的频率 (Hz) |
| $\Delta\phi_n$ | 第 $n$ 个阵元相对参考阵元的相位延迟 |

发射端在阵元 $n$ 上加一个**复权**(complex weight)
$w_n = a_n e^{j\psi_n}$,其中 $a_n$ 是幅度、$\psi_n$ 是初相位,
则远场叠加得到的**阵列因子**(Array Factor)

$$
\boxed{\ \mathrm{AF}(\theta, f) = \frac{1}{N}\sum_{n=0}^{N-1}
a_n\, e^{\,j\bigl(\psi_n + \frac{2\pi f}{c}\,nd\sin\theta\bigr)}\ }
\tag{4.2}
$$

新符号:

| 符号 | 含义 |
|---|---|
| $a_n$ | 第 $n$ 阵元的幅度权,$\ge 0$ |
| $\psi_n$ | 第 $n$ 阵元的相位权 (rad) |
| $w_n = a_n e^{j\psi_n}$ | 复合权 |
| $\mathrm{AF}(\theta, f)$ | 远场方向图(复数);取模即"哪些方向亮、哪些暗" |
| $1/N$ | 归一化因子,让 $\max\|AF\|\le 1$ |

`scripts/make_figures.py:_lut_array_factor` 即按 (4.2) 实现。

### 4.2 经典 phased-array 引导(无 null)

最简单的做法:让所有阵元同幅($a_n = 1$),相位补偿成
$\psi_n = -\frac{2\pi f}{c}\,n d\sin\theta_0$,
代入 (4.2):

$$
\mathrm{AF}(\theta, f) = \frac{1}{N}\cdot
\frac{\sin\bigl(N\pi\frac{d}{\lambda}(\sin\theta - \sin\theta_0)\bigr)}
{\sin\bigl(\pi\frac{d}{\lambda}(\sin\theta - \sin\theta_0)\bigr)}
\tag{4.3}
$$

这就是经典的 **Dirichlet 核**(类似 sinc 函数)。$\lambda = c/f$ 是
当前频率波长,$d = \lambda_c/2$。

| 符号 | 含义 |
|---|---|
| $\theta_0$ | 想要"对准"的目标方位(steering angle) |
| $\lambda$ | 当前频率的波长 $c/f$ |

当 $f = f_c$ 时 $d/\lambda = 1/2$,主瓣半幅宽
$$
\Delta\theta_{-3\,\mathrm{dB}}\approx 0.886\,\frac{\lambda_c}{Nd}\approx 12.7°
$$

(这里 $-3$ dB 指能量降到一半的半角宽度。)
**这就是 8 通道阵列在 40 kHz 上能达到的物理极限**;
任何 PSLL 设计目标必须接受这个主瓣宽度。详见
`reports/DECISIONS.md` 第 3 节关于 PSLL 取 −13 dB 而非 −30 dB 的论证。

### 4.3 引入零点(null-steering)

经典 phased-array 不能在指定的另一方向 $\theta_\text{null}$ 上**专门
压低**旁瓣。本项目要做"左耳听 L 内容、右耳听 R 内容",
就必须既能"对准本耳",又能"在对耳方向打个零点"。
这就需要换一种解权方式 —— 见第 5 节。

---

## 5. Null-Steering 离线优化

> 这一节回答:既然要"主瓣对准 A、零点压向 B",怎么解出每个阵元的
> 复权?答案是离线优化,把所有可能的 (A, B) 组合预先解好存进 LUT。

### 5.1 优化问题设定

对每个 $(\theta_\text{tgt}, \theta_\text{null})$ 配对,以及每个频点 $f_j$
($j = 0,\dots,n_f-1$,$f_j = f_c + (j - n_f/2)\Delta f$,
共 $n_f = 2B/\Delta f + 1 = 81$ 个),独立求解一组复权
$w_n^{(j)} = a_n^{(j)} e^{j\psi_n^{(j)}}$。
**总优化变量数 = $2 N n_f = 2\cdot 8\cdot 81 = 1296$ 个实数**
(8 通道 × 81 频点 × 幅度+相位两个自由度)。

| 符号 | 含义 |
|---|---|
| $\theta_\text{tgt}$ | 主瓣对准方向("目标耳") |
| $\theta_\text{null}$ | 要压制的方向("对耳") |
| $j$ | LUT 频点指标,$0\le j \le 80$ |
| $f_j$ | 第 $j$ 个 LUT 频点 (Hz) |
| $a_n^{(j)}, \psi_n^{(j)}$ | 第 $j$ 频点上、第 $n$ 阵元的幅度/相位权 |

变量界:$a_n^{(j)} \in [0.1, 1.0]$(下界 0.1 避免某通道彻底关闭、
导致驱动器空转),相位无约束。代码 `calibrate_nullsteering.py:219-221`。

### 5.2 损失函数推导

定义角度网格 $\Theta = \{-90°, -89°, \dots, 90°\}$(`AZ_GRID`,
共 181 个角度)。对每个 $f_j$ 与每个 $\theta_i \in \Theta$,
按 (4.2) 计算 $\mathrm{AF}_{ji} \in \mathbb{C}$,取模

$$
M_{ji} = |\mathrm{AF}(\theta_i, f_j)|
= \frac{1}{N}\sqrt{\Bigl(\sum_n a_n^{(j)}\cos\Phi_{nji}\Bigr)^2
+ \Bigl(\sum_n a_n^{(j)}\sin\Phi_{nji}\Bigr)^2}
\tag{5.1}
$$

其中

$$
\Phi_{nji} = \psi_n^{(j)} + \frac{2\pi}{\lambda_j}\, n d\sin\theta_i,
\qquad \lambda_j = c/f_j
$$

| 符号 | 含义 |
|---|---|
| $i$ | 角度网格指标,$0\le i\le 180$,对应 $\theta_i = -90° + i°$ |
| $M_{ji}$ | 在第 $j$ 频点、第 $i$ 方向上的方向图幅值 |
| $\Phi_{nji}$ | 阵元 $n$、频点 $j$、方向 $i$ 上的总相位 |
| $\lambda_j$ | 第 $j$ 频点的波长 |

代码对应 `calibrate_nullsteering.py:141-152`。

把 181 个角度划成三个互不相交的子集:

| 子集 | 定义 | 物理意义 | 宽度 |
|---|---|---|---|
| 主瓣区 $\mathcal{T}$ | $\{\theta_i:\, \|\theta_i - \theta_\text{tgt}\|\le W_M/2\}$ | 应该亮 | $W_M = 10°$ |
| 零点区 $\mathcal{N}$ | $\{\theta_i:\, \|\theta_i - \theta_\text{null}\|\le W_N/2\}$ | 应该暗 | $W_N = 10°$ |
| 旁瓣区 $\mathcal{S}$ | $\Theta\setminus(\mathcal{T}\cup\mathcal{N})$ | 不太管,但不许太亮 | 其余 |

(代码 `calibrate_nullsteering.py:84-101`。)

损失函数:

$$
\boxed{\
L = \underbrace{c_T\!\sum_{j,\,i\in\mathcal{T}} M_{ji}}_{\text{主瓣增益}\,(c_T<0,\text{最大化})}
+ \underbrace{c_S\!\sum_{j,\,i\in\mathcal{S}} M_{ji}}_{\text{旁瓣抑制}}
+ \underbrace{c_N\!\sum_{j,\,i\in\mathcal{N}} M_{ji}}_{\text{零点深度}}
+ \underbrace{c_V\cdot\mathrm{Var}_j\!\Bigl[\,\sum_{i\in\mathcal{T}}M_{ji}\Bigr]}_{\text{跨频一致性}}
\ }
\tag{5.2}
$$

系数(`calibrate_nullsteering.py:62-65`):

| 系数 | 值 | 物理含义 |
|---|---|---|
| $c_T$ | $-1$ | 主瓣加奖励(负号 = 最大化) |
| $c_S$ | $+0.5$ | 旁瓣轻惩罚(允许部分旁瓣以保住主瓣增益) |
| $c_N$ | $+10$ | 零点重惩罚(主目标) |
| $c_V$ | $+1000$ | 跨频一致(避免 $f_c\pm B$ 处方向图发散) |

第四项需要解释一下:**跨频一致性**。
若不加这一项,某些频点 $f_j$ 会"作弊"——把主瓣区能量推到旁瓣,
单频损失看起来更低,但全频段叠起来主瓣会"晃"(不同频率指向略偏),
听感上就是音色发飘。带 $c_V$ 的方差项强制 $\sum_{i\in\mathcal{T}}M_{ji}$
在不同 $j$ 上接近,保证可闻包络重建后没有频域畸变。

### 5.3 梯度推导(给优化器用)

L-BFGS-B 需要 $\nabla L$。链式法则把它拆成
$\nabla L = \sum_{ji} (\partial L/\partial M_{ji})\,\nabla M_{ji}$,
其中前者是"按区域分块的系数",后者是 $M_{ji}$ 对每个变量的偏导。

设辅助量
$$
r_{ji} = \sum_n a_n^{(j)}\cos\Phi_{nji},\qquad
s_{ji} = \sum_n a_n^{(j)}\sin\Phi_{nji}
$$
则 $N M_{ji} = \sqrt{r_{ji}^2 + s_{ji}^2}$。由 (5.1) 直接求导:

$$
\frac{\partial M_{ji}}{\partial a_n^{(j)}}
= \frac{1}{N}\cdot\frac{r_{ji}\cos\Phi_{nji} + s_{ji}\sin\Phi_{nji}}
{\sqrt{r_{ji}^2 + s_{ji}^2}}
\tag{5.3}
$$

$$
\frac{\partial M_{ji}}{\partial \psi_n^{(j)}}
= \frac{a_n^{(j)}}{N}\cdot\frac{-r_{ji}\sin\Phi_{nji} + s_{ji}\cos\Phi_{nji}}
{\sqrt{r_{ji}^2 + s_{ji}^2}}
\tag{5.4}
$$

对应 `calibrate_nullsteering.py:172-175`(代码里
`re_inv = r/M`、`im_inv = s/M`,把 (5.3)(5.4) 重写为
$(\cos\Phi\cdot r_\text{inv} + \sin\Phi\cdot s_\text{inv})/N$)。

方差项 (5.2 第四项) 还需要对 $M_{ji}$ 额外贡献:
令 $F_j = \sum_{i\in\mathcal{T}} M_{ji}$、$\bar F = \frac{1}{n_f}\sum_j F_j$,
则

$$
\frac{\partial}{\partial M_{ji}}\Bigl[c_V\cdot \mathrm{Var}_j[F_j]\Bigr]
= c_V\cdot\frac{2(F_j - \bar F)}{n_f}\cdot \mathbb{1}[\,i\in\mathcal{T}\,]
\tag{5.5}
$$

| 符号 | 含义 |
|---|---|
| $F_j$ | 第 $j$ 频点上主瓣区的总幅值 |
| $\bar F$ | 上式在 $j$ 上的均值 |
| $\mathbb{1}[\cdot]$ | 指示函数(0.3 节) |

`calibrate_nullsteering.py:183-190` 是 (5.5) 的实现。
最终 $\nabla L = \sum_{ji}\,\text{coef}_{ji}\cdot \nabla M_{ji}$,其中
$\text{coef}_{ji}$ 包含 $c_T, c_S, c_N$ 三块系数 + 方差项贡献。

### 5.4 求解器

L-BFGS-B (`scipy.optimize.minimize`):
- 变量界:$a_n^{(j)} \in [0.1, 1.0]$,$\psi_n^{(j)} \in \mathbb{R}$
- 最大迭代:2000 (`calibrate_nullsteering.py:225-232`)
- 初值:$a_n^{(j)} = 1$,$\psi_n^{(j)} = -\frac{2\pi}{\lambda_j} n d\sin\theta_\text{tgt}$
  —— 经典 phased-array 解(4.2 节),给优化器一个**对的方向、错的
  零点**的暖启动,通常 200-500 次迭代收敛。

**L-BFGS-B 是什么**?它是 BFGS(一种用历史梯度近似 Hessian 的拟牛顿
方法)的"限存(Limited-memory) + 带边界(Bounds)"版本,适合
变量上千、目标函数光滑、有简单上下界的问题 —— 正合本场景。

### 5.5 LUT 输出

最终 LUT(查找表)的格式:
- 键(key):`"{tgt}_{null}"`,角度量化到 3°,
  组合数 $41\times 41 = 1681$ (因 $\theta\in\{-60,\dots,60\}$ 共 41 个值)。
- 每条目存 $a$ 与 $\psi$ 两个矩阵,形状 $(n_f, N) = (81, 8)$。
- 总浮点数 $1681 \times 81 \times 8 \times 2 = 2.18\,\mathrm M$
  (JSON 文件 ~30 MB)。
- 角度量化最坏误差 1.5°,远小于阵列 ~12.7° 主瓣宽度,可忽略。

文件位置:`data/beam_weights/nullsteering_lut.json`。

---

## 6. 实时频域加权

> 这一节回答:有了 LUT,运行时怎么把权重作用到通带信号上?——
> 在 FFT 频域上,把每个 LUT 频点对应的 FFT bin 群直接乘上权重。

`beamformer.py:73-113` 的 `apply_passband` 流程:

1. 输入实通带信号 $x(t)$,长度 $T = 4800$ 样本(50 ms)。
2. $X[k] = \mathrm{FFT}(x)$,频率 $f_k = k\cdot f_s/T$
   ($k$ 为 FFT bin 指标)。
3. 对每个 LUT 频点 $f_j$,选 FFT bin 集合
   $$\mathcal{B}_j = \{k: f_j - \Delta f/2 \le f_k < f_j + \Delta f/2\}$$
   把权重 $w_n^{(j)} = a_n^{(j)} e^{j\psi_n^{(j)}}$ 复制到所有 $k\in\mathcal{B}_j$。
4. 通道 $n$ 输出 $Y_n[k] = W_n[k]\cdot X[k]$,然后 IFFT 回时域得
   该通道的实通带信号。

| 符号 | 含义 |
|---|---|
| $X[k]$ | 输入信号的 FFT,$k = 0..T-1$ |
| $f_k$ | 第 $k$ 个 FFT bin 的中心频率 |
| $\mathcal{B}_j$ | 落在 LUT 频点 $f_j$ 宽度内的 FFT bin 集合 |
| $W_n[k]$ | 第 $n$ 通道、第 $k$ bin 的复加权 |
| $Y_n[k]$ | 第 $n$ 通道、第 $k$ bin 的输出频谱 |

**FFT bin 数算一下**:$\Delta f = 100$ Hz,而 FFT bin 宽
$f_s/T = 96\,000/4800 = 20$ Hz,因此每个 LUT 频点平均覆盖
$100/20 = 5$ 个 FFT bin。

带宽外(即 $f < f_c - B$ 或 $f > f_c + B$)的 bin 默认 $W_n = 1$
(`beamformer.py:97`),理论上应置 0 以滤掉非通带能量,但实测
modulator 已经把能量集中在 $f_c\pm B$ 内,该项可忽略。

### 6.1 角度量化

实时来的 $\theta_L, \theta_R$ 是连续值,需先量化到 LUT 的 3° 网格
(`beamformer.py:52-57`):

$$
q(\theta) = \mathrm{round}(\theta / 3°)\cdot 3°,
\qquad q\in[-60°,\,60°]
\tag{6.1}
$$

最坏量化误差 $\le 1.5°$,小于阵列分辨率(12.7° 主瓣)。

### 6.2 双耳同时引导策略

每只耳同时:**主瓣对准自己耳的方位**、**零点压向对耳的方位**。

$$
y_L = \mathrm{apply}(x_L;\ \theta_\text{tgt}=\theta_L,\ \theta_\text{null}=\theta_R)
\tag{6.2}
$$
$$
y_R = \mathrm{apply}(x_R;\ \theta_\text{tgt}=\theta_R,\ \theta_\text{null}=\theta_L)
\tag{6.3}
$$

最终 8 通道 $y = (y_L + y_R)/2$(`beamformer.py:126-128`,即 (3.2))。
理想情况下,左耳接收 $y_L$(右耳被 null 压制),反之亦然,
实现"私人立体声"。

---

## 7. HRTF 卷积

> 这一节回答:为什么还要做 HRTF?——光有"声音从某个角度来"还不够,
> 人耳的耳廓、头颅、肩膀会对不同方向的声音做不同程度的染色;
> 复现这种染色才能让大脑相信"声源真的在那个方向"。

### 7.1 CIPIC 数据集介绍

`hrtf_renderer.py` 使用 CIPIC HRTF Database subject_003,
即对 KEMAR(标准假人头)实测的 HRIR(头相关冲激响应):

- HRIR 形状 $(25, 50, 200)$ = (方位, 仰角, 时间样本)
- 方位网格非均匀:$\{-80, -65, -55, -45, -40, \dots, 40, 45, 55, 65, 80\}$°
- 原始采样率 44 100 Hz → 重采样到 96 000 Hz(`hrtf_renderer.py:57-63`)
  比例 $96/44.1 = 320/147$(用 gcd = 最大公约数化简),
  用 polyphase 算法 `scipy.signal.resample_poly`(高效的有理数倍重采样)。

| 新符号 / 术语 | 含义 |
|---|---|
| HRIR | 时域形式的头相关冲激响应 |
| 仰角 (elevation) | 声源相对水平面的俯仰角(本项目固定 0°) |
| polyphase | 一种把"上采样 + 滤波 + 下采样"合并的高效结构 |

### 7.2 渲染公式

设左耳听到的基带为 $s_L(t)$、右耳 $s_R(t)$,原始单声道为 $x(t)$,
左耳 HRIR 为 $h_L^{(\theta_L)}$,右耳 HRIR 为 $h_R^{(\theta_R)}$,
则

$$
s_L(t) = (h_L^{(\theta_L)} * x)(t),
\qquad s_R(t) = (h_R^{(\theta_R)} * x)(t)
\tag{7.1}
$$

($*$ 是时域卷积,见 0.3 节。)

`hrtf_renderer.py:77-94` 实现。注意:**左耳只用左耳 HRIR、
右耳只用右耳 HRIR**;这与"标准 HRTF 渲染"不同(标准做法是:对
每个声源都要 L+R 两个 HRIR、然后两耳各做一次叠加)。本项目的设定是
"每耳听到的虚拟源就在该耳本身的方位",即头追踪给出的两个角度。

### 7.3 Woodworth ITD 退化

CIPIC 文件缺失时(`HRTFRenderer.load()` 抛 `FileNotFoundError`),
回退到纯延时(Woodworth & Schlosberg 公式):

$$
\mathrm{ITD}(\theta) = \frac{r}{c}\bigl(\theta + \sin\theta\bigr),
\quad r = \tfrac{1}{2}\,W_i
\tag{7.2}
$$

| 符号 | 含义 |
|---|---|
| $r$ | 头半径 (m),取 $W_i/2 = 0.085$ m |
| $\theta$ | 方位角 (rad) |

`hrtf_renderer.py:113-117` 实现 (7.2)。退化后只有 ITD、没有 ILD/HRIR
染色,定位粗糙但仍可用。

---

## 8. 头部追踪几何

> 这一节回答:给定一个 / 两只耳的空间位置,怎么换算成阵列要的
> $(\theta_L, \theta_R, d_L, d_R)$ 四元组?

### 8.1 虚拟模式

`head_tracker.py: VirtualTracker.get_ear_pose`。
给定头中心方位 $\alpha$ 和距离 $d$,头中心位置

$$
\mathbf{c} = (d\sin\alpha,\ 0,\ d\cos\alpha)
$$

头朝向阵列(yaw $= \alpha$,即头的"看向"方向),双耳轴垂直于朝向。
左耳偏移 $-(\cos\alpha, 0, -\sin\alpha)\cdot W_i/2$,右耳对称。

$$
\mathbf{L} = \mathbf{c} + \frac{W_i}{2}\,(-\cos\alpha,\,0,\,\sin\alpha)
$$
$$
\mathbf{R} = \mathbf{c} + \frac{W_i}{2}\,(\cos\alpha,\,0,\,-\sin\alpha)
\tag{8.1}
$$

| 符号 | 含义 |
|---|---|
| $\alpha$ | 头中心相对阵列的方位角 |
| $d$ | 头中心到阵列的距离 |
| $W_i$ | 双耳间距,见 0.4 节 |
| **yaw** | 偏航角,绕垂直轴的旋转 |

到达阵列的方位与距离:

$$
\theta_L = \mathrm{atan2}(L_x,\, L_z),\quad
d_L = \sqrt{L_x^2 + L_z^2}
$$

(同理 $\theta_R, d_R$。)代码 `head_tracker.py:59-78`。

### 8.2 单耳接收角宽度

每只耳朵的物理"收声口"(耳廓 – 耳道入口)横向跨度 $W_\text{ear} = 60$ mm,
其在阵列处看起来的角宽度为

$$
\delta(\theta, d) = 2\arctan\!\Bigl(\frac{W_\text{ear}/2}{d}\Bigr)
\tag{8.2}
$$

| 符号 | 含义 |
|---|---|
| $\delta$ | 单耳"收声口"在阵列看来的张角 |

`head_tracker.py:76-77`。当 $\delta$ 接近或超过阵列主瓣宽度(12.7°)时,
零点策略失效(信号会"溢"进对耳),触发 beam-width 警告。

### 8.3 实时模式(D435I + MediaPipe)

`head_tracker.py: LiveTracker`。
MediaPipe Face Mesh 输出 478 个面部 landmark(关键点),
索引 234 与 454 分别对应左、右 tragus(耳屏)。
D435I 深度相机给出像素 $(u, v)$ 处的深度 $z$;
利用相机内参把像素坐标投影回相机坐标系:

$$
x_\text{cam} = \frac{u - c_x}{f_x}\cdot z,\qquad
y_\text{cam} = \frac{v - c_y}{f_y}\cdot z
\tag{8.3}
$$

| 符号 | 含义 |
|---|---|
| $(u, v)$ | landmark 的像素坐标 |
| $(c_x, c_y)$ | 相机主点坐标 (像素) |
| $(f_x, f_y)$ | 相机焦距 (像素单位) |

(D435I 出厂内参 $f_x, f_y, c_x, c_y$ 从 `pyrealsense2` 取,
`head_tracker.py:164-168`。)

### 8.4 外参变换

D435I 安装在阵列正上 / 下方,垂直偏移 $h$(`CAMERA_HEIGHT_M`)。
相机坐标系 $+y$ 朝下,阵列坐标系 $+y$ 朝上,所以外参矩阵
$T_{c\to a} \in \mathbb{R}^{4\times 4}$(齐次坐标):

$$
T_{c\to a} =
\begin{pmatrix}
1 & 0 & 0 & 0\\
0 & -1 & 0 & h\\
0 & 0 & 1 & 0\\
0 & 0 & 0 & 1
\end{pmatrix}
\tag{8.4}
$$

矩阵作用方式:对相机坐标系下的点 $\mathbf{p}_c = (x, y, z, 1)^\top$,
阵列坐标系下的点是 $\mathbf{p}_a = T_{c\to a}\,\mathbf{p}_c$。

`head_tracker.py:110-127` 的 `_build_extrinsic`。
存在 `data/extrinsic.json` 时使用文件中的标定矩阵
(可由 `directional_speaker/calibration.py` 交互生成),
否则用 (8.4) 默认值。

阵列坐标下 $\theta = \mathrm{atan2}(x_a, z_a)$、$d = \sqrt{x_a^2 + z_a^2}$
(`head_tracker.py:228-232`),与 8.1 同公式。

### 8.5 EMA 平滑

实时 landmark 抖动严重,要先一阶低通(EMA = 指数移动平均):

$$
\hat\theta_t = \alpha\,\theta_t + (1 - \alpha)\,\hat\theta_{t-1},
\qquad \alpha = 0.5
\tag{8.5}
$$

| 符号 | 含义 |
|---|---|
| $\theta_t$ | 第 $t$ 帧原始测量 |
| $\hat\theta_t$ | 平滑后输出 |
| $\alpha$ | EMA 系数,越大越接近瞬时值、越小越平滑 |

`head_tracker.py:175-190`。$\alpha=0.5$ 的半衰期是 1 帧(25 ms),
即 1 帧吸收 50% 的旧信息;延迟可接受、抖动显著降低。

---

## 9. 距离幅度补偿

> 这一节回答:头一远一近时,远耳为什么需要更大增益、近耳为什么
> 不动?以及为什么不在数字端做时间对齐。

`audio_adjuster.py`。线性声学中,声压随距离 $\propto 1/d$;
但**参数阵的可闻波**按 (2.3) 是 $\propto P_0^2/z$,
所以可以把幅度补偿指数取 1(代码 `amp_exponent = 1.0`):

$$
g_\text{ear} = \min\!\Bigl(\Bigl(\frac{d_\text{ref}}{d_\text{ear}}\Bigr)^{1},\ g_\text{max}\Bigr),
\quad d_\text{ref} = \min(d_L,\, d_R)
\tag{9.1}
$$

| 符号 | 含义 |
|---|---|
| $g_\text{ear}$ | 该耳路的幅度补偿增益 |
| $d_\text{ear}$ | 该耳到阵列的距离 |
| $d_\text{ref}$ | 参考距离 = 近耳的距离 |
| $g_\text{max}$ | 增益上限 (代码取 4) |

$g_\text{max} = 4$ 防止远耳被疯狂放大触发削顶。

取 $d_\text{ref} = \min$ 而非 $\max$ 的原因:近耳 $g = 1$ 不放大,
远耳 $g > 1$ 加增益 —— 这保证**近耳通道永远不会因增益而剪切**,
削顶风险只集中在远耳(它有上限 $g_\text{max}$)。

**为什么不做时间对齐**?物理路径自带 $\Delta t = (d_L - d_R)/c$
的 ITD,数字端再做预延时会**双倍计入** ITD,反而破坏定位。

---

## 10. 窗口、跳跃与延迟

> 这一节回答:为什么帧长 50 ms、跳 25 ms?整个系统的端到端延迟多大?

窗口 $T_w = 50$ ms / 跳跃 $T_h = 25$ ms。
50% 重叠下**本项目并未做 OLA**(overlap-and-add 重叠相加,常见 STFT
重建技术),但 25 ms 的跳跃保证两件事:

1. 头部转动响应延迟 $\le 25$ ms(低于人感知阈值);
2. ASIO 缓冲 3 帧 = 75 ms,够吸收抖动而不引入明显唇同步偏差。

端到端延迟预算:

| 阶段 | 延迟 |
|---|---|
| 头追踪 (D435I 30 fps + EMA) | ~33 ms |
| 帧累积 (等够 25 ms 输入) | ~25 ms |
| 处理 (DSP + FFT) | ~5 ms |
| ASIO buffer (3 帧) | ~75 ms |
| **总计** | **~138 ms** |

低于 200 ms 通常不影响视听沉浸感。

---

## 11. 全链路数学一致性约束

下表是"违反则系统出错"的硬约束:

| 约束 | 表达式 | 强制位置 |
|---|---|---|
| 调制度 | $\|z\|\le 1$ | `main.py:129-130` `np.clip` |
| 单耳通带峰 | $\|y_{L/R}\|\le 1$ | 由 (3.1) 数学保证 |
| 8 通道联合峰 | $\|y\|\le 1$ | `beamformer.py:130-132` 后验软限 |
| LUT 角度网格 | $\theta\in\{-60, -57, \dots, 60\}$° | `beamformer.py:_quantize` |
| LUT 频率覆盖 | $f\in[f_c - B,\, f_c + B]$ | `calibrate_nullsteering.py:_freqs` |
| 阵列物理极限 | 主瓣 $\ge 12.7°$ @ 40 kHz | 4.2 节;设计取舍见 `reports/DECISIONS.md` |
| HRIR 重采样比 | 44.1 kHz → 96 kHz,比 $320/147$ | `hrtf_renderer.py:59-63` |
| 载波相位 | 跨帧绝对样本计数 | `modulator.py:29 _n_emitted` |

任何一处违反都会在仿真或听感上立刻显现:
- 调制度溢出 → THD 突增;
- 联合峰溢出 → DAC 削顶,出现咔咔声;
- 载波相位不连续 → 帧边界 click。

---

## 12. 参考文献

1. **Berktay, H. O.** (1965). *Possible Exploitation of Non-Linear Acoustics
   in Underwater Transmitting Applications.* J. Sound Vib., 2(4), 435-461.
   (本文 (2.3) 的原始推导。)
2. **Yoneyama, M. et al.** (1983). *The Audio Spotlight: An Application of
   Nonlinear Interaction of Sound Waves to a New Type of Loudspeaker Design.*
   J. Acoust. Soc. Am., 73(5), 1532-1536.
3. **Pompei, F. J.** (1999). *The Use of Airborne Ultrasonics for Generating
   Audible Sound Beams.* J. Audio Eng. Soc., 47(9), 726-731.
4. **Van Trees, H. L.** (2002). *Optimum Array Processing.* Wiley.
   (Eigenfilter / null-steering 的标准参考。)
5. **CIPIC HRTF Database v1.2** (UC Davis CIPIC Interface Lab).
   <https://interface.cipic.ucdavis.edu/>
6. **Algazi, V. R. et al.** (2001). *The CIPIC HRTF Database.* WASPAA.
7. **Woodworth, R. S. & Schlosberg, H.** (1962). *Experimental Psychology.*
   ((7.2) ITD 公式来源。)
8. **Westervelt, P. J.** (1963). *Parametric Acoustic Array.*
   J. Acoust. Soc. Am., 35(4), 535-537.
   ((2.1) 非线性波动方程来源。)

---

*文档版本 v1.1(新手向重写)· 与代码同步 · 修订请同时更新对应 `file:line` 引用。*
