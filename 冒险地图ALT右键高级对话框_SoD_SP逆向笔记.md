# 冒险地图 ALT+右键「查看信息」归属与实现位置逆向笔记

记录日期：2026-10-16（当日多次追加）。**结论已从"归属已定、分支未定"推进到"实现已定位到函数级"**。

## 0. 一句话结论

- **归属：`SoD_SP.dll`（F12 插件）实现，HD Mod 无关。**
- **宝屋/龙国的信息内容由 `SoD_SP.dll` 的 `FUN_10020ba0 @ 0x10020BA0` 构造**（按"生物宝屋 400 字节定义表"取守卫/奖励数据）。
- **入口接管点**：SoD_SP 把游戏 `Heroes3 HD.exe` 内 `0x40A6DD` 的 5 字节改成 `E9` 相对跳转，落到自己的 trampoline `0x10022A20` → 分派器 `FUN_10022350 @ 0x10022350`；由 `FUN_10021d00 @ 0x10021D00` 判 ALT。
- 改造落点在 `SoD_SP.dll`，**不是游戏 exe，也不是 HD Mod**。

映像基址：`Heroes3 HD.exe` = `0x400000`；`SoD_SP.dll` = `0x10000000`；`HD_SOD.dll` = `0x1000000`。

## 1. 用户问题

「宝屋、龙国上 ALT+右键查看信息的功能是哪里实现的（主要看是 HD Mod 还是 SOD_SP），准备对其进行改造。」

## 2. 归属证据

| 证据 | 内容 |
|---|---|
| 插件自带 Changelog | `...\_HD3_Data\Packs\F12插件\Changelog.txt:279`「[+] Added Advanced Dialogs to map adventure (ALT + RMB)」，:280「Players can still use normal RMB dialogs if ALT is not pressed.」，:281「can be disabled by mapmakers using Unleashed mapeditor」 |
| 代码链（决定性） | SoD_SP 在游戏 `0x40A6DD` 写入 `E9` 跳转 → 自己的分派器按对象类型分发；分派器入口用 "ALT 按住" 谓词门控；`DRAGON_UTOPIA` / `CREATURE_BANK` 两类都有专门 case |
| 门控口诀 | 非 ALT 时返回 1 → 补回原版两条指令继续原版路径；ALT 时返回 0 且把返回地址改写成 `0x40A7B6` → 走"高级对话框"分支。与 Changelog :280 的"不按 ALT 仍是普通右键"完全对应 |
| HD Mod 侧 | `HD_SOD.dll` 虽也检查 ALT（自备 `bool FUN_01005750(vk)` 包装，被 0x12 调用数十处），也挂钩游戏 `0x5D3640` 两处，但**对本题对象信息链零命中**：`0x5D5010`/`0x5D460F`/`0x5D45FD` 均 0 命中；HD_SOD 自己的 `0x5D3640` 回调 `FUN_01051d80` 只特判 `[event+0]=0x200,[+1]=0xD,[+2]=0x9A` 且 `[obj+300]==0` |

## 3. 接线全链（按执行顺序）

### 3.1 游戏侧被接管的位置

补丁点 `0x40A6DD`，位于 `FUN_0040a530 @ 0x40A530`（1455 字节，`Heroes3Src` 符号表；分类 `game_system;video_graphics`，被 `0x409740` 调用）。**该函数同时含已知名的 SoD_SP 钩子点 `0x40A716`（改名候选 `HH_HeroRmbBiography`），可佐证它就是"冒险地图对象右键信息"处理函数。**

原版字节（5 字节，正好是 patch 长度）：

```
0040A6DD: 8B 4F 1E   mov ecx,dword ptr [edi+1Eh]   ; ecx = 对象类型（[edi+0x1E]）
0040A6E0: 8B 07      mov eax,dword ptr [edi]         ; eax = 对象 ID
0040A6E2:            ; ← 原版继续点
```

patch 前紧邻的原版英雄传记捷径（保留不动）：

```
0040A6D6: B9 22 00 00 00  mov ecx,22h      ; 0x22 = 34 = HERO
0040A6DB: EB 05           jmp 0040A6E2      ; 直接跳到 patch 之后的继续点
```

### 3.2 SoD_SP 安装器（0x10005D49 起，同一函数内还有大量其它钩子）

```
10005D4E: push 10022A70h
10005D5B: push 4762F0h
10005D61: call [ecx+1Ch]      ; WriteHiHook(0x4762F0, 1,1,1, FUN_10022a70)

10005D69: push 10022BB0h
10005D6E: push 2              ; subtype = 2
10005D76: push 4E1A70h
10005D7C: call [ecx+1Ch]      ; WriteHiHook(0x4E1A70, 2,1,1, FUN_10022bb0)

10005D90: push 40A6DDh / push 5 / push 80h    ; VirtualProtect(0x40A6DD, 5, 0x80, &old)
10005DBC: mov eax,10022A20h
10005DC1: mov byte ptr [0040A6DDh],0E9h       ; 写 JMP 操作码
10005DC8: sub eax,40A6E2h
10005DCD: mov [0040A6DEh],eax                 ; rel32 = 0x10022A20 - (0x40A6DD+5)

10005DFC: push 10022B20h
10005E09: push 530DB8h
10005E0F: call [ecx+1Ch]      ; WriteHiHook(0x530DB8, 1,1,0, FUN_10022b20)
```

（同一段邻近还有 `push 10022BF0h` / `push 4B8D93h` 一对，属"待验证"，未逐字节核对槽位。）

### 3.3 trampoline `0x10022A20`（SoD_SP 反汇编逐行）

```
10022A20: 54              push esp              ; 传当前 esp 作为帧指针
10022A21: 9C              pushfd
10022A22: 68 E2 A6 40 00 push 40A6E2h          ; 回程地址槽 = 原版继续点
10022A27: 57 56 55       push edi/esi/ebp
10022A2A: 36 FF 74 24 14 push dword ptr ss:[esp+14h]
10022A2F: 53 52 51 50    push ebx/edx/ecx/eax
10022A33: 54              push esp
10022A34: E8 17 F9 FF FF call 10022350          ; ← 唯一调用点：分派器
10022A39: 85 C0           test eax,eax
10022A3B..42:             pop eax/ecx/edx/ebx/ebp/ebp/esi/edi
10022A43: 8F 05 FC 8D 06 10 pop dword ptr ds:[10068DFCh]   ; 取回回程地址
10022A49: 75 08           jne 10022A53           ; 返回非 0 → 补回原指令
10022A4B: 9D              popfd
10022A4C: 36 8B 64 24 E8 mov esp,dword ptr ss:[esp-18h]
10022A51: EB 0D           jmp 10022A60
10022A53: 9D              popfd
10022A54: 36 8B 64 24 E8 mov esp,dword ptr ss:[esp-18h]
10022A59: 3E 8B 4F 1E    mov ecx,dword ptr ds:[edi+1Eh]   ; 原版被覆盖的两条
10022A5D: 3E 8B 07       mov eax,dword ptr ds:[edi]
10022A60: FF 25 FC 8D 06 10 jmp dword ptr ds:[10068DFCh]   ; 回 0x40A6E2（或改写后的 0x40A7B6）
```

栈帧布局（分派器 `param_1` 指向的帧）：`[+0]=eax [+4]=ecx [+8]=edx [+0xC]=ebx [+0x10]=原[esp+14h] [+0x14]=ebp [+0x18]=esi [+0x1C]=edi [+0x20]=回程地址槽`。**所以 `param_1+0x1C` 可取回游戏的 `edi`（地图对象指针）。**

### 3.4 分派器 `FUN_10022350 @ 0x10022350`（1285 字节）

```c
uVar3 = __set_se_translator(seh_translator);
iVar4 = FUN_10021d00();                 // ← ALT 谓词
if (iVar4 == 0) goto switchD_1002244d_caseD_8;   // 非 ALT/不满足 → 原版继续
puVar1 = *(uint **)(param_1 + 0x1c);            // 帧里取回游戏 edi = 地图对象
puVar5 = (*(code *)0x4fd0f0)();                 // 对象/格位解析
if (puVar5 == 0) { if (*(short*)((int)puVar1 + 0x1e) != 0x1a) goto caseD_8; ... }
...
local_1c = (int)*(short *)((int)puVar1 + 0x1e);  // 对象类型（= 原版 mov ecx,[edi+1Eh]）
local_18 = *(short *)((int)puVar5 + 0x22);       // 子类型
switch(local_1c) { ... }
```

返回约定：

- `switchD_1002244d_caseD_8:` → `return 1;`（**原版继续**：trampoline 补回 `mov ecx,[edi+1Eh]; mov eax,[edi]`，回 `0x40A6E2`）
- 各 ALT case 与 `caseD_10` → `uVar3 = FUN_1002286d(); return uVar3;`（**返回 0 + 改写返回地址到 0x40A7B6**）

`FUN_1002286d @ 0x1002286d`（47 字节）本体：

```c
*(undefined4 *)(*(int *)(unaff_EBP + 8) + 0x20) = 0x40a7b6;  // 把回程地址槽改成游戏 0x40A7B6
*(undefined4 *)(unaff_EBP + -4) = 0xffffffff;
return 0;
```

→ 即 **SoD_SP 让游戏从 `0x40A7B6`（`FUN_0040a530` 内另一条继续路径 = 高级对话框路径）恢复执行**，而不是原版的 `0x40A6E2`。

### 3.5 ALT 门控 `FUN_10021d00 @ 0x10021D00`（38 字节，唯一调用者就是 `FUN_10022350`）

```c
if ((DAT_10065650 == 0x20) && (DAT_100656c2 == '\0')) {
    cVar1 = (*(code *)0x4ce950)();       // 游戏谓词：活跃/非模态
    if (cVar1 == '\0') return 1;         // → 启用高级对话框
}
return 0;
```

- `DAT_10065650` = SoD_SP 自持修饰键镜像：**`== 0x20` 表示 ALT 按住**（另有 `& 4` = CTRL 的用法，见 `HH_HeroRmbBiography`）。
- `DAT_100656c2` = 屏蔽位（非 0 时不启用）。
- 置位点：`FUN_10006250`（HiHook 游戏 `0x4089DC`，属 `FUN_00408710`）里 `case 0x20:` 且 `param_3[1] == 0x38` 时 `DAT_10065650 = 0x20;`。该 case 之后还会取 `*(uint *)(param_2 + 0xe8)`（光标格）并调 `(*(code *)0x412b30)`/`(*(code *)0x40b0b0)`。
- 全库仅此一处写入 `0x20`，**清零点在静态反编译里看不到**（疑经别名/结构体写回），属"待验证（需动态确认清除时机）"。

### 3.6 次要钩子（同一功能族的其它接管点）

| 游戏地址 | 类型 | SoD_SP 回调 | 行为 |
|---|---|---|---|
| `0x4762F0` | HiHook(1,1,1) | `FUN_10022a70 @0x10022A70` | ALT 且 `对象类型-0xFC < 2`（0xFC/0xFD）且 `*(int*)(map+0x4FDC+type*4) != 0` → `FUN_10021d30()`，**返回 0 不调原版**；否则调原版并透传 |
| `0x4E1A70` | HiHook(subtype=2) | `FUN_10022bb0 @0x10022BB0` | 同族处理 |
| `0x530DB8` | HiHook(1,1,0) | `FUN_10022b20 @0x10022B20` | ALT 命中时把原版第 2 个参数强制成 `3`（否则透传 `param_4`） |
| `0x40A6DD` | **内联 JMP patch** | trampoline `0x10022A20` → `FUN_10022350` | 本题主线 |

## 4. 对象类型 → 处理函数对照（`FUN_10022350` 的 case 表）

常量口径：`H3API\include\h3api\H3Constants\H3CstObjects.hpp` 的 `eObjectTypes`；宝屋子用 `NCrBank::eCrBank`。

| case | 对象类型常量 | 处理函数 | 备注 |
|---|---|---|---|
| 0x05 | `ARTIFACT`=5 | `FUN_1001cf50` | 宝物表 stride 0x20 |
| 0x06 | `PANDORAS_BOX`=6 | `FUN_1001e6d0(...,'\0')` | |
| 0x07 | `BLACK_MARKET`=7 | `FUN_1001cd70` | |
| 0x0C | `CAMPFIRE`=12 | `FUN_1001d430` | |
| **0x10** | **`CREATURE_BANK`=16** | → `caseD_10`：**`FUN_10020ba0(obj, iVar6=子类型)`** | **宝屋（子类型=宝屋类型 1..10）** |
| 0x11 / 0x14 | `CREATURE_GENERATOR1`=17 / `CREATURE_GENERATOR4`=20 | `FUN_1001dca0` | 生物生成器 |
| 0x16 | `CORPSE`=22 | `FUN_1001d550` | |
| **0x18** | **`DERELICT_SHIP`=24** | → `caseD_10`：**`FUN_10020ba0(obj, 8)`** | 8 = `eCrBank::DERELICT_SHIP` |
| **0x19** | **`DRAGON_UTOPIA`=25** | **`FUN_10020ba0(obj, 10)`** | **龙国；10 = `eCrBank::DRAGON_UTOPIA`** |
| 0x1A | `EVENT`=26 | `FUN_1001e6d0(...,'\x01')` | 事件 |
| 0x1D | `FLOTSAM`=29 | `FUN_1001d780` | |
| 0x22 | `HERO`=34 | `(*(code*)0x4317d0)(*obj)` 解析英雄 → `FUN_10021d30()` | 英雄 |
| 0x27 | `LEAN_TO`=39 | `FUN_1001d8e0` | |
| 0x35 | `MINE`=53 | `FUN_1001da20(obj, FUN_10039820(_DAT_0069ccfc))` | 矿场 |
| 0x36 | `MONSTER`=54 | `FUN_10020580(...)` | 野外兵 |
| 0x37 | `MYSTICAL_GARDEN`=55 | `FUN_1001f3c0` | 神秘花园 |
| 0x3B / 0x5B | | `FUN_1001f510` | |
| 0x3E | | 置 `*(int*)(_DAT_006992d0+0x38) = -1` → `FUN_10021d30()` | |
| 0x3F | `PYRAMID`=63 | `FUN_10020380` | 金字塔 |
| 0x4E / 0x4F | | `FUN_1001f600` / `FUN_1001d0e0` | |
| 0x51 / 0x52 | | `FUN_1001f6f0` / `FUN_1001f840` | |
| 0x53 | | `cVar7='\x01'` → `FUN_10020fb0` | |
| **0x54** | **`CRYPT`=84** | **`FUN_10020ba0(obj, 9)`** | 9 = `eCrBank::CRYPT` |
| **0x55** | **`SHIPWRECK`=85** | **`FUN_10020ba0(obj, 7)`** | 7 = `eCrBank::SHIPWRECK` |
| 0x56 | `SHIPWRECK_SURVIVOR`=86 | `FUN_1001f990` | |
| 0x58 / 0x59 / 0x5A | | `FUN_1001d690` | |
| 0x5D | | `FUN_1001d290` | |
| 0x5F | | `FUN_10020890` + `(*(code*)0x5d82c0)` + `FUN_10020a30` | |
| 0x62 | | `FUN_1001dea0` | |
| 0x65 / 0x66 | | `FUN_1001fa80` / `FUN_1001fbc0` | |
| 0x68 / 0x69 / 0x6C / 0x6D / 0x70 / 0x71 | | `FUN_1001cc40` / `FUN_1001fd20` / `FUN_1001fe80` / `FUN_1001ffc0` / `FUN_10020100` / `FUN_10020240` | |
| 0xD7 | | `cVar7='\0'` → `FUN_10020fb0` | |

**宝屋/龙国两条路径都汇到 `FUN_10020ba0`**，这就是"改内容"的主落点。

## 5. 宝屋/龙国信息构造器 `FUN_10020ba0 @ 0x10020BA0`（1031 字节）

```c
void __fastcall FUN_10020ba0(uint *param_1 /*对象*/, int param_2 /*宝屋类型 eCrBank*/)
{
  piVar10 = (int *)(param_2 * 400 + 4 + _DAT_0047a3c2);   // ← 400 字节步长的生物宝屋定义表
  piVar9 = (int *)*piVar10;
  if (piVar9 != (int *)0x0) piVar10 = piVar9;             // 守军/奖励指针
  local_18 = piVar10;
  if ((*param_1 & 0x2000000) == 0) {                      // 未清空（H3MapitemCreatureBank::taken = bit25）
    iVar11 = (*param_1 >> 0xd & 0xfff) * 0x6c + *(int *)(_DAT_00699538 + 0x4e3dc);
    local_20 = iVar11;                                    // H3Main::creatureBanks[id]（H3CreatureBank 0x6C：守军+资源奖励+宝物向量）；id = 位域 bits13..24
    local_24 = (*(code *)0x44a990)();
    puVar8 = *(uint **)(iVar11 + 0x60);
    uVar6 = (uint)((int)*(uint **)(iVar11 + 100) + (3 - (int)puVar8)) >> 2;   // 该格对象链表长度
    ... 逐条汇总（内联 min/max 累加 _DAT_1005d570.. 系列表）...
  }
```

关键事实：

- `param_2 * 400` = **生物宝屋定义表**（400 字节/条，H3API 的 `H3CreatureBankTable` 尺寸一致），基址 `_DAT_0047a3c2` 相对。
- 对象标志 `*obj & 0x2000000` = 已访问位（访问过则不列守军/奖励）。
- 地图格位步长 `0x6C`，从 `_DAT_00699538 + 0x4e3dc` 取基址；`格位+0x60`/`格位+100` 是该格对象链表的两个指针（遍历其上的对象）。
- 后半段（约 900 字节）构造的具体字段/文本**尚未逐行读完**，属"待验证"。

## 6. 改造指引（面向"准备对其进行改造"）

| 想改什么 | 落点 |
|---|---|
| 宝屋/龙国弹窗**内容**（守军、奖励、统计口径） | `SoD_SP.dll` `FUN_10020ba0 @ 0x10020BA0`（宝屋/龙国/沉船/幽灵船/墓穴共用） |
| 接管**哪些对象类型** | `FUN_10022350 @ 0x10022350` 的 `switch(local_1c)`（跳转表 `switchD_1002244d`）；宝屋共用分支 `caseD_10` |
| **ALT 门控**（改成别的键/加开关） | `FUN_10021d00 @ 0x10021D00`；键位来源 `FUN_10006250`（游戏 `0x4089DC`）里 `DAT_10065650 = 0x20` |
| 让**原版**恢复处理（关掉高级对话框） | 让分派器返回 1（走 `caseD_8`），或让 `DAT_100656c2 != 0` |
| 接管点本身（绕过 SoD_SP） | 游戏 `0x40A6DD`（`FUN_0040a530` 内，5 字节）；同一函数另有 `0x40A716` 已被 SoD_SP 占用 |

注意：

- `SoD_SP.dll` 是**第三方 F12 插件**，直接改它需重打包；若要"叠加自研逻辑"，更稳的是自己挂钩同一个游戏点或 Hook `FUN_10020ba0`，但必须处理加载顺序与版本差异（本机 `SoD_SP.dll` 424960 字节、Changelog 到 `v1.19.4.2`）。
- 若改用自研插件接管同一 Hook 入口，**必须先按 `h3-plugin-crash-guard` 技能规程做四层防御**（原版调用在 `__try` 外、恰好一次）。
- 本功能**没有 ini 开关、默认常开**（本机 `SoD_SP.ini` 269 行 40 个选项里无 ADV/DIALOG 相关键），只能改代码/让地图制作者用 Unleashed 关。

## 7. 勘误（本笔记早期结论已作废，留档）

1. 初稿把 `push 41h` 误写成 VK_SPACE。**0x41 = 键 'A'**（VK_SPACE = 0x20）。
2. 初稿判断"`0x10002A10` handler 就是 ALT+RMB 目标"。**错**：它只处理地形小物件（0x73..0x79、0x8C..0x92、0x7B、0x7D）且读的是 'A' 键，与宝屋/龙国无关。
3. 初稿判断"HD_SOD 侧零命中 ALT，故与 HD Mod 无关"。**前提有误**：HD_SOD 用自备包装 `FUN_01005750(vk)` 查 ALT(0x12) 数十处（我只 grep 了 `GetKeyState(` 所以漏了），并且确实挂钩了游戏 `0x5D3640` 两次（回调 `FUN_01051d80`、`FUN_010e6fb0`）。但**结论仍成立**：HD_SOD 对本题对象信息链（`0x40A6DD`/`0x40A7B6`/`FUN_0040a530`）零命中，PTR 链与功能描述全部落在 SoD_SP。
4. 初稿判断"分支未定、可能在另 106 个钩子里或 UNLEASHED/NCE 数据路径"。**错**：它不在 `hook_sites.csv` 里，因为它是**内联 JMP patch**（不是 patcher 的 LoHook/HiHook），所以按钩子表穷举永远找不到——这是本次的关键教训。
5. 初稿曾把 `0x5D5010` 认作"原版弹出右键信息窗口"。**错**：`FUN_005d5010` 是部队交换/招募状态机（`switch(模式 0..9)`，操作 `+0x124/+0x134/+0x300` 的交换状态与 `+0x2C` 槽位）。原版右键对象信息窗实为 `FUN_00413720 @0x413720`，见 §10。
6. 初稿 §5 曾把 `FUN_10020ba0` 里 `& 0x2000000` 注为"已访问位"。**更正**：是 `H3MapitemCreatureBank::taken`（已清空）位；"哪些玩家来过"是 bits 5..12 的 `visited:8` 位域（`FUN_0040d350` 用 `(*mapItem>>5) & (1<<宝屋子)` 查询）。

## 8. 取证产物与口径

- `D:\logs\dsh\scripts\h3-altinfo\`：`game_exe_disasm.txt`（856131 行）、`sod_sp_disasm.txt`、`hd_sod`/`sod_sp` 的 `*_imports.txt`、`*_strings.txt`、自写 PE IAT 解析器（修正后：`USER32!GetKeyState` IAT_VA = `0x10054138`；游戏 exe 侧 IAT_VA = `0x63A294`）。
- 反编译源：`reversing\SOD_SPsrc`（2306 函数）、`reversing\Heroes3Src`（exe）、`reversing\HD_SODSrc`（HD_SOD.dll）。
- **坑**：`Heroes3Src\symbols\ghidra_functions.csv` 是**制表符分隔**（`address<TAB>name<TAB>size<TAB>isExternal<TAB>callingConvention`），按逗号解析会得到 0 条。
- **坑**：Ghidra 会把格式化字符串**内联**进调用（如 `FUN_10037800(&DAT_00697428,"{%s:} %s      {%s:} %d      {%s:} %d")`），按字符串表地址 grep 会 0 命中，要搜字面量。

## 9. 待验证

- `FUN_10020ba0` 后半段（约 900 字节）逐行内容：具体输出的字段、单位、是否含奖励金币/生物数。
- `DAT_10065650` 的清零时机（静态只见一处写 `0x20`）。
- 安装器里邻近的 `push 10022BF0h` / `push 4B8D93h` 一对（槽位/语义未逐字节核对）。
- 实机验证：ALT+RMB 宝屋/龙国 的实际弹窗内容是否与 `FUN_10020ba0` 输出一一对应（游戏内测试由用户执行）。
- 事件[3]（+0xC）`0x200` 位的极性与触发时序（§10.4：按三处用法反推为"右键按住"；可再读 `FUN_00602930` 事件构造或实机确认）。
- `FUN_0040d350` 中 `FUN_00449370()` / `FUN_0040ab40(1)` 分支的确切语义（"访问过"时拼接的守军描述具体内容）。
- `0x4F6C00` 的 `type=4`（原版右键信息窗所用的值）与 H3API `eButtonType` 枚举的对应关系（§10.6）。
- `H3DlgTextPcx` 的两处 vtable：实测窗口写 `0x63DB40`，而 H3API `_H3API_VTABLE_(H3DlgTextPcx)` 记 `0x642DF8`；二者关系（派生/双入口）待核。
- 原版信息窗背景 PCX 的具体资源名（`0x48FA80` 内未见串引用，疑由 `H3DlgTextPcx` 基类默认底图或 `type` 决定）。

## 10. 原版右键信息弹窗（2026-10-16 下午追加；用户改问「原版在宝屋/龙国上点右键」）

**结论：原版确实有弹窗**——按住右键时在对象旁弹出信息窗、松开后关闭。SoD_SP 的 ALT 高级对话框**就是替换它**：ALT 命中时跳过原版显示调用（`0x40A7B6` = `call 0x413720` 之后的收尾，见 §3.4），因此二者互斥。

### 10.1 原版完整链路（Heroes3Src，含改名 pass 的函数名）

```
AdventureMap_AI_Main @ 0x408710（冒险地图事件分派器；SoD_SP 在此挂钩 0x4089AB/0x4089DC 置 ALT 标志）
  event[0]==0x200 (eMsgCommand::MOUSE_BUTTON) → 按 event[1] (eMsgSubtype) 分派：
    0x0C → AdventureMap_HandleClick      @ 0x409740
    0x0D 且 !(event[3]&0x200) → AdventureMap_HandleRightClick @ 0x4099D0
    0x0E 且  (event[3]&0x200) → AdventureMap_HandleDrag       @ 0x402E70
  HandleClick / HandleRightClick 内部再按 event[2] 分派：
    case 0 / 0x25 → FUN_0040a530 @ 0x40A530   ← SoD_SP 打补丁的函数（§3.1）
    case 1        → FUN_0040a020 @ 0x40A020   ← 收起提示窗（见 10.3）
FUN_0040a530 右键分支：if ((event+0xC) & 0x200) → 取光标下地图对象（edi：类型 +0x1E / 子类型 +0x22）
  → switch(对象类型)：0x21/0x22/0x36/0x62 走专用窗口；default → call 0x413720  ← SoD_SP ALT 时跳过的就是这个 call
FUN_00413720 @ 0x413720（9187B，原版对象信息文本构造器）
  → 按对象类型 switch（约 60 个 case），文本写入全局缓冲 DAT_00697428
  → 尾部：FUN_004f6930(&size) 量文本尺寸；x,y ← 对象格坐标×0x20，
         钳制 x∈[8, 600-w]、y∈[8, 0x228-h]（0x228=552）
  → FUN_004f6c00(x,y,0xffffffff,0,0xffffffff,0,0xffffffff,0,0xffffffff,0)  ← 弹窗（贴对象旁）
```

### 10.2 宝屋/龙国在原版分派器里的 case（与 SoD_SP 同一套宝屋子编号）

```c
case 0x10: FUN_0040d350((int)*(short*)(obj+0x22), mapItem, &DAT_006603bc, 1);  // CREATURE_BANK，子类型=宝屋子
case 0x18: FUN_0040d350(8,  mapItem, &DAT_006603b0, 1);   // DERELICT_SHIP
case 0x19: FUN_0040d350(10, mapItem, &DAT_006603b0, 1);   // DRAGON_UTOPIA＝龙国
case 0x54: FUN_0040d350(9,  mapItem, &DAT_006603b0, 1);   // CRYPT
case 0x55: FUN_0040d350(7,  mapItem, &DAT_006603b0, 1);   // SHIPWRECK
```

`FUN_0040d350 @ 0x40D350`（636B）＝**原版宝屋/龙国信息构造器**（SoD_SP `FUN_10020ba0` 的原版对应物）：

- 首行 `pcVar2 = *(char **)(PTR_DAT_0067029c + 宝屋子*400 + 4)` —— 取宝屋表 **name 字段**（`PTR_DAT_0067029c` = 0x47A3C2 表的重定位指针；`+4` 与 SoD_SP 完全同源）。空串兜底。
- 拼接第 5 参（格式/后缀串 `0x6603b0` / `0x6603bc`）。
- 按访问状态选描述：`param_4 ∈ [0,7]` 且 `(*mapItem >> 5) & (1 << param_4)`（H3MapitemCreatureBank 的 `visited:8`，bits 5..12 = 哪些玩家来过）为假 → 用 `*(char**)(*(int*)(DAT_006a5dc4+0x20)+0x588)` 的通用描述串；否则若 `(*mapItem & 0x2000000) == 0`（未 taken）且 `FUN_00449370()` 为真 → `FUN_0040ab40(1)` 取详细串再拼接。
- 即原版弹窗内容 ≈ **宝屋名 + （未访问）通用描述 / （访问过）详细串**。

### 10.3 显示/隐藏函数（"松开后自动关闭"的机制）

- **显示**：`FUN_004f6c00(x, y, 0xffffffff,0, 0xffffffff,0, 0xffffffff,0, 0xffffffff,0)`（10 参；后 8 个为配色，x/y = 窗口位置）。
- **隐藏**：`FUN_004f6c00(0xffffffff, 0xffffffff, ...)`（首参 -1 即收起）。全 exe 40+ 处隐藏调用，几乎所有界面切换都先收起提示窗。
- **收起点**：`FUN_0040a020 @ 0x40A020`（1293B）**首行**：

```c
if ((*(uint *)((int)event + 0xc) & 0x200) != 0) {
    FUN_004f6c00(0xffffffff,0xffffffff,0xffffffff,0,0xffffffff,0,0xffffffff,0,0xffffffff,0);  // 收起提示窗
    return;
}
AI_UnlockHero(0,1); ...   // 否则按事件坐标差移动英雄（右键拖动方向）
```

它由 `AdventureMap_HandleClick` 的 `case 1:`（`switch(event[2])`）调用。

### 10.4 事件字段口径（H3API `H3CstMessages.hpp`）

- `eMsgCommand`：`KEY_DOWN=1`、**`MOUSE_BUTTON = ITEM_COMMAND = 0x200`**、`MOUSE_WHEEL=0x20A`。
- `eMsgSubtype`：`LBUTTON_DOWN=0xC`、`LBUTTON_CLICK=0xD`、**`RBUTTON_DOWN=0xE`**。
- `eMsgFlag`：`SHIFT=1`、`CTRL=4`、`ALT=32`（与 SoD_SP 的 `DAT_10065650` 镜像一致）。
- **事件[3]（+0xC）的 `0x200` 位未在 H3API 枚举中列出**；按三处用法（`FUN_0040a530` 为真→弹窗、`FUN_0040a020` 为真→收起、`AdventureMap_AI_Main` 0xD 要求为假 / 0xE 要求为真）反推为「右键按住」——**极性属推断，待实机确认**。这也解释了"按住显示、松开收起"。

### 10.5 改造建议（若改原版弹窗而非 SoD_SP）

| 想改什么 | 落点（游戏 exe，或自研插件挂钩） |
|---|---|
| 宝屋/龙国弹窗**内容** | `FUN_0040d350 @ 0x40D350`（名+描述拼接），或 `FUN_00413720` 的 case 0x10 / 0x19（其体内 L40481 / L40795） |
| 弹窗**位置/尺寸** | `FUN_00413720` 尾部（坐标钳制与 `FUN_004f6c00` 调用，其体内 L45159-45187） |
| 弹窗**显示/隐藏行为** | 显示 `FUN_004f6c00 @ 0x4F6C00`；收起 `FUN_0040a020 @ 0x40A020` 首行 |
| 与 SoD_SP ALT 对话框**并存** | 注意 ALT 时 SoD_SP 跳过 `call 0x413720`，原版窗根本不构造 → 挂 `FUN_0040d350`/`FUN_00413720` 只影响**非 ALT** 的普通右键 |


### 10.6 弹窗窗口对象与显示函数本体（2026-10-16 傍晚追加，反汇编证据）

10.1 的链路只到"调用了什么"，本节把**弹窗实体**钉到字节级（dumpbin 反汇编 + H3API 对照）。

**（1）弹窗调用点（`FUN_00413720` 尾部 0x415A80~0x415AEE）**

```asm
00415A80: call 004F6930        ; 量文本尺寸（宽/高 -> [ebp-44h]/[ebp-40h]）
00415A85: mov eax,[ebp+8]      ; 参数 x（格坐标）
00415A8B: shl eax,5            ; ×0x20
00415A88/8E: mov ecx,[ebp+0Ch] ; 参数 y（格坐标）；shl ecx,5
00415A91..00415AA0: x>=8 ? x : 8 ; y>=8 ? y : 8
00415AA8: lea esi,[eax+edx]    ; x + w
00415AAB: cmp esi,258h → 超界则 mov eax,258h-w   ; 屏宽 600
00415ABE: lea esi,[ecx+edx]    ; y + h
00415AC1: cmp esi,228h → 超界则 mov ecx,228h-h   ; 屏高 552
00415AD2..00415AE0: push 0 / push -1 四次        ; 4 个图片槽 = 无
00415AE2/00415AE3: push ecx ; push eax           ; y ; x
00415AE4: mov edx,4                              ; type = 4
00415AE9: mov ecx,697428h                        ; text = &DAT_00697428（全局文本缓冲）
00415AEE: call 004F6C00
```

即完整签名：`0x4F6C00(LPCSTR text /*ecx*/, INT32 type /*edx*/, INT32 x, INT32 y, pic1.type, pic1.subtype, pic2.type, pic2.subtype, pic3.type, pic3.subtype, -1, 0)` —— **12 参 `__fastcall`**，与 H3API `H3API.hpp:29477` 的封装逐参对齐：

```cpp
// H3Messagebox::show(LPCSTR text, eButtonType type, pic1, pic2, pic3)
FASTCALL_12(VOID, 0x4F6C00, text, (INT32)type, -1, -1,
    pic1.type, pic1.subtype, pic2.type, pic2.subtype,
    pic3.type, pic3.subtype, -1, 0);
```

结论：**原版右键对象信息弹窗 = "消息窗家族"函数 0x4F6C00，原版用的 type 值恒为 4、四个图片槽全空、坐标由对象格位置钳制**。H3API 的 `-1,-1` 是"自动定位"，原版这里给的是显式 (x,y)。`type=4` 与 `eButtonType` 枚举的对应关系列入待验证。

**（2）窗口实体（`FUN_004F7020 @ 0x4F7020`，由 0x4F6C00 调用）**

| 现象 | 反汇编证据 | 口径 |
|---|---|---|
| 超时/ID 全局 | `DAT_006977D4` ← `0x4F8970()`+`0x3A98`(15000)；`0x5580A0` 命中时 +`0x4E20`(20000) | 弹窗带自关闭计时器；窗口已存在时置 0 = 不自动关 |
| 分配 | `mov ecx,69D680; call 00557E20` 等前置 → `push 54h; call 00617492`（operator new） | **0x54 字节 = `sizeof(H3DlgTextPcx)`**（与 H3API `_H3API_SIZE_(0x54)` 同值） |
| 构造 | `call 0048F940`（先 `mov dword ptr [esi],63DB40h` 写 vtable） | 窗口类 = **H3DlgTextPcx**；vtable 实测 0x63DB40 |
| 全局槽 | `mov ds:[006995E0],eax`（新窗口指针）；`00699570`/`00699424` 开窗前后保存并置 -1；`006995D8` 时间戳；`DAT_006995DE` "正在显示"标志 | 全 exe 只用这一处窗口；隐藏/关闭即以这些全局为准 |
| 子构造 | `0x48F940` → 基类 `0x5FEFB0` → `0x48FA80`（按 0x100/0x40 粒度换算尺寸、缓冲；含 `mov edi,0C8h`=200 等常量） | 尺寸换算在 0x48FA80；未见串引用，背景 PCX 由基类/type 决定（待验证） |

**（3）对本功能（改造原版弹窗）的决定性结论**

1. 原版弹窗**只是一件 `H3DlgTextPcx`（PCX 底图 + 多行文本）**，不是带控件容器的对话框，`0x54` 的类里也没有子项链表可挂按钮 —— **"在弹窗上加箭头按钮"必须自建窗**（自建窗的底图与高度自适应由插件自理：9 宫格边框/PCX16 自绘 + 按实测字体行高加高）。
2. 弹窗与 SoD_SP 的 ALT 高级对话框互不冲突：SoD_SP 的 ALT 内联补丁落点 `0x40A7B6` 正是 `call 0x413720` 之后的收尾，ALT 命中即跳过整个原版弹窗路径。因此只改原版弹窗不会影响 ALT 路径，反之亦然。
3. 钩子落点若取 `FUN_00413720 @0x413720`（而非 `FUN_0040a530`），可完全避开 SoD_SP 在 `0x40A6DD` 的 5 字节内联补丁；`0x40D350` 有两簇调用者（0x413E31~0x4140F3 与 0x40B4DD~0x40B750），不适合单独作落点。

### 10.7 弹窗时刻"光标下地图项"的运行时定案（2026-10-16 晚，H3Space 实机日志实证）

H3Space 宝屋右键增强插件上线后"仍弹原版窗"，逐轮诊断（每轮日志 + 反汇编交叉验证）得出以下**运行时事实**，静态分析优先级低于这些结论：

| 事实 | 证据 |
|---|---|
| `0x6977DC`（曾以为是"光标下地图项"全局）在 `0x413720` 回调时刻**为空** | 日志 `413720 ... 光标项=00000000 标记=4`（位4=无光标项），同帧原版弹窗正常显示 |
| `0x413720` 的 ECX（self）**不是 H3MapItem**，是 `FUN_0040a530` 的 ESI（光标/地图交互上下文，带 +E4/+E6/+E8/+EC/+F0/+EA/+20C 字段） | `mov esi,ecx` 后 `0x413720` 读 `[esi+E4h]/[esi+E6h]/[esi+E8h]`；该 self 指针不在 mapitems 数组区间（05B68A70 等，数组校验不通过） |
| `0x413720` 的三个栈参数是**弹窗锚点瓦片坐标 (x, y, level)**，不是对象坐标 | 日志 `xy=(25,12)` 与弹窗屏幕位置 `(800,384)` 满足 25×32/12×32；且该瓦片上 `objectType=0`（空地），对象本体不在锚点格上 |
| **对象地图项由调用方 `FUN_0040a530` 在 `0x40A61F~0x40A660` 算入 EDI**：`[ebp-14h]`（打包坐标）→ `(int16)(v*4)>>12 * mapSize + sign16(v<<6)>>6` 两轮 → ×19×2（38 字节/项）→ `lea edi,[ecx+eax*2]`；**`0x40A663` 是"EDI=地图项已就绪、尚未进 ALT/普通分支"的唯一稳定点** | 反汇编 0x40A61F-0x40A660；0x40A663 起才读 `[ebp+8]` 事件、分 ALT（`test bl,bl`）/普通（`call 0x413720`@0x40A698）两路；SoD_SP 补丁点 0x40A6DD 也在其后 |
| 捕获方案（已实机验证）：**LoHook `0x40A663` 存 `context->edi` 到全局，`0x413720` HiHook 里消费**（用后即清） | 日志 `413720 self=... resolved=0F943AC2 ... 标记项=0F943AC2 why=0`，随后 `增强=1`，增强窗正常替换原版弹窗 |
| 修正坐标复刻尝试（self+E4/E6 十位有符号偏移叠加）**不必要**：EDI 捕获已给出精确对象 | 保留 `BankRmbAdjustedItem_` 仅作 resolved 缺失时的兜底 |

诊断位口径（BankRmbTune `why`）：1=无右键按下 2=ALT按下 4=坐标/self无效 8=非宝屋 16=已领取 0x80=诊断异常。二进制日志样例：`why=4`→0x6977DC 空；`why=8`→坐标格 objectType=0；`why=0`→命中。

### 10.8 增强窗内容口径（2026-10-16 晚用户裁定）

- 不再复用原版 `0x4F6C00` 正文；自建 H3Dlg 常开窗整窗替换（type=4 且未领取宝屋时）。
- 内容参考 SoD_SP ALT+右键高级对话框：守兵**分队展示**（`NH3Dlg::Assets::CREATURE_SMALL` 即 `CPRSMALL.def` 32×32 小头像，帧号=生物ID+2，前两帧保留；每队下方"数量 名称"）；奖励含生物头像格 + 资源行 + 宝物行。
- 守兵/奖励各一对升降档箭头，**分两行追加在对应内容之后**（2026-10-17 起，见 §11.4；不再是"节标题行右端"）；无说明行。箭头**常显**：到边界或 `ModifySize=0` 时不灰化/不隐藏，点击无变化即无操作。
- 换档只 `SetFrame/SetText/Show-Hide` 原地刷新，不重建窗口（宽度按四档最大分队数一次算足）。
- **守兵换档口径（2026-10-17 用户裁定）**：不拷贝表内阵型，保留运行时已有的分队数与各队兵种（宝屋中间那队常是原版**升级后**的兵种），只把目标档 `states[tier].guardians` 的**总兵力平均分配**到现有分队（余数补给前面的分队）；只写 `count[7]`，`type[7]` 一位不动，写完 `memcmp` 断言兵种未变，否则整次回滚。原版守军的升级概率/分堆机制见 §11 相关行。

## 11. SoD_SP 高级对话框**排版尺寸**定案（2026-10-17，用户实机截图 + 反编译逐函数核对）

用户提供真实 ALT+右键截图（美杜莎宝屋）指出 H3Space 首版增强窗"不像"，据此逐行核对 `FUN_10020ba0` 及其绘制子函数，得到可直接照抄的排版事实：

### 11.1 内容顺序与行距（`FUN_10020ba0` 调用序）

| 序 | 内容 | 证据 | y / 步长 |
|---|---|---|---|
| 1 | 居中大标题（宝屋名） | `0x4b51f0(...,0,0xe,iVar11,0x26,2,5,-1)` | y≈0x26(38) |
| 2 | 守兵逐队头像 + 下方数量 | `FUN_1001c440(a4,0x2e,bank,guardCount,0)` | y=0x2e(46)，**格步长 0x22(34)** |
| 3 | 资源图标 + 下方数量 | `FUN_1001c3b0(a4,y,bank+0x38,resourceCount)` | 守兵之后 +0x32(50)，**步长 0x22(34)** |
| 4 | 宝物图标（44×44，居中一行） | 循环 `FUN_1001c4d0(a4,x,y,artifactId)`，`x += 0x2e`，起点 `(0x104-count*0x2e)/2` | **步长 0x2e(46)，图标 0x2c(44)** |
| 5 | 奖励生物头像 + 下方数量（居中） | `FUN_1001c050(a4,-1,y,bank+0x54,*(char*)(bank+0x58),1)`，x=-1 时内部取 `width/2-0x10` | 宝物之后 +0x38(56) |

即 SoD_SP 的奖励区顺序是 **资源 → 宝物 → 奖励生物**（生物奖励在最后一行），不是"生物在最上"。

### 11.2 单格绘制与数量框（`FUN_1001c050` / `FUN_1001c220`）

- 图标一律 `0x47be90(0,0,0x20,0x20,...)` = **32×32**（守兵/资源/奖励生物同尺寸）；宝物走 `FUN_1001c4d0` 的 44×44。
- 数量在图标正下方、**文字框高 0x14(20)、宽 0x20(32)**、水平居中：`0x4b51f0(buf,font,x,y+0x20,0x20,0x14,align,1,-1)`。
- 数量对齐常量：普通项 `align=1`(TOP_MIDDLE)，奖励生物（param_5≠0）`align=0xd`；文字由 `FUN_100361d0(数量,&DAT_00697428)` 格式化 —— **只显示数字，不显示中文名**（与截图一致）。
- 行高换算：32 图标 + 20 数量框 ≈ 52，行间再 +50~56，故守兵行 y=46、资源行 y=96。

### 11.3 窗口尺寸公式（`FUN_10020ba0` 收尾）

- 宽：`max(0x104(260), 文本宽 + 0x28(40))`。
- 高：基数 `0x46(70)`；有守兵 → `0x78(120)`；有资源 `+0x32(50)`；有奖励生物 `+0x38(56)`；有宝物 `+0x36(54)`。

### 11.4 H3Space 增强窗的对齐口径（本次实现）

照抄上述行序与尺寸：大标题 bigfont 居中 → 守兵（`CPRSMALL.def`，帧=生物ID+2，步长 34）→ 资源（`resource.def` 帧=资源序号 0..6，步长 34）→ 宝物（`artifact.def`，帧=宝物 ID，步长 46）→ 奖励生物（居中）→ 再追加两行「守兵 n/4 / 奖励 n/4」增减按钮行；全部只显示图标 + 数字，且**每个图标带一圈与格子等宽的描边边框**（复刻原版"同一格先画框、再画图标"的两层叠加）。空行不留：仅当实时值或四档模板存在生物奖励时才预留奖励生物行。

### 11.5 画面缝隙定名（2026-10-17）

对照 H3API `H3API.hpp:20979 / 21021` 与 `reversing\Heroes3Src` 符号表，SoD_SP 绘图所用的两个游戏函数定名如下（本次查图标"边框"时确认）：

| 地址 | 名称 | 签名要点 |
|---|---|---|
| `0x47BE90` | `H3DefFrame::DrawToPcx16` | `(src_x, src_y, src_w, src_h, pcx16->buffer, dst_x, dst_y, pcx16->width, pcx16->height, pcx16->scanlineSize, palette565, mirror, do_not_use_special_colors)`；`this` = 帧指针 |
| `0x55C9C0` | `H3LoadedDef::Load` | 内部引用字符串 `GetSprite`（`Heroes3Src\symbols\function_string_refs.csv` 0x55C9C0 → 0x6830D8） |

据此重读 `FUN_1001c050`（守兵头像）/`FUN_1001c220`（资源）/`FUN_1001c4d0`（宝物）：三者都是**同一格上连续多次 `DrawToPcx16` 同尺寸 blit**（守兵 3 次同源、资源 3 次两条 DEF 交替、宝物先框后调用 `FUN_10039110` 设图再画图标），参数中的 `piVar2[8]` 即 DEF 的调色板指针、`*(this+0x70)` 是对话框绘制缓冲（`H3LoadedPcx16*`）。**即"图标带边框"是"先画框 DEF、再画图标"两层叠加**；框 DEF 的名字在反编译里不可见（`Load` 的实参被 Ghidra 丢弃），故 H3Space 侧用等尺寸自绘描边复刻（见 §11.4 与之配套的设计文档）。

照抄上述行序与尺寸：大标题 bigfont 居中 → 守兵（`CPRSMALL.def`，帧=生物ID+2，步长 34）→ 资源（`resource.def` 帧=资源序号 0..6，步长 34）→ 宝物（`artifact.def`，帧=宝物 ID，步长 46）→ 奖励生物（居中）→ **再追加两行「守兵 n/4 / 奖励 n/4」增减按钮行**；全部只显示图标 + 数字。空行不留：仅当实时值或四档模板存在生物奖励时才预留奖励生物行。

