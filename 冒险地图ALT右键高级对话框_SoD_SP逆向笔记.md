# 冒险地图 ALT+右键「查看信息」归属与实现位置逆向笔记

记录日期：2026-10-16。结论分两层，不能混为一谈：

- **归属已定**：Changelog v1.18.0 第 279 行记载 "Added Advanced Dialogs to map adventure (ALT + RMB)"，且实现确实在 `SoD_SP.dll`（F12 插件）侧，**HD Mod 侧对同一链零命中**。这条有独立证据（Changelog + 107 个钩子注册表中第 11 项）支撑，可信。
- **具体分支未定**：被找到的 `0x10002A10` handler 只覆盖地形物件（`BUSH`(0x73)..`FROZEN_LAKE`(0x79)、`HILL`(0x7B)、`KELP`(0x7D)），**与"宝屋/龙国"对不上**；且它查的是 `GetKeyState(0x41)`（= 键 'A'，VK 0x41），不是 ALT(0x12)。所以这个 handler 身份仍然存疑，不能直接当改造目标。

本次为纯静态调研，未启动游戏、未改动任何代码。

> ⚠️ 勘误（2026-10-16 10:12）：本笔记初稿曾把 `push 41h` 误写成 VK_SPACE。**0x41 = 键 'A'**，VK_SPACE 是 0x20。该 handler 判的键位因此完全对不上 ALT，这一点反过来提醒"命中分支 ≠ 目标功能"，见 §4 与 §5。

## 1. 用户问题

「宝屋、龙国上 ALT+右键查看信息的功能是哪里实现的（主要看是 HD Mod 还是 SOD_SP），准备对其进行改造。」

## 2. 归属结论（三路证据交叉）

| 证据 | 内容 |
|---|---|
| 插件自带 Changelog | `...\_HD3_Data\Packs\F12插件\Changelog.txt:279`「[+] Added Advanced Dialogs to map adventure (ALT + RMB) […] Players can still use normal RMB dialogs if ALT is not pressed.」 |
| 反汇编钩子注册 | `SoD_SP.dll`（base `0x10000000`）在 `0x10002EF3` 处用 `call [ecx+18h]` 注册 handler `0x10002A10`，钩挂游戏 exe `0x005D45FD`（`push 5D45FDh / push 10002A10h` 两条立即数在注册函数尾段连续出现） |
| HD_SOD 侧排查 | `HD_SOD.dll` 无任何对应实现：对 `0x005D45FD/0x005D5810/0x005D5010/0x005C7BA0` 全部 0 命中；HD_SOD 自己的 ALT 判定只有 `0x14`(CapsAsEnter) 与 `0xA0/0xA2`(LSHIFT/RSHIFT) 两处，与本地图右键无关 |

- 游戏 exe = `...\Heroes3 HD.exe`（2.8 MB，ImageBase `0x400000`），HD_SOD.dll 映像基 `0x1000000`。

## 3. 游戏侧原文件地址（SoD_SP 改造点）

`FUN_005d3640`（`reversing\Heroes3Src` 符号表，6249 字节，游戏侧负责冒险地图对象右键派发的函数）里：

```
005D45FD: mov  eax,[ebx+0x19C]
005D4603: push 0
005D4605: push 0
005D4607: push eax
005D4608: mov  ecx,ebx
005D460A: call 005D5010      ; 原版「弹出右键信息窗口」
005D460F: push esi            ; SoD_SP 接管后的落点
005D4610: mov  ecx,ebx
005D4612: call 005C7BA0
005D4617: pop edi/esi; mov eax,1; ret 4
```

SoD_SP 的注入方式：handler 结束时把 `[ebx+0x20]` 改成 `0x005D460F`，从而跳过 `0x005D5010` 这条原版路径、走自己那支（`call 005C7BA0` 收尾）。**改造这个功能，落点是 `SoD_SP.dll` 的 `0x10002A10` 这个 handler，不是游戏 exe。**

## 4. SoD_SP handler `0x10002A10` 结构（按地址）

| 地址 | 行为 |
|---|---|
| `10002A4A` | `mov eax,4CE950h; call eax` → 游戏谓词：`DAT_0069959c != 0 || DAT_00698a40 == 3` 才继续（否则走 `10002BF3` 直接返回原路径） |
| `10002A59` | `push 41h; call GetKeyState` → 0x41 = **键 'A'**（不是 ALT；`test ax,ax; jns` 高位为 0 即松开时跳过） |
| `10002A6A` | 取 `[0x69954C]`→`[eax+0x38]` 得 adv manager 指针 `esi` |
| `10002A7A` | `mov eax,[ebx+0x1C]`：地图对象 type/subtype 域，减去 `0x73`（= `BUSH 115`） |
| `10002AA4` | 校验：`MAP_ITEM_TYPE(ebx)==esi+1`（即鼠标下对象的类型字节） |
| `10002AB2` | `(type-0x73) <= 6` → 走 `10002ABD` 分支：`push [esi+0xC]; mov ecx,[ebp-0x10]; call 4317D0`，成功再 `call 100028F0` 拼文本 |
| `10002B00` | `(type-0x8C) <= 6` → `push [esi+0x10]` 同型分支 |
| `10002B45` | `type == 0x7B`（HILL 123）→ 7 次循环 `call 100028F0` 拼资源/守军文本 |
| `10002B87` | `type == 0x7D`（KELP 125）→ 同上 7 次循环 |
| `10002BC8` | 拼完非空时：`ecx=[0x69954C]; call 005D5930; call 005D5810`（刷新 UI） |
| `10002BE7` | `mov [ebx+0x20], 005D460Fh` ← **改写返回落点**，这就是"抢走原版右键弹窗"的一行 |

- 键位事实：`0x10002A59` 的 `push 41h` = 键 'A'，**不是 ALT(0x12)、不是空格(0x20)**。Changelog 记载的功能是 ALT+RMB，但本机 `v1.19.4.2` 这个 handler 读的是 'A' —— 两者对不上，是"该 handler 可能根本不是 ALT+RMB 那个功能"的硬证据之一。

## 5. 类型常量口径

`SoD_SP.dll` 的 `(type-0x73)<=6` 覆盖 `H3CstObjects.hpp` 的 `BUSH(115)…FROZEN_LAKE(121)`、`0x7B`=`HILL(123)`、`0x7D`=`KELP(125)`。宝屋/龙国类对象**不在**这些区间内（`TREASURE_CHEST=101`、`CRYPT=84`、`DRAGON_UTOPIA=25` 均不匹配四条分支中的任何一条：`0x73..0x79`、`0x8C..0x92`、`0x7B`、`0x7D`）。所以这个 handler 判的是**地形小物件**，不是宝屋/龙国。宝屋/龙国的实现要么在 SoD_SP 的另外 106 个钩子里，要么走另一条机制（例如 `UNLEASHED` 数据/`NCE` 之类读取地图存档扩展信息的路径），**尚未定位**。

## 6. 与 HD_SOD 的同地址函数对照（供改造时不误伤）

游戏 exe 侧 `005D3640` 家族（`FUN_005d3640` 6249B / `FUN_005d5010` 1299B / `FUN_005d5810` 284B / `FUN_005d5930` 134B / `FUN_005c7ba0`）全部属于原版 SoD/HD Mod 的冒险地图对象右键派发链，HD_SOD.dll 未挂钩该链（对 `005D5810/005D5930/005D5010` 引用 0 命中）。

## 7. 复现/深挖用的取证产物

`D:\logs\dsh\scripts\h3-altinfo\`：`sod_sp_disasm.txt`（SoD_SP 全量）、`game_exe_disasm.txt`（Heroes3 HD.exe 全量，856131 行）、`hd_sod_strings.txt`、`sod_sp_strings.txt`、`sod_sp_headers.txt` 等。分析口径：dumpbin `/disasm` + 自写 PE IAT 解析器（`USER32!GetKeyState` → SoD_SP IAT_VA `0x10054138`）。

## 8. 待验证

- **键位**：Changelog 记 ALT+RMB，`0x10002A10` 读 'A' 键 —— 需实机确认 ALT+RMB 弹的是不是同一个窗；若不是，说明 `0x10002A10` 是另一个功能，必须重新找。
- **宝屋/龙国的实现位置**：SoD_SP.dll 共注册 107 个钩子（注册函数 `0x10002C20`，`call [ecx+18h]`），目前只排查了其中 11 个（`0x5F3C43/0x5F439B/0x5F6BE2/0x5F4B05/0x5F522A/0x46D12B/0x46D4CB/0x46D9F0/0x5F50F8/0x5D45FD`），尚未逐一定性。下一步应把宝屋/龙国的对象 type 常量（如 `0x19`=DRAGON_UTOPIA、`0x54`=CRYPT 等）拿去比对这 107 个 handler 里的 `cmp/sub` 常量。
- 也可从 SoD_SP 的 `[options]` 键值侧反查：本机 `SoD_SP.ini` 里没有 ALT/对话框相关开关，说明该功能**没有 ini 开关、默认常开**，改造只能改代码。
