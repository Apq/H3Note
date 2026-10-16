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
  if ((*param_1 & 0x2000000) == 0) {                      // 未访问过（visited 位）
    iVar11 = (*param_1 >> 0xd & 0xfff) * 0x6c + *(int *)(_DAT_00699538 + 0x4e3dc);
    local_20 = iVar11;                                    // 该地图格位结构（stride 0x6C）
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
