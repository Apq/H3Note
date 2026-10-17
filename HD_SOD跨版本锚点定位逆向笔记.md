# HD_SOD 跨版本锚点定位与随身空间界面兼容逆向笔记

记录日期：2026-10-17。任务缘起：玩家反馈「随身空间在 5.4 版本显示不了」。用户裁定把界面改成
支持多个 HD_SOD 版本，并尽量兼容后续 SOD 版本更新。

结论一句话：**界面代码本身没坏，是版本门卫把旧版 HD_SOD 整块拒了**。门卫原先要求
`FileVersion=0.2.0.92 + 文件大小 1451520 + SHA256 37FA9723…` 三者全中，而整合包自带的
HD_SOD 是 0.2.0.34（1325568 字节），于是 `随身空间UI: HD_SOD 指纹不匹配，阶段A不安装任何UI Hook`，
面板从不出现。

## 1. 两个目标文件

| 版本 | 路径 | 大小 | SHA256 |
|------|------|------|--------|
| 0.2.0.92 | `D:\Heroes3\Heroes3_2026.10.09\HD_SOD.dll` | 1451520 | `37FA9723F39349558CA82F5379531311C266E8DFFFA382F80BB7550902039C75` |
| 0.2.0.34 | `D:\Heroes3\英雄无敌3 V5.4\HD_SOD.dll` | 1325568 | `62BC488A39B19062B0B533B034C7CCD8F758514E4B40394CAC153A02204EBD18` |

两者 `ProductVersion` 都是 `5.0.0.4`，`ImageBase` 都是 `0x1000000`，节区布局：

- 0.2.0.92：`.text` VA 0x1000 / VSize 0x12F400 级；映像 SizeOfImage 0x1123000
- 0.2.0.34：`.text` VA 0x1000 / VSize 0x1154F1；映像 SizeOfImage 0x1105000

> 换算仍按专题笔记的老规矩：`.text` 的 `file = rawPtr + (rva - sectionVA)`，别漏掉 sectionVA。

## 2. 先说被推翻的方案（供后人止步）

**先试的方案：把 5.4 的 HD_SOD 换成 10.09 那份**。2026-10-17 实测**可行**：
替换后门卫 `version=1 size=1 hash=1 bytes=1` 全绿，面板 attach/展开/关闭/detach 全流程正常。
但用户随后裁定「先还原 5.4 的 HD_SOD，并且要支持两个版本、最好能跟后续版本更新」——
理由很实在：那是玩家的整合包，发布时不能要求每个玩家替换 HD Mod 核心 DLL
（它们和 HD_ES/HD_WOG/patcher_x86 是一套）。所以最终没走替换路线。

还原方法与备份位置：原版备份在 `D:\Heroes3\_backup_hdsod_20261017\HD_SOD.dll.0.2.0.34.orig`。

## 3. 完整背包构造函数的两版定位（字符串交叉验证）

方法：搜 `BkPack.pcx` / `"Backpack"` 字符串 → 找 `.text` 中引用其 VA 的 `push imm32` → 向前回溯函数 prolog。

| 版本 | `BkPack.pcx` 字符串 RVA | 引用点 RVA | 构造函数 RVA | 结尾 |
|------|------------------------|-----------|--------------|------|
| 0.2.0.92 | 0x1426B0 | 0x039C03 | **0x039A00** | `ret 0x18`（6 栈参） |
| 0.2.0.34 | 0x1218AC | 0x03AF49 | **0x03AD80** | `ret 0x18`（6 栈参） |

两版都内联构造状态条：`mov edx, 0x5BCB70`（H3.exe 的 `H3DlgTextPcx` 构造，绝对地址，**勿加
HD_SOD 基址**）→ call → `call 0x1006030`（把 item 加入 dialog）→ `mov [ecx+0x74], eax`
（状态条存 dlg+0x74），与旧笔记一致。

## 4. 模态调用窗口：两版逐字节相同（关键发现）

0.2.0.92 @ `0x039E66` 与 0.2.0.34 @ `0x03B170` 的前 23 字节**完全一致**：

```
6A 00                 push 0            ; ShowAndRun 栈参
BA 04 00 00 00        mov  edx, 4
6B C2 06              imul eax, edx, 6  ; vtable 偏移 0x18
8B 4D F8              mov  ecx, [ebp-8] ; dlg
8B 11                 mov  edx, [ecx]   ; vtable
8B 4D F8              mov  ecx, [ebp-8]
8B 04 02              mov  eax, [edx+eax]
FF D0                 call eax          ; 寄存器间接调用（不能装 CALL_，只能 LoHook）
```

**detach 点规则**：`call eax`（`FF D0`，位于 pattern 偏移 21）之后的下一条指令，即
`site + 0x17`。两版实测吻合：

- 0.2.0.92：`0x039E66 + 0x17 = 0x039E7D` → `8B 4D F8`（`mov ecx,[ebp-8]`）
- 0.2.0.34：`0x03B170 + 0x17 = 0x03B187` → `B9 04 00 00 00`（`mov ecx,4`）

### 4.1 两版 show 之后的行为不同（但钩子不受影响）

0.2.0.92 在 show 返回后清 dialog 字段并读结果族：

```
0x039E7D  8B 4D F8                  mov ecx,[ebp-8]
0x039E80  C7 41 08 00 00 00 00      mov [ecx+8], 0        ← 原 detach 落点（0.2.0.92 专用）
0x039E87  8B 55 F8                  mov edx,[ebp-8]
0x039E8A  C7 42 0C 00 00 00 00      mov [edx+0xC], 0
...      读 [dlg+0x7C] result → 析构 @0x039EB8 → ret 0x18 @0x039EC0
```

0.2.0.34 在 show 返回后取 hero 再调一次 vtable，然后返回 hero：

```
0x03B187  B9 04 00 00 00            mov ecx, 4
0x03B18C  C1 E1 00                  shl ecx, 0
0x03B18F  8B 55 F8                  mov edx,[ebp-8]
0x03B192  8B 44 0A 78               mov eax,[edx+ecx+0x78]   ; hero = dlg+0x78
0x03B196  89 45 BC                  mov [ebp-0x44], eax
0x03B199  6A 01                     push 1
0x03B19B  B9 04 00 00 00            mov ecx, 4
0x03B1A0  6B D1 00                  imul edx, ecx, 0
0x03B1A3  8B 45 F8                  mov eax,[ebp-8]
0x03B1A6  8B 00                     mov eax,[eax]
0x03B1A8  8B 4D F8                  mov ecx,[ebp-8]
0x03B1AB  8B 14 10                  mov edx,[eax+edx]
0x03B1AE  FF D2                     call edx
0x03B1B0  8B 45 BC                  mov eax,[ebp-0x44]
0x03B1B3  8B E5                     mov esp, ebp
0x03B1B5  5D                        pop ebp
0x03B1B6  C2 18 00                  ret 0x18
```

所以**不能沿用「0x039E80 那条 `mov [ecx+8],0`」当 detach 锚点**——旧版没有这条。
统一规则是「`FF D0` 之后」，两版都能挂 LoHook 且 `[ebp-8]` 仍是 dlg，`Local(2)` 照样能读。

## 5. 外框阴影函数：两版逐字节相同

| 版本 | RVA | 说明 |
|------|-----|------|
| 0.2.0.92 | 0x006620 | 旧笔记已记录 |
| 0.2.0.34 | 0x006450 | 2026-10-17 新增 |

特征（26 字节，含一处通配）：

```
55 8B EC 83 EC 10        push ebp; mov ebp,esp; sub esp,0x10
A1 ?? ?? ?? ??           mov eax,[<H3.exe 绘图对象>]   ← 绝对地址，必须通配
8B 48 40                 mov ecx,[eax+0x40]
89 4D FC                 mov [ebp-4],ecx
8B 55 14                 mov edx,[ebp+0x14]            ; h
83 EA 09                 sub edx,9
52 6A 07                 push edx; push 7
```

两版函数体逐条一致（只是起始 RVA 差 0x1D0）。签名 `stdcall(x,y,w,h)`、`ret 0x10`，
内部 4 次 thiscall `0x0044E2C0` 画右/底暗化条。**注意 `0x6992D0` 是 H3.exe 全局**，
不同 exe 版本会变，所以特征里那 4 字节必须通配，否则换 exe 就失效。

## 6. 整窗背景工厂：同一函数，调用约定变了（本轮最重要的坑）

两版都引用同样的三个资源字符串，可据此确认身份：

```
sb%.4u%.4u%.1u%.1u     运行时缓存 key（宽、高、!statusBar、颜色）
DiBoxBck.PCX           底纹平铺源
dialgbox.def           玩家色边框 11 帧
```

| 版本 | RVA | prolog | 调用约定 | ret |
|------|-----|--------|----------|-----|
| 0.2.0.92 | 0x0FADB0 | `55 8B EC 83 EC 40 A1 68 50 15 01 33 C5 89 45 FC 53 8B 5D 08 8B C1 ...` | **fastcall**：x=ECX、y=EDX + 5 栈参 | `ret 0x14` |
| 0.2.0.34 | 0x0E4330 | `55 8B EC 81 EC 94 00 00 00 A1 5C 53 13 01 33 C5 89 45 FC 83 7D 10 40 ...` | **stdcall**：7 个栈参 | `ret 0x1C` |

旧版调用点（0.2.0.34 构造函数 @0x03AE71..0x03AE8E）逐参可见：

```
movsx ecx, byte [eax]   ; color = hero->owner
push ecx                ; 7th: color
push 1                  ; 6th: statusBar
push 0                  ; 5th: itemId
push 0x1CB              ; 4th: height = 459
push 0x195              ; 3rd: width  = 405
push [ebp+0xC]          ; 2nd: y
push [ebp+8]            ; 1st: x
call 0x10E4330
```

ABI 判定用**双证据**，两者都成立才认（否则当作未定位，放弃背景工厂、面板退回简易边框）：

1. 函数内首个 `ret imm16` ∈ {`0x14`, `0x1C`}；
2. `ret == 0x14` 时函数内必须出现 `8B C1`（`mov eax,ecx`，fastcall 从 ECX 取第一参）。

实测：0.2.0.92 → `0x14` + 有 → fastcall5；0.2.0.34 → `0x1C`、无 → stdcall7。
插件侧用两个函数指针分别承接，`WarehouseUiCreateSkin_` 按判定的 ABI 分派。

### 6.1 定位陷阱：`DiBoxBck.PCX` 有 4 个字符串实例

直接在 `.rdata` 里搜第一个 `DiBoxBck.PCX` 再找引用，会命中**别的资源加载器**
（0.2.0.92 命中 0x022EA0、0.2.0.34 命中 0x01FAD0），那些函数里既没有 `ret 0x14/0x1C`
也无法确认 ABI。必须遍历**所有**实例、逐个找 `push imm32` 引用、各自回溯 prolog：

| 版本 | 实例 RVA（全部 4 个） | 真正的引用 | 命中的函数 |
|------|----------------------|-----------|-----------|
| 0.2.0.92 | 0x1402F4 / 0x14DB2C / **0x14DB50** / 0x14DCEC | 0x0FAE70 | 0x0FADB0 |
| 0.2.0.34 | 0x11F4C4 / 0x12FCC4 / **0x12FCE8** / 0x12FEE0 | 0x0E449C | 0x0E4330 |

## 7. 卷轴 DEF 判别全局（SpScrArt 开关）——两版均已定案

这是「法术卷轴(artifactId=1)在背包里画成对应法术图标，还是通用卷轴图」的总开关，
由 HD 配置在启动时写入 `.data`，随后被完整背包构造函数消费。

| | 0.2.0.92 | 0.2.0.34 |
|---|---|---|
| 全局 RVA | **0x157FB8** | **0x1388D0** |
| 构造函数内消费点 | 0x039CE8（ctor @0x039A00） | 0x03B009（ctor @0x03AD80） |
| 配置赋值点 | 0x047F0E `mov [0x1157FB8],edx` | 0x04741A `mov [0x11388D0],eax` |
| 另一背包窗口同款分支 | 0x03AD53 / 0x03B04E / 0x03B13C（函数 0x03AF80） | 0x03C3F6 / 0x03C75E / 0x03C7DF（函数 0x03C690） |
| 引用点总数 | 9 | 8 |

### 7.1 两版判定链逐条同构（0.2.0.92 侧，0.2.0.34 只差寄存器分配）

```
0x039CD8  cmp dword [hero + idx*8 + 0x1D4], 0     ; artifactId
0x039CE0  jl  0x1039DF5                           ; id<0 → 跳过该格
0x039CE6  cmp dword [0x1157FB8], 0                ; ★ 开关
0x039CED  je  0x1039D74                           ; 关 → 普通宝物分支
0x039CFF  cmp dword [hero + idx*8 + 0x1D4], 1     ; artifactId == 1（法术卷轴）
0x039D07  jne 0x1039D74                           ; 不是卷轴 → 普通分支
0x039D15  mov eax, [hero + idx*8 + 0x1D8]         ; subtype = 法术 ID
0x039D1C  mov [ebp-0x54], eax
0x039D2B  push "def.SpScrArt"                     ; 卷轴专用美术
```

0.2.0.34 侧只有两处差异：全局换成 `[0x11388D0]`（0x03B007 处），
subtype 暂存槽是 `[ebp-0x38]`（0x03B03D）。判定顺序、跳转结构完全一致。

### 7.2 运行时实证（2026-10-17，只读 ReadProcessMemory）

游戏跑 5.4（HD_SOD 0.2.0.34，基址 0x03000000）时读进程内存：

```
HD_SOD+0x1388D0  值 = 1     ← 该整合包确实开启了卷轴 SpScrArt 美术
HD_SOD+0x157FB8  值 = 0     ← 新版地址在旧版里是无关数据，证明两版布局不同、不能混用
```

初值方面：`0x1388D0` 落在 `.data` 的未初始化区（该节 VSize 0xFC1288 但 RawSize 仅
0x2A00，文件里无数据），运行时由配置加载代码写入 —— 所以「文件里查初值」查不到，
只能看运行时值，这一点与 `0x157FB8` 相同。

### 7.3 消费口径（插件侧）

`makeIconView` 等价的判定：

```
artifactId < 0                      → 不显示
artifactId == 1 && 开关非 0          → 显示 def.SpScrArt，帧号 = subtype（法术 ID）
否则                                → 显示 artifact.def，帧号 = artifactId
```

插件原先对 0.2.0.34 读不到全局 → 恒 false → 卷轴一律显示 `artifact.def` 第 1 帧
（通用卷轴图）。2026-10-17 补上 0x1388D0 后两版行为一致，不再有降级。
影响面回顾：只影响**原生背包那 64 格**的覆盖图标层；随身空间面板自己的格子本来就
按 artifactId 设帧；悬停提示走 `H3Artifact::GetName()` + 法术名拼接，与 DEF 无关。

## 8. 插件侧落地（H3Space）

新增 `modules/HsodAnchorLocator.hpp`（纯函数、可单测、无 H3API 依赖）：

- `FindPattern`：带掩码（`0xFF` 精确 / `0x00` 通配）的特征搜索，**有歧义即 fail closed**；
- `FindAsciiZ`：NUL 结尾 ASCII 串定位（遍历多实例）；
- `FindFunctionStart`：引用点向前回溯 `55 8B EC`，且要求前一个字节是 `CC/C3/00/90`；
- `FindFirstRetImmediate` / `ContainsMovEaxEcx`：ABI 双证据；
- `LocateAnchors(image, imageSize, imageBase)` → `Anchors{modalSite, modalEnd, shadow,
  skinFactory + abi, scroll}`，并带回候选计数供日志自证；
- `FindKnownProfile` / `MatchesKnownProfile`：已知版本交叉校验表。

门卫（`WarehouseUiStageA.inc.cpp`）三态：
1. 模态锚点定位不到或候选≠1 → 拒绝，日志「未定位到完整背包弹窗模态锚点」；
2. 命中已知版本表 → 定位结果必须与实测表一致，否则判「文件可能被修改」拒绝；
3. 未知版本 → 特征适配放行 + `warn` 提示补表。

StageB 全部改用 `WarehouseUiAnchors_()` 的 RVA；Panel 用双 ABI 分派背景工厂。

单元测试 `tests/warehouse_ui_test.cpp` 新增 10 组（合成最小 PE 映像）：
唯一定位、重复特征拒绝、`int3` 紧跟拒绝、通配绝对地址、空指针、prolog 回溯、
`ret` 立即数判定、ASCII 串、两个版本档案值 + 交叉校验、卷轴全局取值。

## 9. 实机验证（2026-10-17，agent 只做启动与日志判读，操作由用户完成）

**5.4（HD_SOD 原版 0.2.0.34，未替换任何游戏文件）**：

```
随身空间UI: HD_SOD 身份 file=0.2.0.34 product=5.0.0.4 bytes=1325568 sha256=62BC488A39…
随身空间UI: HD_SOD 锚点 modalSite=0x0003B170(候选1) modalEnd=0x0003B187 shadow=0x00006450(候选1) skinFactory=0x000E4330(abi=2 引用2) scroll=0x001388D0 text段=1
随身空间UI: 门卫通过（已知版本 0.2.0.34，锚点与实测表一致）
随身空间UI: 指针 ScrollEnabled = HD_SOD.dll+0x1388D0
随身空间UI: 指针 Shadow = HD_SOD.dll+0x6450
随身空间UI: modal LoHook 已安装 site=0x0003B170 end=0x0003B187（动态定位，非硬编码）
随身空间UI: HD整窗背景 abi=stdcall7 canvas=405x523 stride=812 color=5
随身空间UI: 卷轴DEF开关=1（全局=HD_SOD.dll+0x1388D0 值=1）
随身空间UI: attached dialog=20A7DC10 hero=9 token=1 side=1
随身空间UI: 已展开置顶随身空间层 dialog=20A7DC10
随身空间UI: 已关闭随身空间层，背包恢复原生交互
随身空间UI: detached token=1
```

（补上 0x1388D0 后日志不再出现「卷轴DEF判别全局未定位」warn，卷轴降级已消除。）

**10.09（HD_SOD 0.2.0.92）**：门卫「已知版本 0.2.0.92，锚点与实测表一致」，
`modal LoHook 已安装 site=0x00039E66 end=0x00039E7D`，无回归。

部署产物 `H3Space.dll` SHA256 `B359E9D9926A4C7A0AEBBA3FF12098047AA112F8CD601FE14FDDF2EEB750F94B`，
两个游戏目录一致；构建 0 警告 0 错误；单元测试全绿（含新增 120 断言，卷轴断言已改为 0x1388D0）。

## 10. 待验证 / 后续

- 0.2.0.34 的「卷轴 DEF 全局」已于 2026-10-17 定案为 `0x1388D0`（见第 7 节），降级已消除。
- 旧版面板的**像素级外观**（stdcall 背景工厂产出的 405×523 画布）只验证了尺寸/stride/颜色
  与 attach 流程，未与 0.2.0.92 做逐像素对比；若要宣称外观完全一致需另做截图比对。
- 未来 HD_SOD 版本：先看日志两行（`HD_SOD 锚点` 与 `门卫通过/拒绝`）；适配成功就把新
  `FileVersion` 与三个 RVA 补进 `HsodAnchorLocator.hpp` 的 `FindKnownProfile` 表。
