# 冒险地图 ALT+右键「查看信息」归属与实现位置逆向笔记

记录日期：2026-10-16。结论：**该功能由 SoD_SP.dll（热血 F12 插件目录）实现，与 HD Mod 无关**。本次为纯静态调研，未启动游戏、未改动任何代码。

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
| `10002A59` | `push 41h; call GetKeyState` → 等 0x41 = **VK_SPACE**（不是 ALT；`test ax,ax; jns` 高位为 0 即松开时也跳过） |
| `10002A6A` | 取 `[0x69954C]`→`[eax+0x38]` 得 adv manager 指针 `esi` |
| `10002A7A` | `mov eax,[ebx+0x1C]`：地图对象 type/subtype 域，减去 `0x73`（= `BUSH 115`） |
| `10002AA4` | 校验：`MAP_ITEM_TYPE(ebx)==esi+1`（即鼠标下对象的类型字节） |
| `10002AB2` | `(type-0x73) <= 6` → 走 `10002ABD` 分支：`push [esi+0xC]; mov ecx,[ebp-0x10]; call 4317D0`，成功再 `call 100028F0` 拼文本 |
| `10002B00` | `(type-0x8C) <= 6` → `push [esi+0x10]` 同型分支 |
| `10002B45` | `type == 0x7B`（HILL 123）→ 7 次循环 `call 100028F0` 拼资源/守军文本 |
| `10002B87` | `type == 0x7D`（KELP 125）→ 同上 7 次循环 |
| `10002BC8` | 拼完非空时：`ecx=[0x69954C]; call 005D5930; call 005D5810`（刷新 UI） |
| `10002BE7` | `mov [ebx+0x20], 005D460Fh` ← **改写返回落点**，这就是"抢走原版右键弹窗"的一行 |

- 键位修正：ini 没有暴露该功能开关，`GetKeyState(0x41)` 是 VK_SPACE。Changelog 说 ALT+RMB，但本机 `v1.19.4.2` 实际读的是空格（Changelog 落后于实现，或该版本改过键位）。**改造前务必以 `0x10002A59` 的 `push 41h` 为准自行实测**。

## 5. 类型常量口径

`SoD_SP.dll` 的 `(type-0x73)<=6` 覆盖 `H3CstObjects.hpp` 的 `BUSH(115)…FROZEN_LAKE(121)`、`0x7B`=`HILL(123)`、`0x7D`=`KELP(125)`。宝屋/龙国类对象是否走这支，取决于它们的地图对象 type；需要按实际对象 id 复核（`TREASURE_CHEST=101`、`CRYPT=84`、`DRAGON_UTOPIA=25` 等均**不在**这些区间内，说明 handler 覆盖的是"地形小物件 + 指定类型"两套分支，宝屋那一支是 `(type-0x73)<=6` 还是 `(type-0x8C)<=6` 需实机确认）。

## 6. 与 HD_SOD 的同地址函数对照（供改造时不误伤）

游戏 exe 侧 `005D3640` 家族（`FUN_005d3640` 6249B / `FUN_005d5010` 1299B / `FUN_005d5810` 284B / `FUN_005d5930` 134B / `FUN_005c7ba0`）全部属于原版 SoD/HD Mod 的冒险地图对象右键派发链，HD_SOD.dll 未挂钩该链（对 `005D5810/005D5930/005D5010` 引用 0 命中）。

## 7. 复现/深挖用的取证产物

`D:\logs\dsh\scripts\h3-altinfo\`：`sod_sp_disasm.txt`（SoD_SP 全量）、`game_exe_disasm.txt`（Heroes3 HD.exe 全量，856131 行）、`hd_sod_strings.txt`、`sod_sp_strings.txt`、`sod_sp_headers.txt` 等。分析口径：dumpbin `/disasm` + 自写 PE IAT 解析器（`USER32!GetKeyState` → SoD_SP IAT_VA `0x10054138`）。

## 8. 待验证

- 空格 vs ALT：在宝屋/龙国上实测按空格是否触发同一弹窗；若触发，本机版本键位确为空格。
- 宝屋/龙国具体命中哪条 type 分支。
