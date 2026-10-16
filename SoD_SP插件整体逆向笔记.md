# SoD_SP.dll 插件整体逆向笔记（入口/hook 表/接缝/结构）

> 目标版本：**SoD_SP.dll v1.19.4.2**（FileVersion 1.19.4.2，ProductName `SoD_SP`，作者 RoseKavalier，
> SHA256 `EC5A94F0…856D049`，424,960 字节，x86 PE32，ImageBase 0x10000000，**无导出表**）。
> 来源：Ghidra 12.1.2 + PyGhidra 3.1.0 全量反编译（2306 函数）+ 原始字节扫描 +
> 公开源码 `H3Plugins/SoD_SP_Public` 对拍 + `Heroes3Src` 交叉验证。
> 工程与产物：`D:\GitHub\H3\reversing\SOD_SPsrc`（详见该仓库 `docs/` 与 `symbols/`）。
> 范围：插件**整体结构**（入口、hook 框架、配置容器、宿主接缝）。
> 具体功能点（如 ALT 右键信息框）见 `冒险地图ALT右键高级对话框_SoD_SP逆向笔记.md`。

## 1. 启动链（已确认）

```text
CRT 静态初始化表（.rdata VA 0x1005419C）
  └─ 0x100014D0 plugin_start（212 字节）
       ├─ LoadLibraryA("patcher_x86.dll")          [字符串 @0x100598F8]
       ├─ GetProcAddress(..., "_GetPatcherX86@0")  ← 实导出名，不是 "GetPatcher"
       ├─ DAT_100664d8 = (*pFVar1)()               ; Patcher*
       ├─ (*p+0x04)(p,"SoD_SP") != 0 → 错误码 3    ; 实例已注册
       ├─ DAT_100664dc = (*p+0x00)(p,"SoD_SP")     ; PatcherInstance*
       ├─ 0x10005B00 hooks_init
       ├─ (*p+0x34)(p,"HD.OnlineLobby.On") → 若存在则 (*v+0x04)(v, 0)
       │     ← **启动即关闭 HD Mod 在线大厅开关**（互斥）
       └─ DAT_100664ec = (*p+0x30)(p,"SoD_SP.BQ.State", DAT_1006567e != 0)
```

- 错误码 2/3/4 落 `jumptable @ PTR_LAB_100015B0[code]` → 对应弹窗分支（"A previous attempt…" 等）。
- `hooks_init`(0x10005B00) 调用序：`config_load`(0x10025A50) → `get_dll_info`×3 →
  `fixes_init`(0x100050C0) → `improvements_init`(0x1000D430 + 0x1000D0B0) →
  `overflow_init`(0x1000F3F0) → 私有模块（0x10002C20 / 0x100072B0 / 0x100105B0 /
  0x10016B40 / 0x1001BBE0）。
- `config_load` 失败即"全部 hook 关闭"：先 `__set_se_translator`(0x10037010)，
  再取插件路径(0x1003BD60) → `parse_ini`(0x10025120) → `parse_language_file`(0x10024870)。

**取证教训（重要）**：首轮 Ghidra 自动分析**没有**把 0x100014D0（以及 0x100013D0）
识别为函数，插件入口一度缺失于反编译产物（.text 6.9% 未被任何函数覆盖）。
补救方法（可复用）：用①被 `E8/E9` 直接引用的目标 ②函数序言字节特征
（`55 8B EC` / `8B FF 55 8B EC` / `83 EC` / `6A FF 68`…）③CRT 初始化表里的指针
三重证据筛出真实函数起点，再让 Ghidra 建函数并全量重导。结果 2288 → **2306 函数，0 error**，
缺口降到 6.6%。

## 2. patcher_x86 接口（跨项目复用价值最高）

SoD_SP 不链接 patcher 头，全部以虚调用使用。以下偏移**经公开源码 80 处 hook 调用
与反编译实参逐一对拍**（73 处命中）+ 入口函数反编译体实证：

| 对象 | 偏移 | 方法 | 实证 |
|------|------|------|------|
| PatcherInstance | +0x0c | `WriteJmp(from,to)` | 0x464DF1 → 0x464DFB |
| PatcherInstance | +0x18 | `WriteLoHook(addr, func)` | 0x4941FE → 0x100031D0 |
| PatcherInstance | +0x1c | `WriteHiHook(addr, ht, st, ct, func)` | 0x596520,1,1,1 → 0x10005EC0 |
| PatcherInstance | +0x3c | `CreateHiHook(...)`（返回 Hook*） | 0x4AD160（后接 `ApplyInsert(2)`） |
| Hook | +0x18 | `ApplyInsert(zorder)` | `(hook, 2)` |
| Patcher | +0x00 | `CreateInstance(name)` | `"SoD_SP"` |
| Patcher | +0x04 | 实例注册检查（非 0 = 已存在） | `"SoD_SP"` → 错误码 3 |
| Patcher | +0x30 | `CreateVariable(name, initial)` | `"SoD_SP.BQ.State"` |
| Patcher | +0x34 | `FindVariable(name)` | `"HD.Version.Dword"`、`"HD.OnlineLobby.On"` |
| Variable | +0x00 / +0x04 | `GetValue` / `SetValue` | `(*v+0x04)(v, 0)` 关大厅 |

枚举值（对拍定案）：hooktype `CALL_=0` / `SPLICE_=1`；subtype `EXTENDED_=1`；
calltype `STDCALL_=0`（0x4AC790 实证）/ `THISCALL_=1` / `FASTCALL_=2`。

> 未取证的虚表槽位**不要猜**：本笔记只列上述已实证项。

## 3. hook 安装总表（358 条，`symbols/hook_sites.csv`）

| 形态 | 条数 |
|------|------|
| `+0x18` WriteLoHook | 176 |
| `+0x1c` WriteHiHook | 83 |
| `+0x3c` CreateHiHook + ApplyInsert(2) | 1 |
| VirtualProtect 裸写（dword） | 97 |
| VirtualProtect 裸写（指针） | 1 |
| `+0x0c` WriteJmp | 1 |

安装器归属（公开源码对拍）：0x100050C0 = Fixes/AnchorBug/HorizontalScrollbar 系；
0x1000D430 + 0x1000D0B0 = improvements；0x1000F3F0 = overflow；0x10005B00 = hooks_init 本体。

**两个特殊挂接点（确认）**：

- `0x4AD160`（BattleRNG）**同址两层**：improvements_init 用 WriteHiHook 挂
  `FUN_1000A280`，hooks_init 另用 CreateHiHook+ApplyInsert(2) 挂 `FUN_1000DDC0`
  （链在外层）。公开源码只写了一层 → 1.19.4.2 新增第二层（语义待验证）。
- `0x4B352F`（BerserkAI）**条件安装**：先读宿主字节 `DAT_004B352F`，若已等于 `0xE9`
  （即已是 JMP）就跳过，避免与 HD_SOD.dll 同址补丁冲突 → 跨插件共址防护写法。

另：公开源码 80 个 hook 地址中 **6 个在 1.19.4.2 无任何字面安装**
（0x59BFFD / 0x59D3BA / 0x59D7B6 / 0x4E59F1 / 0x4E5B24 / 0x59C01C；
同组的 0x59BFBE / 0x59C002 正常）→ 推断按计算地址安装或已改实现，**待验证**。

## 4. 配置容器（ini → 运行态）

| 项 | 事实 |
|----|------|
| 键指针表 | `.rdata` VA **0x10059BB0**，40 个 `char*`（Ghidra 标签 `PTR_s_DisablePlague_10059bb0`） |
| 索引方式 | `(&PTR_s_DisablePlague_10059bb0)[index]`，下标即选项枚举序 |
| 遍历者 | `parse_ini` 0x10025120（1396B）、`ini_walk_keys_2` 0x100257C0（549B） |
| ini 文件 | `SoD_SP.ini`；同函数内还引用 `CheckUpdate`/`UpdateAddress`/`DownloadAddress` |
| 语言 | `SoD_SPLanguage` → `lang/<lng>.json`（公开源码 5 语种：deu/eng/gre/pol/rus） |
| 选项落点 | `DAT_100656xx` 区（`DAT_1006567e` = BattleQueuePanel 开关，被 6 处读取判定） |
| 读 ini 封装 | `0x1003AC80` ini_read_string（经**游戏 API 0x61CF80**）、`0x1003AD80` ini_read_int |
| 表外键 | 12 个（`SoD_SPLanguage`/`LogData`/`Development`/`CheckUpdate`/`UpdateAddress`/`DownloadAddress` + 各 `[section]` 显示项） |

40 键全表（下标 0..39）：`DisablePlague, DisableDoubleGrowth, DisableWeeklyGrowth,
FixTurretBug, FixCreaturesOverflow, FixResourcesOverflow, FixPrimaryOverflow,
CombatObstacles, CreaturesSplit, OriginalRNG, BerserkAI, ResourcesFormat,
CombatRMBTextbox, CombatCoordinates, ShowHitPoints, ShowMoveSequence, TurboAnimation,
AICheats, SpellDetails, AdventureCoordinates, RealKills, QuickSpellPanel,
BattleQueuePanel, BattleQueueText, AdmiralBugFix, MovementBugs, CloneBug, Earthquake,
EventBug, AIMinimap, Vanish, AnchorBug, FastBattleBugs, NagaBank, Hireable, QCoverflow,
AINecromancy, HeroFusion, AIMagicMirror, EnchantersFix`。

## 5. 宿主接缝（SoD_SP → Heroes3.exe）

**调用形态（实测排除法确认）**：游戏功能调用是
`mov eax/ecx/edx/ebx/esi/edi, <gameVA>`（`B8..BF`）+ 同寄存器间接调用 `FF D0..D7`。
**不是** `E8 rel32`（全库仅 1 处），**不是** `FF 15 [imm32]`（共 262 处，**全部**是
DLL 自身 IAT，游戏区间命中 0）。共 **145 个目标 / 987 处调用点**（`symbols/game_seams.csv`）。

**交叉验证**：与 `Heroes3Src/symbols/ghidra_functions.csv`（11521 函数）做包含判定，
**143/145（98.6%）目标精确落在其函数起点（偏移 +0x0）**。

头号接缝：

| 游戏地址 | 调用点 | 身份 |
|---------|-------|------|
| 0x004CE950 | 92 | FUN_004ce950 |
| 0x00617492 | 63 | **operator_new** |
| 0x004040F0 | 52 | FUN_004040f0 |
| 0x0060B0F0 | 51 | FUN_0060b0f0 |
| 0x004B51F0 / 0x005F4B90 / 0x004F6C00 | 46 / 38 / 36 | 各 FUN_ |
| 0x004B56F0 / 0x0041B2A0 / 0x004317D0 / 0x005FF270 | 33/32/29/29 | 含控件消息 |
| 0x00404180 | 28 | 数值转换（ini_read_int 内） |
| 0x0047BE90 | 26 | 精灵/位图绘制（Heroes3Src 标 `FUN_47be90_needs_name`） |
| 0x0061ACD0 / 0x0061B7E0 | 25 / 18 | **`_strlen` / `_memset`** |

**结论**：SoD_SP **直接复用宿主 exe 内的 CRT**（`operator_new`+`_strlen`+`_memset` 共 106 处），
且 145 个接缝全为硬编码绝对地址、无导出表解析 → 这就是插件必须与 HD Mod/游戏版本
严格配套的结构性原因。装钩子走 patcher 虚调用，调功能走绝对地址直呼，两套并存。

## 6. 结构校准

| 全局 | 类型 | 赋值处 | 说明 |
|------|------|--------|------|
| `DAT_100664D8` | `Patcher*` | plugin_start | `_GetPatcherX86@0` 返回值 |
| `DAT_100664DC` | `PatcherInstance*` | plugin_start | 全库 260 处 hook 经它调用 |
| `DAT_100664EC` | `Variable*` | plugin_start | `SoD_SP.BQ.State`，跨插件共享 |
| `DAT_1006565C` | `u32` | hooks_init | `HD.Version.Dword`，**版本门控判据** |
| `DAT_10065728/44/60` | `DllInfo` ×3 | hooks_init | `_hd3_.dll` / `HD_TC2.dll` / `HD_SOD.dll`，**步长 0x1C** |
| `DAT_1006567E` | `u8` | ini 解析 | BattleQueuePanel 开关 |

**版本门控（确认）**：`improvements_init` 内

```c
if (DAT_1006565c < 0x4c63ec) {          // 仅旧版本才挂这些 hook
    WriteHiHook(0x4AC2D6, CALL_, THISCALL_, HH_CreatureSplit);
    WriteLoHook(0x61842C, OriginalRng);
    WriteLoHook(0x50C7C0, CombatObstacles);
    ...
}
```

即 **SoD_SP 的功能集在运行期由 HD Mod 版本决定**（阈值 `0x4C63EC`，变量由 HD 侧创建），
不是编译期固定表。阈值物理含义（尺寸/时间戳？）**待验证**。

## 7. 命名成果（81 个函数，`symbols/rename_candidates.csv`）

证据分级：A=公开源码回调名按 hook 地址对拍（约 66 条，high）；B=入口链定案；
C=字符串锚点（mid）；D=冲突覆盖。代表：

`plugin_start`(0x100014D0)、`hooks_init`(0x10005B00)、`load_config`(0x10025A50)、
`parse_ini`(0x10025120)、`parse_language_file`(0x10024870)、`fixes_init`(0x100050C0)、
`improvements_init`(0x1000D430)、`improvements_growth_init`(0x1000D0B0)、
`overflow_init`(0x1000F3F0)、`log_write_debug_txt`(0x10032C00)、
`textcolor_bridge_init`(0x1000DC30，桥 H3.TextColor.dll)、`get_dll_info`(0x10036500)、
`HH_FixObstacleAnchorBug`(0x10002F20→0x465E70)、`RepositionAnchorDef`(0x100031D0→0x4941FE/0x494523)、
`HH_HrztlScrollbarHotkey`(0x10005EC0→0x596520)、`HH_HScrollbarRight`(0x10005F50→0x5965C3)、
`VerifyMonsterCount`(0x1000CF40)、`WeeklyGrowthSetup`(0x1000CFE0)、
`HH_Whirlpool_OF`(0x1000F130→0x4AC790，STDCALL)、`AIberserk1`(0x1000C6A0)、
`HH_BattleRNG`(0x1000A280)/`HH_BattleRNG_layer2`(0x1000DDC0)。

## 8. 待验证

1. 6 个公开源码 hook 地址在 1.19.4.2 的字面缺席原因（0x59BFFD 等）。
2. `DAT_1006565c` 阈值 `0x4C63EC` 的物理含义（需 HD Mod 侧写入点对照）。
3. 接缝 0x69CCFC（3 处）、0x677708（1 处）未落在 Heroes3Src 任何函数内 → 实机断点确认。
4. `DllInfo` 结构 7 个字段的完整语义（仅确证前若干字段写入顺序）。
5. 同址双层 `0x4AD160` 第二层的具体作用。
6. 私有模块（battle queue 面板 UI 链、versions/update、hotkeys）未逐函数还原。

## 9. 复现与取证产物

- 仓库：`D:\GitHub\H3\reversing\SOD_SPsrc`（远端 gogs `Hero3/SOD_SPsrc`）
- `docs/`：体检报告、方案、计划、功能定位、模块划分、接缝清单、结构校准
- `symbols/`：`hook_sites.csv`(358)、`option_keys.csv`(40)、`modules.csv`(2306)、
  `rename_candidates.csv`(81)、`game_seams.csv`(145)
- `src/decompiled/`：`all_functions.c`（原始，2306 函数）+ `all_functions_named.c`（命名版）
- `src/hd/`：可编译重建层（入口/patcher/安装器/4 模块 + `HookTable.hpp`/`OptionKeys.hpp`）
- 编译验证：`tests/compile_vs2026.bat`（VS2026 MSVC 14.51, x86, `/std:c++20`）
  实跑 **exit code 0**，并打印 hook 表自检（358 站点 / 40 键）
- Ghidra 脚本：`ghidra/{export_sp,decompile_sp,gapfill_sp}.py`
