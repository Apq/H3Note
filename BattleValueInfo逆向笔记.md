# 逆向笔记

> 本文件只记录**已通过 dump 或反汇编确认**的硬事实，供后续接手者（AI 或人）查阅，
> 避免重复试错。凡标注"确认"的均有实测/反汇编依据；未确认的不写入。
> 目标版本：HoMM3 SoD（HotA + SoD_SP 环境），仅 x86。

## 1. 窗口身份

- 生物信息窗口原版 298×311，本插件通过 exe patch 改为配置高度（默认 487）。
- 背景控件 `id=200`，`(0,0,width,height)`。
- 名称控件 `id=203`，`(20,21,258,19)`。
- **creatureId 存放在 `dlg+0x60`**（三种界面通用，确认）。
- 数量文本在 `id=204`（纯数字，从其文本读取当前数量，确认）。
- 同一时间只有一个该窗口（模态）。三种入口都复用同一布局：战斗/冒险/城镇界面。

## 2. 双击管理窗口完整 item dump（298×487 窗口）

| idx  | id      | flags | x   | y   | w   | h   | vtable   | 资源               | 含义           |
| ---- | ------- | ----- | --- | --- | --- | --- | -------- | ---------------- | ------------ |
| 0    | 200     | 0x800 | 0   | 0   | 298 | 487 | 0x63BA94 | bv_bgA.pcx       | 背景           |
| 1    | 203     | 0x8   | 20  | 21  | 258 | 19  | 0x642DC0 | —                | 名称           |
| 2    | 202     | 0x800 | 21  | 48  | 100 | 130 | 0x63BA94 | CrBkgFor.pcx     | 头像背景         |
| 3    | 201     | 0x12  | 21  | 48  | 100 | 130 | 0x63EC48 | cdrfir.def       | 头像 DEF       |
| 4    | 204     | 0x8   | 21  | 160 | 100 | 20  | 0x642DC0 | —                | 数量文本         |
| 5–14 | 205–218 | 0x8   | 154 | 48→ | 122 | 17  | 0x642DC0 | —                | 属性行(成对)      |
| 15   | 219     | 0x10  | 23  | 189 | 42  | 38  | 0x63EC48 | imrl42.def       | 士气           |
| 16   | 220     | 0x10  | 77  | 189 | 42  | 38  | 0x63EC48 | ilck42.def       | 幸运           |
| 17   | 3006    | 0x8   | 48  | 209 | 20  | 20  | 0x642DC0 | —                | —            |
| 18   | 3007    | 0x8   | 101 | 209 | 20  | 20  | 0x642DC0 | —                | —            |
| 19   | 225     | 0x800 | 215 | 237 | 66  | 32  | 0x63BA94 | bv_frmL.pcx      | 确认金框         |
| 20   | 30722   | 0x2   | 216 | 238 | 64  | 30  | 0x63BB54 | bv_okN.def       | 确认按钮 DEF     |
| 21   | -1      | 0x800 | 19  | 236 | 48  | 34  | 0x63BA94 | bv_frmS.pcx      | 解雇金框         |
| 22   | 30723   | 0x2   | 20  | 237 | 46  | 32  | 0x63BB54 | bv_dsN.def       | 解雇按钮 DEF     |
| 23   | 224     | 0x8   | 7   | 363 | 284 | 19  | 0x642DF8 | —                | 状态栏          |

### 关键结论（确认）

- **确认按钮** = 金框(id=225) + DEF(id=30722)，两个独立控件。
- **解雇按钮** = 金框(id=-1) + DEF(id=30723)，与确认按钮完全同构。
- 解雇金框的 **id 是 -1**（不是独立编号），靠"小尺寸(h<100)"与右键窗口的描述框(h≈105)区分。
- 右键窗口（hold/release）**没有解雇按钮**，但**有描述框** `id=-1, h≈105`。
- **魔法书按钮**仅在法术生物出现时存在（id=30724），与解雇同构。

## 3. 控件 vtable 地址（确认）

| vtable 地址           | 类型                                | Draw 函数(vtable[4])           |
| ------------------- | --------------------------------- | ---------------------------- |
| 0x63BA94            | PCX8 静态 (`_DlgStaticPcx8_`)       | 0x450120                     |
| 0x63BACC            | **PCX16 静态** (`_DlgStaticPcx16_`) | 0x450460                     |
| 0x63BB54            | DEF 按钮 (`_DlgButton_`)            | 0x4EAC20                     |
| 0x63EC48            | DEF 静态 (`_DlgStaticDef_`)         | 0x4EAC20                     |
| 0x642DC0 / 0x642DF8 | 文本控件                              | —                            |

- PCX16 资源对象 vtable = **0x63B9C8**（`_Pcx16_::CreateNew` 设置）；`vtable[1]` 是 DerefOrDestruct(0x55D300)。
- 控件 vtable 在 `+0x00`。当前方案**不复制/不替换 vtable**，只替换控件内部的图片指针（pcx8/def）。

## 4. 渲染行为（反汇编确认）

- **PCX8 静态 Draw (0x450120)**：原样拷贝到屏幕，**不缩放**。
- **DEF 按钮/静态 Draw (0x4EAC20)**：DEF 当前帧**自动居中**绘制，**不缩放**。
- **PCX16 静态 Draw (0x450460)**：经 `DrawSurface16`(0x44DF80) 贴屏，会**登记脏矩形**让引擎刷新。
- **教训（确认）**：直接往 `screen_pcx16->buffer` 写像素**不显示**（没登记脏矩形）。
  正确套路：把内容烘焙进 CPU 内存 pcx16，再让原生 PCX16 控件去显示。

## 5. _DlgItem_ 内存布局（确认）

| 偏移    | 字段                                  |
| ----- | ----------------------------------- |
| +0x00 | v_table                             |
| +0x04 | parent (_Dlg_*)                     |
| +0x08 | prev_item                           |
| +0x0C | next_item                           |
| +0x10 | id (word)                           |
| +0x12 | z_order (word)                      |
| +0x14 | flags (word)                        |
| +0x16 | state (word)                        |
| +0x18 | x (int16)                           |
| +0x1A | y (int16)                           |
| +0x1C | width (word)                        |
| +0x1E | height (word)                       |
| +0x30 | 派生类首字段：PCX 控件=pcx8 指针；DEF 控件=def 指针 |

- `_Dlg_` 的 item 列表在 `dlg+0x30`：`[+0]=vtbl? [+4]=Data起 [+8]=Data止`，
  `cnt = (vec[2]-vec[1])/4`，`data=(char**)vec[1]`。

## 6. 关键函数地址（确认）

| 地址       | 含义                                         |
| -------- | ------------------------------------------ |
| 0x6747B0 | 生物表指针；结构大小 0x74，fight_value 在 +0x3C        |
| 0x55AA10 | `_Pcx8_::Load`（__fastcall，1参数：文件名）          |
| 0x55B1E0 | `_Pcx16_::Load`（__fastcall）                  |
| 0x55C9C0 | LoadDef                                     |
| 0x5F4503 | 战斗 BUILD hook 点（ebx=dlg）                   |
| 0x5F3E75 | 冒险 BUILD hook 点（esi=dlg）                   |
| 0x5F491E | 城镇 BUILD hook 点（esi=dlg）                   |
| 0x41B120 | `_Dlg_::DefProc`（兜底 hook）                  |
| 0x468440 | ShowStatsEntry（功能二标记）                      |
| 0x4746B0 | 右键空格子入口（功能二）                               |
| 0x47BA90 | `_Def_::Draw_Transparent`（DEF 解码，用 def 自带调色板） |
| 0x44DF80 | `DrawSurface16`（pcx16 贴屏，登记脏矩形）              |

## 7. 资源文件系统

### 7.1 资源名长度限制（确认）

LOD 归档条目 `H3LodItem` 和资源管理器 `H3ResourceItemData` 中，名字字段固定 `CHAR name[12]`。
即资源文件名（含扩展名）**最多 11 字符 + null 终止**。

### 7.2 PCX 格式要求（确认）

游戏 `bitmap8` 加载只认 **1 plane × 8 bpp 的 ZSoft PCX**。
3 plane × 8 bpp（24-bit RGB）会报 `could not find the "bitmap8" resource`。

### 7.3 资源覆盖机制（确认）

游戏按**文件名**从 `Data\` 加载散文件，优先于 LOD 档案。
自制 PCX 放 `Data\` 即覆盖；不同名的文件（如 `bv_bgA.pcx` vs 原版 `CrStkP1.pcx`）互不干扰。

### 7.4 游戏内部资源类型常量（确认）

| 常量 | 值 | 含义 |
|------|---|------|
| PCX8 / BITMAP8 | 0x10 | 8 位索引 PCX |
| PCX24 / BITMAP24 | 0x11 | 24 位 PCX |
| PCX16 / BITMAP16 | 0x12 | 16 位 PCX |

游戏内部已有 `H3LoadedPcx24` 类，支持加载 24-bit PCX 并转 RGB565。

## 8. exe patch 地址表（窗口尺寸/布局，BattleValueInfo 内联实现）

以下 patch 由 BattleValueInfo 直接写入，用于扩展生物信息窗口尺寸与布局；当前项目不依赖外部“生物框”插件或 shengwukuang.dll/txt。
地址基于原版 SoD exe。

| 地址 | 原值 | 含义 |
|------|------|------|
| 0x68C6E8 | `CrStkP1.pcx` | 背景图名；当前不再 patch 该字符串，运行时局部替换背景控件内部 `_Pcx8_*` |
| 0x5F3F1B, 0x5F406B | `push 0x137`(311) | 战斗界面窗口高度×2 |
| 0x5F3728, 0x5F38CF | `push 0x137`(311) | 冒险界面窗口高度×2 |
| 0x5F45D8, 0x5F4712 | `push 0x137`(311) | 城镇界面窗口高度×2 |
| 0x5F4117 | `6A 13` | 名称行参数 |
| 0x5F4469, 0x5F3E3E, 0x5F4884 | 字体引用 | 三界面字体改 smalfont.fnt(0x65F2F8) |
| 0x5F446F/71, 0x5F3E44/46, 0x5F488A/8C | 文本尺寸 | 三界面文本区高度/宽度 |
| 0x5F44D3, 0x5F3CE4, 0x5F48EE | `push 0x15B`(347) | 三界面详细信息栏 Y 坐标 |

所有值已改为从 INI `[Layout]` 段动态生成。

## 9. 可用绘制原语

- `_Pcx16_::DrawPcx16Resized`：最近邻缩放。
- `_Pcx16_::DrawPcx8`：区域拷贝，跳过 index0（透明）。
- `_Pcx16_::CreateNew / Delete`、`_Pcx8_::Load`/`_Pcx8_::CreateNew`。
- `_Def_::Draw_Transparent`（0x47BA90）：DEF 解码，**用 def 自带调色板**，颜色正确。

### DEF 帧绘制踩坑（确认）

- ❌ `_DefFrame_::DrawInterfaceToPcx16`：需外部传调色板，传错→绿色乱码。
- ✅ `_Def_::Draw_Transparent`：内部用 def 自带调色板，颜色正确，但**不缩放**。
  要缩放：先画原尺寸到临时 pcx16，再 `DrawPcx16Resized`。

## 10. LOD 文件格式（确认）

LOD 档案：`Data\` 下，精灵(DEF) 在 `H3sprite.lod`/`H3ab_spr.lod`，位图(PCX) 在 `H3bitmap.lod`/`H3ab_bmp.lod`。

- 文件头：`4s(magic) I(type) I(count)`；文件表从 `0x5C` 起，每项 32 字节：
  `name[16], offset(4), usize(4), type(4), csize(4)`。`csize>0` → zlib 压缩。
- HoMM3 内部 PCX（非标准）：`size(4) w(4) h(4)` + 像素；
  `size==w*h` → 8 位+尾随 768 字节调色板；`size==w*h*3` → 24 位 BGR。
- DEF：`type(4) fullW(4) fullH(4) blocks(4)` + 256×3 调色板；
  DEF 特殊调色板：index0=(0,255,255) 透明，index1=(255,150,255) 阴影。

## 11. 24-bit PCX 图像处理（当前方案：复用原控件 + 量化后的 `_Pcx8_`）

当前不做全局 `_Pcx8_::Load` hook，也不让游戏资源系统直接加载 24-bit/3-plane PCX。

核心原则：**不新建控件、不换 vtable、不走 PCX16 控件；复用原控件，把控件内部图片指针替换为已量化好的 `_Pcx8_*`。**

背景在 `AdjustCreatureInfoDlg` 中局部处理：

1. 找到原背景控件 `id=200`，保留其 vtable、层级和绘制路径；
2. 读取插件目录 `pcx\\bv_bgA.pcx`（标准 24-bit / 3-plane PCX）；
3. 自己 RLE 解码 R/G/B 三个 plane；
4. 使用原背景控件已加载 `_Pcx8_*` 的调色板做最近色量化；
5. 构造新的 `_Pcx8_`，替换 `id=200` 控件内部的 `pcx8` 指针。

同一原则也适用于解雇按钮、魔法书按钮等图片替换：

- 优先找到原有 PCX8 控件（例如按钮外框/底图），保留原控件；
- 自己读取 24-bit PCX 素材并量化；
- 给原控件替换量化后的 `_Pcx8_*`；
- 不再用“新建 PCX16 控件 / 换 vtable / 合成 PCX16 图”的路线，除非以后有新的硬证据证明其稳定。

这样可以避免：

- 依赖外部插件；
- 全局 hook `_Pcx8_::Load` 影响其它资源；
- PCX16/HD_TC 显示链路导致的颜色异常；
- 新控件插入导致的 z-order / 生命周期问题。

代价：24-bit 图会量化到 8-bit 调色板，存在轻微色差。

## 12. 生物描述信息控件与 ZCN2 兼容（最终确认）

### 12.1 原版描述控件创建方式

生物信息窗口的描述信息是 `_DlgStaticText_`，不是 `_DlgScrollableText_`。原版通过 `_DlgStaticText_::Create` (`0x5BC6A0`) 创建。

三个标准创建点已从 `Heroes3.exe` 字节确认：

| 场景 | 参数区 | call 点 |
|------|--------|---------|
| 战斗 | `0x5F4469` 附近 | `0x5F447F` |
| 冒险 | `0x5F3E3E` 附近 | `0x5F3E54` |
| 城镇 | `0x5F4884` 附近 | `0x5F489A` |

原版参数：

| 参数 | 原版值 | 说明 |
|------|--------|------|
| `x` | `20` | 左边距 |
| `y` | `232` | 原版描述框 Y |
| `width` | `192` | 原版宽度 |
| `height` | `41` | 原版高度 |
| `id` | `-1` | 与部分小 PCX 金框共用，需结合 vtable/尺寸判断 |
| `flags` | `8` | 文本控件 flags |
| `text_color` | `4` | 文本颜色 |
| `font_name` | `0x65F2F8` | 当前 patch 为 `smalfont.fnt` |

战斗创建点示例：

```asm
6A 08                    ; flags
6A 00                    ; bkcolor
6A 00                    ; align
57                       ; id = -1
6A 04                    ; text_color
68 F8 F2 65 00           ; font_name
52                       ; text
6A 29                    ; height = 41
68 C0 00 00 00           ; width = 192
68 E8 00 00 00           ; y = 232
6A 14                    ; x = 20
E8 ...                   ; call 0x5BC6A0
```

描述文本来源：生物表 `*(char**)0x6747B0`，结构大小 `0x74`，描述指针在 `creature + 0x1C`。

```cpp
char* table = *(char**)0x6747B0;
const char* desc = *(const char**)(table + creature_id * 0x74 + 0x1C);
```

### 12.2 `h=65487` 根因

`h=65487` 已确认不是可靠的“ZCN2 特殊控件协议”，而是旧 patch 把 `TextHeight=207` 直接写进原版 `push imm8` 后产生的符号扩展结果。

原版：

```asm
6A 29   ; push imm8 0x29 = 41
```

旧 patch：

```asm
6A CF   ; push imm8 0xCF
```

x86 `push imm8` 会有符号扩展：

```text
0xCF -> -49 -> 0xFFFFFFCF
低 16 位 = 0xFFCF = 65487
```

结论：不能用原地 `6A xx` 表示 `TextHeight > 127`。

### 12.3 最终描述控件方案：call 前改栈

最终方案不是大范围重写原版 push 序列，而是在 `_DlgStaticText_::Create` call 前 LoHook 改写栈参数。

| 场景 | call 点 | 处理 |
|------|---------|------|
| 战斗 | `0x5F447F` | 改写栈上 `x/y/w/h` |
| 冒险 | `0x5F3E54` | 改写栈上 `x/y/w/h` |
| 城镇 | `0x5F489A` | 改写栈上 `x/y/w/h` |

LoHook 触发时，栈顶参数布局为：

```text
esp+00 = x
esp+04 = y
esp+08 = width
esp+0C = height
```

写入：

```cpp
sp[0] = 20;
sp[1] = cfg.desc_y + 6;  // 当前 254
sp[2] = cfg.text_width;  // 当前 200
sp[3] = cfg.text_height; // 当前 207，真实 32-bit 高度
```

保留一个安全的原地 `height` 占位（如 `105`），避免原版指令流在 hook 前产生负高度；真正传给 `Create` 的高度由栈 hook 修正。

验证日志 `BattleValueInfo_20260628_001150.log` / `BattleValueInfo_20260628_011201.log` 已确认：

```text
DescCreateParams: stack patched ... x=20 y=254 w=200 h=207
id=-1 vt=00642DC0 flags=0008 x=20 y=254 w=200 h=207
h=65487 0
```

### 12.4 ZCN2 崩溃根因与窗口吸附

描述框变为 `y=254 h=207` 后，如果窗口本身太靠下，ZCN2 会按绝对屏幕坐标绘制到 HD buffer 外并在 `ZCN2.dll+0x11A34` 越界。

典型崩溃标记：

```text
[Z571_Y254_...]
窗口 y = 571
描述 y = 254
描述 h = 207
绝对底边 = 571 + 254 + 207 = 1032
```

当前 HD 启动器分辨率为 `1712x900`，所以底边 1032 越过 900 高 buffer。

### 12.5 安全高度来源

`o_ScreenHeight` 在 HD/OpenGL 模式下可能是桌面/逻辑高度，例如 `1440`，不能作为 ZCN2 绘制安全高度。

最终以 HD 启动器配置为准：读取 `Heroes3.exe` 同目录下：

```text
_HD3_Data\Settings\sod.ini
<Graphics.Resolution> = 1712x900
```

解析 `1712x900` 或 `1712, 900`，使用其中高度作为 `safe_h`；读不到时才 fallback 到 `o_ScreenHeight`。

验证日志：

```text
SafeRenderHeight: hd_resolution_h=900 o_ScreenHeight=1440 safe_h=900
```

### 12.6 最终窗口 Y 吸附方案

不在 BUILD 阶段直接改 `dlg->y`。最终在 `_Dlg_` 初始化入口 `0x41AFA0` LoHook 中扫描栈参数，匹配生物信息窗口尺寸：

```text
w = 298
h = cfg.window_height  // 当前 487
```

然后按 HD 分辨率高度夹 `y`：

```cpp
max_by_window = safe_h - cfg.window_height;
max_by_desc   = safe_h - (cfg.desc_y + 6) - cfg.text_height;
max_y = min(max_by_window, max_by_desc);
y = clamp(y, 0, max_y);
```

当前配置：

```text
safe_h = 900
window_h = 487
desc_y + 6 = 254
text_h = 207
max_by_window = 413
max_by_desc = 439
max_y = 413
```

验证日志 `BattleValueInfo_20260628_011201.log`：

```text
DlgInitY: stack[1] y adjusted 558 -> 413 ... safe_h=900 raw_screen_h=1440
DlgInitY: stack[1] y adjusted 474 -> 413 ... safe_h=900 raw_screen_h=1440
AfterAdjust dlg=... x=409 y=413 w=298 h=487
AfterAdjust dlg=... x=1025 y=413 w=298 h=487
```

该轮测试没有新的崩溃；`HD_CRASH_LOG.txt` 仍停留在上一轮旧崩溃。

### 12.7 正常高度 `h=41` 兜底

部分带魔法书/施法按钮的窗口会创建正常高度描述控件：

```text
id=-1 vt=00642DC0 flags=0008 x=72 y=232 w=140 h=41
```

这是正常 `_DlgStaticText_`，不是 `h=65487` 问题。由于魔法书按钮已被移到右侧按钮列，该控件可在 BUILD 阶段兜底调整为：

```text
x=20
y=cfg.desc_y + 6
w=cfg.text_width
h 保持 41
```

验证日志：

```text
BUILD: 正常描述控件兜底调整 ... old=(72,232,140,41) target=(20,254,200)
```

### 12.8 当前最终原则

- 描述控件创建参数必须在 `_DlgStaticText_::Create` 前修正，不能在 ZCN2 初始化/绘制后改扩展高度控件字段。
- `TextHeight > 127` 不能写成原版 `push imm8`。
- 窗口 Y 吸附必须按 HD 启动器分辨率高度计算，不能用 `o_ScreenHeight`。
- BUILD 阶段只保留正常高度控件（如 `h=41`）兜底调整；扩展高度描述控件只记录，不再改字段。


## 13. 战场显示区域与重绘边界（确认）

### 13.1 全局重绘边界地址

`homm3.h` 已定义：

```cpp
#define BattleRedraw_Borders (*(_RedrawBorders_*)0x694F68)
```

`_RedrawBorders_` 字段语义：

```cpp
struct _RedrawBorders_ {
    int Left;
    int High;
    int Right;
    int Low;
};
```

该结构用于战斗场景的重绘裁剪边界。字段含义由 `homm3.h` 中 `_BattleMgr_` 的边界计算逻辑确认：

```cpp
Brd.Left  = max(X_Pos, BattleRedraw_Borders.Left);
Brd.High  = max(Y_Pos, BattleRedraw_Borders.High);
Brd.Right = min(X_Pos + Width - 1, BattleRedraw_Borders.Right);
Brd.Low   = min(Y_Pos + Height - 1, BattleRedraw_Borders.Low);
```

因此 `BattleRedraw_Borders.Left/Right/High/Low` 可作为战场实际渲染/重绘范围的当前全局边界。

### 13.2 `_BattleMgr_::dlg` 偏移

`_BattleMgr_` 中确认：

```cpp
_Dlg_* dlg; // +0x132FC
```

`GetHexIxAtXY` 也确认战场坐标会扣除 `dlg->x / dlg->y`：

```cpp
inline int GetHexIxAtXY(int x, int y) {
    return CALL_2(int, __stdcall, 0x464380, x - dlg->x, y - dlg->y);
}
```

这说明 `_BattleMgr_::dlg` 是战斗窗口/战场坐标换算的基准窗口。若全局重绘边界异常，可用 `dlg->x + dlg->width / 2` 作为战场中心的回退值。

### 13.3 `0x493FC0` 战场重绘函数中的确认点

`_BattleMgr_::RedrawBattlefield` 调用地址：

```cpp
CALL_7(void, __thiscall, 0x493FC0, this, Flip, SetBattleRedraws, UseBattleRedraws,
       WaitingTime, RedrawBackground, Wait);
```

反汇编 `0x493FC0` 可确认：

```asm
0x00493fc7  mov esi, ecx                         ; esi = BattleMgr*
0x00494043  mov ecx, dword [esi + 0x132fc]       ; ecx = mgr->dlg
```

在完整背景重绘分支中可见原版战场背景尺寸常量：

```asm
0x004940da  push 0x22c    ; 556
0x004940df  push 0x320    ; 800
0x004940e8  call 0x44df80 ; DrawSurface16
```

即原版战斗背景绘制面以 `800 × 556` 为基础尺寸。

在局部重绘分支中，函数读取 `_BattleMgr_` 的局部边界字段并计算宽高：

```asm
0x004940f4  mov ecx, dword [esi + 0x13d3c]
0x004940fa  mov edx, dword [esi + 0x13d38]
0x00494119  mov eax, dword [esi + 0x13d44]
0x00494121  sub eax, edi
0x00494123  inc eax
0x00494125  mov eax, dword [esi + 0x13d40]
0x0049412b  sub eax, ebx
0x0049412d  inc eax
```

这些字段参与 `DrawSurface16(0x44DF80)` 的局部矩形拷贝，属于战场局部重绘矩形链路。

### 13.4 插件面板定位的可靠依据

用于把战场顶部远程力量面板吸附到战场范围上方中心时，优先顺序应为：

1. 使用 `BattleRedraw_Borders.Left/Right` 的中点作为战场显示区域中心 X。
2. 使用 `BattleRedraw_Borders.High` 作为战场显示区域顶部 Y。
3. 若边界值异常，再回退到 `_BattleMgr_::dlg`：

```cpp
center_x = dlg->x + dlg->width / 2;
y        = dlg->y + configured_offset;
```

当前确认范围仅限：

- `BattleRedraw_Borders` 是战场重绘裁剪边界；
- `_BattleMgr_::dlg` 是战场坐标换算基准窗口；
- `0x493FC0` 使用 `mgr->dlg` 与 `800×556` 原版背景尺寸进行战场绘制。

尚未写入固定运行时坐标值；具体 HD 分辨率下的 `screen/dlg/borders` 数值需以运行日志为准。

## 14. HD ReplayableQB 结果窗口“取消”按钮来源（确认）

本节记录 2026-07-01 对 HD Mod 结果窗口附加按钮的反汇编确认信息。

### 14.1 结论

快速战斗结果窗口上的“取消”按钮不是 BattleValueInfo 插件添加的，也不是原版 `CPResult` 构造函数直接创建的。

已确认来源为 HD Mod 的 `HD_SOD.dll` 中 Replayable Quick Battle 相关逻辑。

核心开关/字符串：

| 项 | 确认值 |
|----|--------|
| 功能开关 | `HD+.ReplayableQB` |
| 语言/文本键 | `ApplyQBattleResult` |
| 相关配置/功能键 | `HD.QuickCombat` |
| 按钮资源 | `iCANCEL.def` |
| 按钮 ID | `0x1FB` / `507` |

### 14.2 `HD_SOD.dll` 字符串位置

目标文件：

```text
D:\Heroes3\Heroes3_2026.05.01\HD_SOD.dll
```

PE 信息：

```text
ImageBase = 0x01000000
.text paddr = 0x00000400, vaddr = 0x01001000
.rdata paddr = 0x00129200, vaddr = 0x0112A000
```

已确认字符串：

| 字符串 | VA | 说明 |
|--------|----|------|
| `ApplyQBattleResult` | `0x0114309C` / `0x011430B0` / `0x011430C4` | 快速战斗结果应用文本键 |
| `box64x30.pcx` | `0x011430D8` | 按钮/背景资源 |
| `iCANCEL.def` | `0x011430E8` | 取消按钮 DEF 资源 |
| `HD.QuickCombat` | `0x011430FC` | 快速战斗相关键 |
| `HD+.ReplayableQB` | `0x0114766C` | 可重打快速战斗结果开关 |
| `QuickFinishBattle` | `0x01145770` | 快速结束战斗文本键 |

### 14.3 添加结果窗口按钮的函数

已确认函数入口附近：

```text
HD_SOD.dll VA 0x010A6630
文件偏移约 0x000A5A30
```

该函数开头附近会检查：

```asm
push 0x114766c              ; "HD+.ReplayableQB"
call 0x10051a0              ; 读取 HD 配置/开关对象
cmp dword [eax], 0
```

并在满足条件时处理 `ApplyQBattleResult` 文本和附加按钮。

### 14.4 “取消”按钮创建点

确定的按钮创建序列位于：

```text
HD_SOD.dll VA 0x010A6778 ~ 0x010A67E7
```

关键反汇编：

```asm
0x010A6778  push 2
0x010A677A  push 1
0x010A677C  push 1
0x010A677E  push 1
0x010A6780  push 0
0x010A6782  push 0x11430e8        ; "iCANCEL.def"
0x010A6787  push 0x1e61           ; hotkey/消息相关值
0x010A678C  push 0
0x010A678E  push 0
0x010A6790  push 0x1fb            ; id = 507
0x010A6795  push 0x15             ; y = 21
0x010A6797  push 0x68             ; x = 104
0x010A6799  mov eax, 0x617492
0x010A679E  call eax              ; 分配/构造前置包装
0x010A67A0  add esp, 4
0x010A67A3  mov edx, 0x455BD0     ; 原版 _DlgButton_::Create
0x010A67A8  mov ecx, eax
0x010A67AA  call edx
0x010A67AC  mov [ebp-4], eax      ; 保存按钮指针
...
0x010A67E0  mov eax, [ebp-4]
0x010A67E3  push eax
0x010A67E4  mov ecx, [ebp+0x0C]   ; 目标 dlg
0x010A67E7  call 0x1055C70        ; 加入结果窗口 dlg
```

由此确认：

- 该按钮是 HD 在结果窗口对象上动态追加的 `_DlgButton_`；
- 使用原版 `_DlgButton_::Create`，地址 `0x455BD0`；
- 资源名为 `iCANCEL.def`；
- 控件 ID 为 `507`；
- 该逻辑属于 `HD+.ReplayableQB` / 快速战斗结果可重打机制。

### 14.5 相关按钮/文本创建

同一函数还创建/处理 `ApplyQBattleResult` 文本与 `box64x30.pcx`：

```asm
0x010A66C9  push 0x114309c        ; "ApplyQBattleResult"
0x010A66D0  push 0x11430b0        ; "ApplyQBattleResult"
...
0x010A6704  push 0x11430c4        ; "ApplyQBattleResult"
...
0x010A675C  push 0x11430d8        ; "box64x30.pcx"
```

这说明结果窗口中的“应用结果/取消重打”一组 UI 元素由同一段 HD_SOD.dll 逻辑创建。

### 14.6 取消按钮事件处理线索

同一附近存在后续处理函数，入口约：

```text
HD_SOD.dll VA 0x010A6800
```

该函数会读取事件/消息值，并对若干地址常量比较：

```asm
cmp [ebp-4], 0x477254
cmp [ebp-4], 0x4772F4
cmp [ebp-4], 0x4AD2F7
cmp [ebp-4], 0x4AE121
```

其中当当前/焦点控件 ID 匹配 `0x1E61` 时，会写入：

```asm
mov dword [0x1151E68], 2
mov dword [ecx], 0x477303
```

该段与取消/重打流程有关，但这里仅记录已反汇编确认的地址和值；具体状态机语义需后续单独验证。

### 14.7 与原版 CPResult 的关系

原版 `Heroes3.exe` 中 `CPResult.pcx` 引用位于 `CPResult` 构造流程：

```text
Heroes3.exe VA 0x0046FE20 附近
CPResult.pcx 字符串 VA 0x00670188
引用文件偏移 0x0006FEA0
```

扫描确认 `CPResult.pcx` 只在原版结果窗口构造中被引用；`HD_SOD.dll` 不直接引用该字符串，而是在运行时对已有结果窗口 dlg 追加 ReplayableQB 相关控件。

因此后续若要观察或处理 HD 的取消按钮，应优先围绕：

- HD_SOD.dll `0x010A6630` 附近的 ReplayableQB UI 创建函数；
- 按钮 ID `0x1FB` / `507`；
- 原版 `_DlgButton_::Create` (`0x455BD0`) 与 HD 加入 dlg 的调用点 `0x010A67E4`；
- 事件处理入口约 `0x010A6800`。

不要误判为 BattleValueInfo 插件自身添加，也不要只从原版 `CPResult.pcx` 构造函数中寻找该按钮。


## SoD_SP SpellDetails 无目标魔法书详情（确认）

- 环境：`D:\Heroes3\Heroes3_2026.05.01\_HD3_Data\Packs\SoD_SP插件19版\SoD_SP.dll`。
- 配置项表中存在 `SpellDetails` 字符串，文件偏移 `0x59868`，运行 VA `0x1005AA68`。
- 配置项表起始附近：`0x10059BB0`；其中 `SpellDetails` 表项在 `0x10059BF8`。
- `SpellDetails` 对应运行时开关字节为 `0x10065673`。
- 对 `0x10065673` 的直接引用共 3 处（文件偏移 / VA）：
  - `0x9BDC` / `0x1000A7DC`，函数起点 `0x1000A7A0`。
  - `0x9C8C` / `0x1000A88C`，函数起点 `0x1000A850`。
  - `0xA241` / `0x1000AE41`，函数起点 `0x1000ADF0`。
- SoD_SP hook 注册处确认：
  - `0x1000A7A0` hook 原版地址 `0x004F55F8`。
  - `0x1000A850` hook 原版地址 `0x00571709`。
  - `0x1000ADF0` hook 原版地址 `0x005591B9`。
- `0x1000ADF0` 不是魔法伤害算法；它是通用数值格式化/显示增强逻辑，确认看到格式串：
  - `%d,%03d`
  - `%d,%03d{k}`
  - `%d{M}`
  - `%d,%03d{M}`
- `0x1000A7A0` 与 `0x1000A850` 会在 `SpellDetails` 开启时读取 UI/控件对象中已有的数值字段：
  - `mov esi, [eax+8]` 或同类读取；
  - 判断 `>= 1000` 后改写/追加控件文本；
  - 这两处目前确认更像“把已有 value 插入控件文本”，不是直接计算法术伤害。
- 因此当前结论：SoD_SP `SpellDetails` 很可能不直接实现完整无目标魔法伤害公式，而是读取魔法书 UI 控件中已经存在的数值字段并增强显示；真正需要继续追的是原版/HD 在魔法书控件创建或刷新时，谁给该控件数值字段（疑似 `+8`）赋值。
- 已排除一条错误方向：带 `target stack`、目标 HP/数量的 SoD_SP 代码链属于战场施法/预览/实际施法相关路径，不是魔法书右键无目标详情算法。

## 原版法术伤害相关函数链（确认）

### FUN_004e52f0 @ 0x4E52F0 — 取有效法术等级

签名：

```cpp
int __thiscall FUN_004e52f0(int spellId, int heroContext)
```

- 读取 `o_Spell[spellId]` 的 school flags（`PTR_DAT_00687fa8 + spellId * 0x88 + 0x1c`）。
- 根据英雄对应的魔法学派等级（气/水/土/火）返回有效法术等级（0-3）。
- 内部调用 `FUN_004e5370(schoolFlags, heroContext)` 做学校等级换算。
- 在魔法书窗口 `FUN_005a3560` 中被调用：

```cpp
iVar4 = FUN_004e52f0(iVar6, *(undefined4 *)(DAT_00699420 + 0x53c0));
```

其中 `DAT_00699420` 是 BattleMgr，`+0x53c0` 是当前英雄指针。

### FUN_004e54b0 @ 0x4E54B0 — 带额外检查的法术等级

类似 `FUN_004e52f0`，但还会从 `o_Spell + (level + spellId * 0x22) * 4 + 0x20` 取值，并调用 `FUN_0044a850` 做额外检查。

### FUN_004e6260 @ 0x4E6260 — 英雄法术特长加成

签名：

```cpp
int __thiscall FUN_004e6260(int hero, int spellId, int creatureLevel, int baseValue)
```

- 检查 `hero->specialty` 类型是否为 3（法术特长）。
- 检查特长对应的 spellId 是否匹配。
- 匹配后按 spellId 分支处理：
  - `case 0x0f`（雷鸣爆弹）：返回 `baseValue / 2`
  - `case 0x2b/0x2c/0x2d/0x2e/0x30/0x35`：返回固定表 `DAT_0063eaa8` 中值
  - `case 0x2f`：返回 2
  - `case 0x33`：返回 `3 - baseValue`
  - `case 0x37`：返回 `DAT_0063eac4` 表值
  - `default`：按英雄等级和目标等级算额外加成
- `hero + 0x1a` 是英雄特长 ID。

### FUN_005a8c60 @ 0x5A8C60 — 法术说明文本生成

用于生成法术详细描述文本。
- 引用 `o_Spell[spellId * 0x88 + 0x10]`（法术名）。
- 按 spellId 分支生成说明文本。
- 包含伤害数值的文本格式化。

### FUN_005a2b90 @ 0x5A2B90 — 法术提示字符串

生成法术简短提示文本（tooltip）。
- 读取 `o_Spell[spellId * 0x88]`（spell flags）。
- 按 flags 和 spellId 分支。
- 对伤害类法术会格式化数值。

### 当前推断：无目标魔法伤害值链

```text
1. effectiveLevel = FUN_004e52f0(spellId, hero)
2. baseDamage = o_Spell[effectiveLevel].effect[effectiveLevel]
              + o_Spell[effectiveLevel].eff_power * hero->power
3. specialtyBonus = FUN_004e6260(hero, spellId, 1, baseDamage)
4. Sorcery 加成
5. displayDamage = 最终值
```

### 待确认

- `FUN_004e52f0` 的第二个参数到底是 hero 指针还是 hero->power。
- `o_Spell` 结构的 `effect` 数组与 `eff_power` 字段的确切偏移。
- Sorcery 在原版里的应用位置（是在 `FUN_005a8c60` 文本生成时加，还是在更底层）。

### 已确认：英雄特长体系

#### spec 表结构

- **spec 表指针**：`*(_ptr_*)0x679C80`（需要一次解引用）
- **每条记录** 0x28 字节，用 hero_id 索引
- **hero_id**：`*(int*)((char*)hero + 0x1a)`
- **hero_level**：`*(short*)((char*)hero + 0x55)`
- **字段**：
  - `+0`: spec_type（0=技能特长, 3=法术特长）
  - `+4`: spec_param（技能特长时=HSS_常量；法术特长时=spellId）

#### spec_type=0 技能特长

当 spec_type=0 且 spec_param=25(HSS_SORCERY) 时，为**魔力特长**。

魔力特长不通过 `FUN_004e6260` 起作用（该函数对 spec_type≠3 的英雄返回 0），而是直接修改 Sorcery 技能的乘数。

#### 魔力特长公式（实测确认）

```text
effective_sorcery_pct = sorcery_base_pct × (1 + hero_level / 20.0)
```

- sorcery_base_pct: Basic=0.05, Advanced=0.10, Expert=0.15
- 浮点计算，最终 `ftol` 截断
- **必须已学会 Sorcery 副技能才生效**（无技能时 base=0，特长加成也为 0）

实测（58 级、专家魔力、冰bolt sp=92）：
```text
base = 50 + 20×92 = 1890
mult = 1 + 0.15×(1 + 58/20) = 1 + 0.15×3.9 = 1.585
damage = (int)(1890 × 1.585) = 2995  ✓ (魔法书显示一致)
```

#### homm3.h 主属性偏移修正

homm3.h 中 `power` 定义在 +1142(0x476)，与 `attack` 同偏移，这是定义错误。
实际 4 个主属性在 0x476~0x479，顺序为 ATK/DEF/SPW/KNO：

```cpp
int atk = *(unsigned char*)((char*)hero + 0x476);
int def = *(unsigned char*)((char*)hero + 0x477);
int spw = *(unsigned char*)((char*)hero + 0x478);
int kno = *(unsigned char*)((char*)hero + 0x479);
```

原版代码确认（`FUN_004e6390` 等）从 `param_1 + 0x476` 开始连续读 4 字节。
