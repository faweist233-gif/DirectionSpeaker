# DirectionalSpeaker — 原理与数学推导

> 配套文档:`MANUAL.md`(操作)、`reports/DECISIONS.md`(设计取舍)。
> 本文给出**所有数学推导**与代码对应位置(`file:line`)。所有物理常量见
> `directional_speaker/config.py`,本文中出现的符号一律以那里的值为准。

---

## 0. 符号约定

| 符号 | 含义 | 代码常量 | 数值 |
|---|---|---|---|
| $c$ | 空气声速 | `C_SOUND` | 343 m/s |
| $f_c$ | 超声载波频率 | `FC_HZ` | 40 000 Hz |
| $f_s$ | DAC 采样率 | `FS_HZ` | 96 000 Hz |
| $\lambda_c$ | 载波波长 $c/f_c$ | `LAMBDA_M` | 8.575 mm |
| $N$ | 阵列通道数 | `N_CHANNELS` | 8 |
| $d$ | 阵元间距 $\lambda_c/2$ | `ELEMENT_SPACING_M` | 4.287 mm |
| $T_w$ | 窗口长度 | `WINDOW_MS` | 50 ms (4800 样本) |
| $T_h$ | 跳跃长度 | `HOP_MS` | 25 ms (2400 样本) |
| $B$ | 单边带带宽 | `PASSBAND_BW_HZ` | 4000 Hz |
| $\Delta f$ | LUT 频率步长 | `FREQ_STEP_HZ` | 100 Hz |
| $\Delta\theta$ | LUT 角度步长 | `THETA_STEP_DEG` | 3° |

阵列坐标系:$+x$ 右,$+y$ 上,$+z$ 朝向用户。方位角
$\theta = \mathrm{atan2}(x, z)$,主轴 $\theta=0$ 朝正前方。

---

## 1. 系统总览

```
mono(t) ──► HRTF(θ_L,θ_R) ──► (s_L, s_R)
                                  │
                          AudioAdjuster (d_L,d_R 增益)
                                  │
                          (s_L', s_R')
                                  │
                    DSB-AM 调制(共享载波相位)
                                  │
                          (x_L(t), x_R(t))   ← 实通带信号
                                  │
              Null-Steering 频域加权(每耳一组 8 通道权)
                                  │
                          y[k,t], k=1..8   ← 8 通道通带
                                  │
                          ASIO ── 8 路超声换能器
                                  │
                          空气中非线性自解调(Berktay)
                                  │
                          可闻波束 → 用户双耳
```

每 25 ms 跳跃执行一次完整流水线;见 `directional_speaker/main.py:114-160`。

---

## 2. 参数阵原理 (Berktay 远场解)

### 2.1 物理出发点

空气在大振幅声压下并非线性介质。Westervelt 方程把非线性源项写作

$$
\Box^2 p - \frac{1}{c^2}\frac{\partial^2 p}{\partial t^2}
= -\frac{\beta}{\rho_0 c^4}\frac{\partial^2 p^2}{\partial t^2}
$$

其中 $\beta\approx 1.2$(空气非线性系数),$\rho_0$ 密度。
右端 $\partial^2 p^2/\partial t^2$ 是**二阶非线性源**,在窄带超声场中
会产生差频分量。

### 2.2 Berktay 远场近似

当一束高指向性超声 $p(z,t) = P_0 E(t)\cos(2\pi f_c t)$
(其中 $E(t)$ 是慢变包络,$|E|\le 1$)沿 $+z$ 传播,
Berktay 推得远场(轴上)可闻分量

$$
\boxed{\ p_\text{aud}(z, t) \;\propto\;
\frac{\beta P_0^2 a^2}{16\rho_0 c^4 \alpha z}
\cdot \frac{\partial^2}{\partial t^2}\bigl[E^2(t - z/c)\bigr]\ }
\tag{2.1}
$$

$a$ 为换能器有效半径,$\alpha$ 为高频吸收系数。

**关键结论**:
1. 可闻波形 $\propto \partial_t^2 [E^2]$,即**包络平方的二阶导数**。
2. 用 DSB-AM 形式 $E(t) = 1 + m\,s(t)$($|s|\le 1$,$m\le 1$)代入,
   $E^2 = 1 + 2m s + m^2 s^2$。其中 $1$ 是直流被 $\partial_t^2$ 滤掉,
   $m^2 s^2$ 是失真项。要让失真小,必须 $m\ll 1$,但这会损失效率;
   工程上取 $m=1$ 接受 ~−10 dB THD,再用预失真补偿(本项目不做)。

### 2.3 与本项目的对应

代码层面我们**只负责生成 $p(t)$**(即 8 通道通带电压);非线性自解调
在空气里自动发生。所有可闻方向性都来自:
**8 通道超声场在阵列正前方按 $\theta$ 方向聚焦**,
而非传统电声扬声器的低频指向性(8 mm 间距下做不到)。

---

## 3. DSB-AM 调制与归一化

### 3.1 调制公式

设基带 $z[k, t]$(本项目中其实是实数,但形式上写为复数以保留通用性),
载波 $\cos(2\pi f_c t)$,调制度 $m$:

$$
x[k, t] = \tfrac{1}{2}\,\mathrm{Re}\!\Bigl\{\bigl(1 + m\,z[k, t]\bigr)\,
e^{\,j 2\pi f_c t}\Bigr\}
\tag{3.1}
$$

对应 `modulator.py:44`:`out = 0.5 * np.real((1.0 + m*z) * carrier)`。
取 $m=1$、$|z|\le 1$ 时

$$
|1+z|\le 2 \implies |x|\le 1
$$

恰好用满 DAC 满量程而不削顶。

### 3.2 载波相位连续性

帧间不能让 $\cos(2\pi f_c t)$ 跳变,否则 DAC 输出有周期性 click。
做法:维护全局**绝对样本计数** $n_\text{emit}$
(`modulator.py:29` 的 `self._n_emitted`),

$$
\phi_n = 2\pi f_c \cdot \frac{n}{f_s},
\qquad n = n_\text{emit}, n_\text{emit}+1, \dots
$$

每帧产出后 $n_\text{emit} \mathrel{+}= T$。
当 $f_c/f_s = 40\,000/96\,000 = 5/12$ 是有理数,
12 个样本后相位回到 $2\pi$ 倍数,所以理论上每 125 µs 就能"对齐",
但代码不依赖这点 —— 绝对计数法对任意 $f_c/f_s$ 都正确。

### 3.3 双耳共享载波

L/R 两路必须用**同一组样本时刻**生成载波,否则两耳间出现固定相位差,
退化为人为 ITD。`modulator.py:58-77` 的 `modulate_multi` 一次 build
`carrier`、给所有输入复用,正好保证这点。

### 3.4 联合归一化的数学保证

最终送 DAC 的 8 通道信号是

$$
y[k, t] = \tfrac{1}{2}\bigl(y_L[k, t] + y_R[k, t]\bigr)
$$

其中 $y_L, y_R$ 各自已满足 $|y_L|,|y_R|\le 1$(单耳条件下)。
但 $|(y_L+y_R)/2|$ 不一定 $\le 1$ —— 当 L/R 在某通道某瞬时同号
同相,峰值可达 $1$。代码 `beamformer.py:128-132`:

```python
out = (out_L + out_R) / 2.0
peak = np.max(np.abs(out))
if peak > 1.0:
    out = out / peak
```

数学上是后验软限。**严格做法**应在权重层做联合归一化:

$$
\alpha = \frac{1}{\max_\theta\bigl(\,|\!|\mathbf{w}_L(\theta)|\!|_1
+ |\!|\mathbf{w}_R(\theta)|\!|_1\,\bigr)}
$$

但 LUT 权已经分别归一化,且每帧仅做 1 次峰值检查,实测开销可忽略,
工程上接受当前实现。Monte Carlo 验证:
`scripts/make_figures.py:fig_joint_norm_mc` 在 200 组随机
$(\theta_L,\theta_R)$ + 随机音频下,$\max|y|=1.000$,
说明软限触发率高但能量损失 $<$ 0.5 dB(实测)。

---

## 4. 均匀线阵 (ULA) 阵列因子

### 4.1 推导

$N$ 个全向阵元,沿 $x$ 轴等距 $d$ 排列,第 $n$ 个阵元位于 $x_n = nd$
($n=0,\dots,N-1$)。远场入射方向 $\theta$(相对 $+z$ 轴),
入射波在阵元 $n$ 处相对参考(阵元 0)的几何相位延迟

$$
\Delta\phi_n(\theta, f) = \frac{2\pi f}{c}\,nd\sin\theta
\tag{4.1}
$$

发射端给阵元 $n$ 施加复加权 $w_n = a_n e^{j\psi_n}$,
则远场方向图(阵列因子)

$$
\boxed{\ \mathrm{AF}(\theta, f) = \frac{1}{N}\sum_{n=0}^{N-1}
a_n\, e^{\,j(\psi_n + \frac{2\pi f}{c}nd\sin\theta)}\ }
\tag{4.2}
$$

`scripts/make_figures.py:_lut_array_factor` 即按 (4.2) 实现。

### 4.2 经典 phased-array 引导(无 null)

若取 $a_n = 1$、$\psi_n = -\frac{2\pi f}{c}nd\sin\theta_0$,
代入 (4.2):

$$
\mathrm{AF}(\theta, f) = \frac{1}{N}\frac{\sin(N\pi\tfrac{d}{\lambda}(\sin\theta-\sin\theta_0))}
{\sin(\pi\tfrac{d}{\lambda}(\sin\theta-\sin\theta_0))}
$$

(Dirichlet 核)。$\lambda = c/f$,$d = \lambda_c/2$。
当 $f = f_c$ 时 $d/\lambda = 1/2$,主瓣半幅宽
$\Delta\theta_{-3} \approx 0.886\,\lambda_c/(Nd) \approx 12.7°$。
**这就是 8 通道阵列在 40 kHz 上能达到的物理极限**;
任何 PSLL 设计目标必须接受这个主瓣宽度。
详见 `reports/DECISIONS.md` 第 3 节关于 PSLL 取 −13 dB 而非 −30 dB 的论证。

### 4.3 引入零点(null-steering)

经典 phased-array 不能在指定 $\theta_\text{null}$ 处压制旁瓣。
本项目转而求解**带 null 约束**的最优权:见下一节。

---

## 5. Null-Steering 离线优化

### 5.1 设定

对每个 $(\theta_\text{tgt}, \theta_\text{null})$ 配对,以及每个频点 $f_j$
($j=0,\dots,n_f-1$,$f_j = f_c + (j - n_f/2)\Delta f$),
独立求解复权 $w_n^{(j)} = a_n^{(j)} e^{j\psi_n^{(j)}}$。
变量总数 $2 N n_f = 2\cdot 8\cdot 81 = 1296$。

幅度 $a_n^{(j)}\in[0.1, 1.0]$,相位无约束,
`scripts/calibrate_nullsteering.py:219-221`。

### 5.2 损失函数推导

定义角度网格 $\Theta = \{-90°, -89°, \dots, 90°\}$(`AZ_GRID`)。
对每个 $f_j$ 与每个 $\theta_i\in\Theta$,
按 (4.2) 计算 $\mathrm{AF}_{ji} \in \mathbb{C}$,取模

$$
M_{ji} = |\mathrm{AF}(\theta_i, f_j)|
= \frac{1}{N}\sqrt{\Bigl(\sum_n a_n^{(j)}\cos\Phi_{nji}\Bigr)^2
+ \Bigl(\sum_n a_n^{(j)}\sin\Phi_{nji}\Bigr)^2}
\tag{5.1}
$$

其中 $\Phi_{nji} = \psi_n^{(j)} + (2\pi/\lambda_j) nd \sin\theta_i$,
$\lambda_j = c/f_j$。代码对应 `calibrate_nullsteering.py:141-152`。

将角度网格划成三个掩码:
- 主瓣区 $\mathcal{T} = \{\theta_i:\,|\theta_i - \theta_\text{tgt}|\le W_M/2\}$,$W_M=10°$
- 零点区 $\mathcal{N} = \{\theta_i:\,|\theta_i - \theta_\text{null}|\le W_N/2\}$,$W_N=10°$
- 旁瓣区 $\mathcal{S} = \Theta\setminus(\mathcal{T}\cup\mathcal{N})$

(`calibrate_nullsteering.py:84-101`)。
损失函数:

$$
\boxed{\
L = \underbrace{c_T\!\sum_{j,i\in\mathcal{T}} M_{ji}}_{\text{主瓣增益(负值,要最大化)}}
+ \underbrace{c_S\!\sum_{j,i\in\mathcal{S}} M_{ji}}_{\text{旁瓣抑制}}
+ \underbrace{c_N\!\sum_{j,i\in\mathcal{N}} M_{ji}}_{\text{零点深度}}
+ \underbrace{c_V\cdot\mathrm{Var}_j\!\Bigl[\sum_{i\in\mathcal{T}}M_{ji}\Bigr]}_{\text{跨频一致性}}
\ }
\tag{5.2}
$$

系数(`calibrate_nullsteering.py:62-65`):

| 系数 | 值 | 物理含义 |
|---|---|---|
| $c_T$ | $-1$ | 主瓣加奖励(负号 = 最大化) |
| $c_S$ | $+0.5$ | 旁瓣轻惩罚(允许部分旁瓣保住主瓣增益) |
| $c_N$ | $+10$ | 零点重惩罚(主目标) |
| $c_V$ | $+1000$ | 跨频一致(避免 $f_c\pm B$ 处方向图发散) |

第四项的物理动机:若不加,某些 $f_j$ 会"作弊"——
把能量推到旁瓣以最小化主瓣区跨频方差以外的损失;
而带 $c_V$ 的方差项强制 $\sum_{i\in\mathcal{T}}M_{ji}$ 在不同 $j$ 上接近,
保证可闻包络重建无频域畸变。

### 5.3 梯度推导

设 $r_{ji} = \sum_n a_n^{(j)}\cos\Phi_{nji}$,
$s_{ji} = \sum_n a_n^{(j)}\sin\Phi_{nji}$,则 $NM_{ji} = \sqrt{r^2+s^2}$。

$$
\frac{\partial M_{ji}}{\partial a_n^{(j)}}
= \frac{1}{N}\frac{r_{ji}\cos\Phi_{nji} + s_{ji}\sin\Phi_{nji}}
{\sqrt{r_{ji}^2+s_{ji}^2}}
\tag{5.3}
$$

$$
\frac{\partial M_{ji}}{\partial \psi_n^{(j)}}
= \frac{a_n^{(j)}}{N}\frac{-r_{ji}\sin\Phi_{nji} + s_{ji}\cos\Phi_{nji}}
{\sqrt{r_{ji}^2+s_{ji}^2}}
\tag{5.4}
$$

对应 `calibrate_nullsteering.py:172-175`(注意代码里
`re_inv = r/M`、`im_inv = s/M`,把 (5.3)(5.4) 重写为
$(\,\cos\Phi\,r_\text{inv} + \sin\Phi\,s_\text{inv})/N$)。

把每个角度区域的系数 $\partial L/\partial M_{ji}$ 收成矩阵
`coef[:, :]`,加上方差项的额外梯度

$$
\frac{\partial}{\partial M_{ji}}\Bigl[c_V\cdot\mathrm{Var}_j[F_j]\Bigr]
= c_V\cdot\frac{2(F_j - \bar F)}{|\mathcal{T}|}\cdot\mathbb{1}[i\in\mathcal{T}]
\tag{5.5}
$$

其中 $F_j = \sum_{i\in\mathcal{T}}M_{ji}$。
`calibrate_nullsteering.py:183-190` 是 (5.5) 的实现。
最终 $\nabla L = \sum_{ji}\,\text{coef}_{ji}\cdot\nabla M_{ji}$。

### 5.4 求解器

L-BFGS-B(`scipy.optimize.minimize`),
界 $a_n\in[0.1,1.0]$,$\psi_n\in\mathbb{R}$,最大迭代 2000,
`calibrate_nullsteering.py:225-232`。初值:
$a_n=1$,$\psi_n=-2\pi n d\sin\theta_\text{tgt}/\lambda_j$
(经典 phased-array 解,见 4.2)。这给优化器一个**对的方向、错的零点**
的暖启动,通常 200-500 次迭代收敛。

### 5.5 输出

LUT 键 `"{tgt}_{null}"`,角度量化到 3°,
组合数 $41\times 41 = 1681$。
每条目存 $a, \psi$ 矩阵,形状 $(n_f, N) = (81, 8)$,
共 $1681\times 81\times 8\times 2 = 2.18\text{M}$ 浮点(JSON ~30 MB)。
量化误差最坏 1.5°,对 8 通道阵列 ~12.7° 主瓣宽度可忽略。

---

## 6. 实时频域加权

`beamformer.py:73-113` 的 `apply_passband`:

1. 输入实通带信号 $x(t)$,长度 $T = 4800$ 样本(50 ms)。
2. $X[k] = \mathrm{FFT}(x)$,频率 $f_k = k\cdot f_s/T$。
3. 对每个 LUT 频点 $f_j$,
   选 FFT bin 集合 $\mathcal{B}_j = \{k:\,f_j-\Delta f/2 \le f_k < f_j+\Delta f/2\}$,
   把权重 $w_n^{(j)} = a_n^{(j)}e^{j\psi_n^{(j)}}$ 复制到所有 $k\in\mathcal{B}_j$。
4. 通道 $n$ 输出 $Y_n[k] = W_n[k]\cdot X[k]$,然后 IFFT 回时域。

$\Delta f = 100$ Hz,FFT bin 宽 $f_s/T = 96\,000/4800 = 20$ Hz,
所以每个 LUT 频点平均覆盖 5 个 FFT bin。
带宽外(即 $f<f_c-B$ 或 $f>f_c+B$)的 bin 默认 $W_n=1$(`beamformer.py:97`),
理论上应置 0 以滤掉非通带能量,但实测 modulator 已经把能量集中在
$f_c\pm B$ 内,影响可忽略。

### 6.1 角度量化

实时来的 $\theta_L, \theta_R$ 是连续值,代码 `beamformer.py:52-57`:

$$
q(\theta) = \mathrm{round}(\theta/3°)\cdot 3°,
\qquad q\in[-60°, 60°]
$$

最坏误差 1.5°,小于阵列分辨率。

### 6.2 双耳同时引导

策略:每耳同时引导**主瓣到自己耳的方位**、**零点到另一耳的方位**:

$$
y_L = \mathrm{apply}(x_L;\ \theta_\text{tgt}=\theta_L,\ \theta_\text{null}=\theta_R)
$$
$$
y_R = \mathrm{apply}(x_R;\ \theta_\text{tgt}=\theta_R,\ \theta_\text{null}=\theta_L)
$$

最终 8 通道 $y = (y_L + y_R)/2$(`beamformer.py:126-128`)。
理想情况下,左耳接收 $y_L$(右耳被 null 压制),反之亦然,
实现"私人立体声"。

---

## 7. HRTF 卷积

### 7.1 CIPIC 数据

`hrtf_renderer.py`。CIPIC 数据库 subject_003 (KEMAR 假人头):

- HRIR 形状 $(25, 50, 200)$ = (方位, 仰角, 时间样本)
- 方位网格非均匀:$\{-80, -65, -55, -45, -40, ..., 40, 45, 55, 65, 80\}$°
- 原始 $f_s = 44\,100$ Hz $\to$ resample 到 96 000 Hz(`hrtf_renderer.py:57-63`)
  比例 $96/44.1 = 320/147$(经 gcd 化简),用 polyphase `resample_poly`。

### 7.2 渲染

$$
s_L(t) = (h_L^{(\theta_L)} * x)(t),
\qquad s_R(t) = (h_R^{(\theta_R)} * x)(t)
\tag{7.1}
$$

`hrtf_renderer.py:77-94`。注意:**左耳只用左耳 HRIR、右耳只用右耳 HRIR**;
这与传统 HRTF 渲染不同(传统对每个声源都要 L+R 两个 HRIR)。
本项目的设定是"每耳听到的虚拟源就在这只耳的方位",即头跟踪决定的两个角度。

### 7.3 Woodworth ITD 退化

CIPIC 文件缺失时(`HRTFRenderer.load()` 抛 `FileNotFoundError`),
回退到纯延时:

$$
\mathrm{ITD}(\theta) = \frac{r}{c}\bigl(\theta + \sin\theta\bigr),
\quad r = \tfrac{1}{2}\,W_\text{interaural}
\tag{7.2}
$$

$r = 0.085$ m。`hrtf_renderer.py:113-117` 实现 (7.2)。
退化后只有 ITD、没有 ILD/HRIR 染色,定位粗糙但可用。

---

## 8. 头部追踪几何

### 8.1 虚拟模式

`head_tracker.py:VirtualTracker.get_ear_pose`。给定头中心方位 $\alpha$、距离 $d$:

$$
\mathbf{c} = (d\sin\alpha,\ 0,\ d\cos\alpha)
$$

头朝向阵列(yaw $=\alpha$),双耳轴垂直于朝向。
左耳偏移 $-(\cos\alpha,\,0,\,-\sin\alpha)\cdot W_i/2$,
右耳对称。$W_i = $ `INTERAURAL_M` $= 0.17$ m。

$$
\mathbf{L} = \mathbf{c} + \frac{W_i}{2}(-\cos\alpha,\,0,\,\sin\alpha)
$$
$$
\mathbf{R} = \mathbf{c} + \frac{W_i}{2}(\cos\alpha,\,0,\,-\sin\alpha)
$$

到达阵列的方位与距离:

$$
\theta_L = \mathrm{atan2}(L_x, L_z),\quad d_L = \sqrt{L_x^2+L_z^2}
$$
(同理 $\theta_R, d_R$)。代码 `head_tracker.py:59-78`。

### 8.2 接收角宽度

每只耳朵的物理"收声口"(耳廓-耳道入口)横向跨度 $W_\text{ear} = 60$ mm,
其在阵列看来的角宽度

$$
\delta(\theta, d) = 2\arctan\!\Bigl(\frac{W_\text{ear}/2}{d}\Bigr)
\tag{8.1}
$$

`head_tracker.py:76-77`。当 $\delta$ 大于阵列主瓣宽度时,
零点策略失效(信号会"溢"进对耳),触发 beam-width 警告。

### 8.3 实时模式(D435I)

`head_tracker.py:LiveTracker`。MediaPipe Face Mesh 输出 478 个面部 landmark,
索引 234 / 454 对应左右耳屏(tragus)。
设深度图在像素 $(u,v)$ 处给出 $z$:

$$
x_\text{cam} = (u - c_x)/f_x \cdot z, \quad
y_\text{cam} = (v - c_y)/f_y \cdot z
\tag{8.2}
$$

(D435I 出厂内参 $f_x, f_y, c_x, c_y$ 从 `pyrealsense2` 取,
`head_tracker.py:164-168`。)

### 8.4 外参变换

D435I 安装在阵列正上/下方,垂直偏移 $h$(`CAMERA_HEIGHT_M`)。
相机坐标系 $+y$ 朝下,阵列坐标系 $+y$ 朝上,
外参 $T_{c\to a} \in \mathbb{R}^{4\times 4}$:

$$
T_{c\to a} =
\begin{pmatrix}
1 & 0 & 0 & 0\\
0 & -1 & 0 & h\\
0 & 0 & 1 & 0\\
0 & 0 & 0 & 1
\end{pmatrix}
\tag{8.3}
$$

`head_tracker.py:110-127` 的 `_build_extrinsic`。
存在 `data/extrinsic.json` 时使用文件中的标定矩阵
(可由 `directional_speaker/calibration.py` 交互生成),否则用 (8.3) 默认值。

阵列坐标后 $\theta = \mathrm{atan2}(x_a, z_a)$、$d = \sqrt{x_a^2+z_a^2}$
(`head_tracker.py:228-232`),与 8.1 同公式。

### 8.5 EMA 平滑

实时 landmark 抖动严重。一阶 EMA:

$$
\hat\theta_t = \alpha\,\theta_t + (1-\alpha)\,\hat\theta_{t-1},
\quad \alpha = 0.5
$$

`head_tracker.py:175-190`。半衰期 $\ln 0.5/\ln 0.5 = 1$ 帧 $= 25$ ms,
即 1 帧吸收过去 50% 信息。系统延迟可控、抖动显著降低。

---

## 9. 距离幅度补偿

`audio_adjuster.py`。物理上声压随距离 $\propto 1/d$,
但可闻波在参数阵中按 (2.1) $\propto P_0^2/z$,
所以补偿指数取 1(实现里 `amp_exponent=1.0`):

$$
g_\text{ear} = \min\!\Bigl(\Bigl(\frac{d_\text{ref}}{d_\text{ear}}\Bigr)^{1},\ g_\text{max}\Bigr),
\quad d_\text{ref} = \min(d_L, d_R)
\tag{9.1}
$$

$g_\text{max} = 4$ 防止远耳被疯狂放大触发削顶。
取 $d_\text{ref}=\min$ 而非 $\max$ 的原因:
近耳 $g=1$ 不放大,远耳 $g>1$ 加增益 —— 这保证了**近耳通道始终
不会因增益而剪切**,把削顶风险只集中在远耳。

不做时间对齐:物理路径自带 $\Delta t = (d_L-d_R)/c$,
数字预延时会双倍计入,反而破坏 ITD。

---

## 10. 窗口、跳跃与延迟

窗口 50 ms / 跳 25 ms,50% overlap-and-add 不必要(本项目无 OLA 重叠相加),
但 25 ms 跳跃保证:

- 头部转动响应时间 $\le 25$ ms(人不可感)
- ASIO 缓冲 3 帧 = 75 ms,够吸收抖动且不引入显著唇同步偏差

端到端延迟预算:

| 阶段 | 延迟 |
|---|---|
| 头追踪(D435I 30 fps + EMA) | ~33 ms |
| 帧累积 | ~25 ms |
| 处理(DSP + FFT) | ~5 ms |
| ASIO buffer(3 帧) | ~75 ms |
| **总计** | **~138 ms** |

低于 200 ms 通常不影响沉浸感。

---

## 11. 全链路数学一致性约束

| 约束 | 表达式 | 强制位置 |
|---|---|---|
| 调制度 | $\|z\|\le 1$ | `main.py:129-130` `np.clip` |
| 单耳通带峰 | $\|y_{L/R}\|\le 1$ | $(3.1)$ 数学保证 |
| 8 通道联合峰 | $\|y\|\le 1$ | `beamformer.py:130-132` 后验软限 |
| LUT 角度网格 | $\theta\in\{-60,-57,\dots,60\}$° | `beamformer.py:_quantize` |
| LUT 频率覆盖 | $f\in[f_c-B, f_c+B]$ | `calibrate_nullsteering.py:_freqs` |
| 阵列物理极限 | 主瓣 $\ge 12.7°$ @ 40 kHz | 4.2 节,设计取舍见 `reports/DECISIONS.md` |
| HRIR 重采样 | 44.1 → 96 kHz, 比 320/147 | `hrtf_renderer.py:59-63` |
| 载波相位 | 跨帧绝对样本计数 | `modulator.py:29 _n_emitted` |

任何一处违反都会在仿真或听感上立刻显现:调制度溢出 → THD;
联合峰溢出 → DAC 削顶咔咔声;载波相位不连续 → 帧边界 click。

---

## 12. 参考文献

1. **Berktay, H. O.** (1965). *Possible Exploitation of Non-Linear Acoustics
   in Underwater Transmitting Applications.* J. Sound Vib., 2(4), 435-461.
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
   (ITD 公式来源。)
8. **Westervelt, P. J.** (1963). *Parametric Acoustic Array.*
   J. Acoust. Soc. Am., 35(4), 535-537.

---

*文档版本 v1.0 · 与代码 commit 同步生成 · 修订请同时更新对应 `file:line` 引用。*
