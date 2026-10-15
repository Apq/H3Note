# HoMM3 资源格式（LOD / DEF / PCX）与原版按钮资源清单逆向笔记

> 目标版本：`D:\Heroes3\Heroes3_2026.10.09`（SoD + HD Mod，`HD_SOD.dll` 0.2.0.92 / ProductVersion 5.0.0.4）
> 来源：只读该游戏目录的 `Data\*.lod`、`_HD3_Data\**\*.def|*.pcx`，用 python 自写解析器逐块解码并把帧渲染成 PNG 目视核对
> 记录日期：2026-10-14（H3RndNew 随身空间 UI round-19 需求“找原版有没有表示关闭的 X 形按钮”牵引出的资源考古）
> 脚本：`D:\logs\dsh\scripts\h3-warehouse-ui\{find_close_x.py, probe_defs.py, decode_cancel.py, decode_common.py}`，产物在 `...\x19\`

## 1. 结论速览

| 结论 | 状态 |
| --- | --- |
| LOD 容器格式（条目表布局、zlib 压缩条目、`size==0` 表示“属于前一个压缩容器”） | 已确认 |
| DEF 标准 8-bit 布局：16 字节头 + **调色板 16..784** + **块表 784** | 已确认 |
| **`type=0x47` / `0x43` 的 HD 版 DEF 与 0x40 布局相同**（同样有 768 字节调色板、块表在 784） | 已确认（6 个原版按钮 + `_HD3_Data\Common` 46 个 DEF 全部按此解码成功） |
| 帧数据 fmt：0=原样、1=按行偏移的 RLE、2/3=分块（32 像素）RLE | 已确认（沿用既有`h3-warehouse-skin\extract.py` 解码器） |
| **原版没有“字面 X 形”的关闭按钮资源** | 已确认（两组穷举，见 §4、§5） |
| 原版“关闭/取消”语义按钮 = `H3sprite.lod!iCANCEL.def`（64×30 四态） | 已确认 |
| `_HD3_Data\Common` 里 62/108 个 DEF 未被本解析器识别（`ddb.def`/`mapgrid.def`/`iam_*.def`/`tp_sel.def`/`crdeflt.DEF`(0x46)/`tpmageap.def`(0x49) 等） | **待验证**（可能另有布局或另有类型语义） |

## 2. LOD 容器格式

```
偏移 0   : 4 字节（本机样本未用）
偏移 8   : uint32 条目数 count
条目 i   : 92 + i*32 起 32 字节 =
             char name[16]（NUL 结尾，可含扩展名）
             uint32 offset      # 文件绝对偏移
             uint32 size        # 解压后大小；==0 表示是前一个压缩容器内的子条目
             uint32 type
             uint32 compressed  # 非 0 = 该条目数据被 zlib 压缩，值通常为压缩后大小
```

- 解压：`raw = data[offset : offset + (compressed or size)]`，`compressed != 0` 时再 `zlib.decompress(raw)`，解出长度应等于 `size`。
- 实测容器：`H3ab_bmp.lod` 2491、`H3ab_spr.lod` 569、`H3bitmap.lod` 4919、`H3sprite.lod` 5665 条目。
- **散文件覆盖 LOD 同名资源**（既有结论，见 `HoMM3资源文件名长度限制.md` 与指南 §6），所以“同一个按钮”可能在 `_HD3_Data\**` 与 LOD 里各有一份，`iCANCEL` 这类核心 UI 只存在于 LOD。

## 3. DEF 帧格式（本机 SoD + HD 版实测）

### 3.1 头与块表

```
偏移 0  : uint32 type      # 0x40/0x41 原生；本机 HD 版普遍是 0x43/0x47（还有 0x46、0x49）
偏移 4  : uint32 width     # 声明尺寸（各帧可不同，见帧头）
偏移 8  : uint32 height
偏移 12 : uint32 blocks    # 组数（本机按钮类 DEF 全是 1）
偏移 16 : 调色板 768 字节（256 × RGB）       <-- 仅 0x40/0x43/0x47 这批
偏移 784: 块表
```

块表（每组）：

```
uint32 id, uint32 n, uint32 ?, uint32 ?
n × 13 字节 帧名（NUL 结尾，如 "iCANCELn.pcx"）
n × uint32 帧数据偏移（各自指向帧头）
```

帧头（8 × uint32）：`size, fmt, fullWidth, fullHeight, width, height, left, top`
（`fullWidth/fullHeight` 是整帧画布，`width/height` 是实际绘制的子块，贴到 `(left, top)`）

### 3.2 帧像素编码

- `fmt == 0`：`width*height` 字节裸索引。
- `fmt == 1`：`height` 个 uint32 行偏移表（相对帧体起点），每行是一串 `(code, count-1)`：`code==255` 表示随后 `count` 字节是字面像素，否则该值重复 `count` 次。
- `fmt == 2/3`：分块（`fmt==2` 整行 1 块；`fmt==3` 每 32 像素 1 块）的 uint16 偏移表 + 每字节 `code = v>>5`、`count = (v&31)+1`，`code==7` 为字面量。

### 3.3 坑

- **`type=0x47/0x43` 千万不要当成“无调色板”**：按“块表紧跟 16 字节头”解析会读飞（块表其实在 784）。
- **所有解析出的计数字段都要加范围守卫**：这些文件里字段错位时 `n` 会是天文数字，`for i in range(n)` 会卡死（实测把一个 python 进程烧到 CPU 1380 秒才手动杀掉）。
- **块表用“结构搜索”定位最稳**：遍历 16..1100 的候选偏移，校验 `1<=n<=128`、连续 13 字节帧名全为可打印 ASCII、每帧头 `8×u32` 自洽（`fmt<=8`、`w<=fullW<=2048`、`h<=fullH`、帧偏移落在表尾之后）。本机所有已解出的 DEF 都命中 **784** 这一个候选。
- **`fmt==1` 的行偏移表是 u32，别被“禁用帧的斜纹肌理”误导去换解析**：`d`（禁用）帧背景带斜纹是**原版真实内容**（HD 的禁用态肌理），不是解码伪影。对照实验（`probe_rowtab.py`）：按 u32 行表解，`iCANCEL`/`MuBexit` 的 n/s/d/h 四帧全部出干净图；按 u16 行表解，`iCANCEL` 四帧直接“行不闭合”失败、`MuBexit` 四帧全变满屏斜纹（连正常的 n/h 帧也毁）。**u32 正确**，且“正常帧也会被解坏”就是判别表宽假设错误的快捷信号。

## 4. 原版“关闭”类按钮清单（`Data\*.lod`，按名字过滤 close|exit|cancel|quit|btnx|_x\.|^x\.|esc 共 16 条命中）

| 资源 | 来源 | 尺寸 | 帧（名/语义） | 目视结论 |
| --- | --- | --- | --- | --- |
| **`iCANCEL.def`** | `H3sprite.lod` | **64×30**，type 0x47 | `iCANCELn/s/d/h.pcx`（普通/按下/禁用/高亮 四态） | **H3 对话框标准取消/关闭键**：木纹金底 + 黄圈斜杠「⃠」（不是字母 X） |
| `MuBexit.def` | `H3sprite.lod` | 64×32，0x47 | `MuBexitn/s/d/h` | 金底中文「退出」按钮 |
| `QLexit.def` | `H3sprite.lod` | 32×32，0x47 | `QLexitN/S` | 木底红色「✓」确定键 |
| `SOQUIT.DEF` | `H3sprite.lod` | 100×48，0x47 | `SOQuitS/H` | 退出条（战役/序章） |
| `GSPEXIT.DEF` | `H3sprite.lod` | 166×40，0x47 | `GSPExitn/s/d/h` | 战役退出横幅 |
| `CSSexit.def` | `H3sprite.lod`（另有 `H3ab_spr.lod`） | 120×105，0x47 | `CSSexitN/S/H` | 战役退出画面件 |
| `BoSEscap.pcx` | `H3bitmap.lod` / `H3ab_bmp.lod` | 58×64 | 单帧 | “Esc 键”图形（非 X 形关闭按钮） |

**关键旁证**：H3Auto 的取消键 `img/HA_cancel_normal.pcx` / `HA_cancel_pressed.pcx` 是 **64×30**，逐像素就是 `iCANCEL` 的 n/s 两态 —— 即“自研插件用原版取消键”的既有先例，取图路径可直接复用。

## 5. HD Mod 自带按钮资源（`_HD3_Data\Common`，108 个 `*.def` 中本解析器可解 46 个）

| 资源 | 尺寸 | 帧名/语义 |
| --- | --- | --- |
| `bckpck.def` | 52×36 | `bckpck_n/s/d` — 背包窗按钮（与随身空间/背包主题最相关） |
| `hd_split.def` / `hd_xchng.def` | 52×36 | `split(_p/_d)` / `xchng(_p)` — 分兵 / 交换 |
| `hd_movl/hd_movr/hd_mov1l/hd_mov1r` | 52×36 / 37×19 | 移动/快速移动 |
| `SwAML/SwAMR/SwCML/SwCMR/SwSpl/SwXCh` | 48..64 宽 | 战阵面板按钮（分兵/交换） |
| `Mov1LM/Mov1RM` | 37×23 | 战阵移动（各 6 帧） |
| `icm001q..icm012q`（+e/p/r 变体） | 44×36 / 295×48 | 英雄屏命令按钮（n/s/d，四态的有 h） |
| `qcb.def` | 64×32 | `qc_n/s/P/P2` 四态 |
| `HWBUT2.def` | 116×20 | `GSPBut2n/s/d/h` |
| `PSKIL21.def` | 21×21 | `pskil21a/d/p/s` |
| `SimpFram.def` / `DlgBluBo.def` | 4×4 / 42×42 | 边框角件 / 对话框蓝边框（各 8 帧） |
| `default.def` | 800×600 | `defdffrm` — 默认整窗底图 |

**没有任何一个是 X 形关闭按钮**；HD 窗口的“关闭”很可能就是**游戏字体画的 “X”**（无独立位图资源），这也是自研控件沿用字体 “X” 的合理性依据。

## 6. 工具与复现

```powershell
$py='C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
Start-Process -File $py -ArgumentList @('-X','utf8','D:\logs\dsh\scripts\h3-warehouse-ui\decode_common.py') -Wait -WindowStyle Hidden
# 日志：...\x19\x19-common.txt  接触印相：...\x19\common\*.png
```

- 用 `pythonw.exe` 跑（本机只有 pythonw，无 stdout/stderr）：脚本必须自己 `try/except BaseException` 把 traceback 写进日志文件。
- **只读游戏目录**，产物一律落 `D:\logs\dsh\scripts\h3-warehouse-ui\x19\`；不要往游戏目录写任何解码中间产物。
- 大 LOD 单次读取约几十秒（`H3bitmap.lod` 104MB、`H3sprite.lod` 67MB）：脚本要“一个 LOD 只读一次、一次取全部目标”，否则每个目标重读一遍会慢到不可用。

## 7. 对 H3RndNew 随身空间 UI 的影响（round-19 裁定）

用户要求“X 按钮找一下原版资源有没有表示关闭的 X 形按钮（没有就用当前的）”。取证结论是**没有字面 X 形按钮**，于是**保留当前字体 “X” 的关闭按钮**，理由两条：

1. 原版唯一的关闭/取消位图资源是 `iCANCEL`（⃠ 圆圈斜杠），形状与用户要的“X 形”不符；
2. 当前关闭按钮是 **24×24**，`iCANCEL` 是 **64×30 宽椭圆**，缩放会违反 round-18 用户裁定“按需正中直裁、不缩放/不平铺”的素材纪律。

若将来要用 `iCANCEL`：其四态命名（n/s/d/h）与自研四态按钮模型天然对齐，直接取 n 态作 normal、s 态作 pressed 即可（H3Auto 已如此用），但需重新设计控件尺寸到 ≥64×30。
