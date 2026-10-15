# H3Auto（打铁助手）功能合并进 H3BattleStore 笔记

日期：2026-10-15　范围：把 H3Auto 的功能合并进 H3BattleStore 单一 DLL，**不含** H3Auto 的打包日志（LogPack）。
设计文档：`H3BattleStore\docs\11-H3Auto功能移植.md`；本笔记只记逆向/机制层面的硬事实与落位结论。

## 1. 四个钩子地址的语义（SoD 1.0 / 0xFFFFE403）

| 地址 | 类型 | 原生语义 | 合并后归属 |
|------|------|----------|------------|
| `0x600430` | LoHook | backbuffer Blt 完成（每帧） | **同址单壳**：宿主战斗悬浮条 + 移植层面板帧/自动推进 |
| `0x4746B0` | LoHook | 战斗消息处理入口 `FUN_004746b0`，`this`=H3CombatManager 在 ECX，消息指针在栈上 `[esp+4]`，`msg[0]`=类型（`4`=鼠标移动） | 移植侧独占（宿主本来没挂） |
| `0x4744D0` | HiHook | `FUN_004744d0` 接管判定：返回非 0 = 自动/AI 执行，返回 0 = 等本地人类输入 | 移植侧独占 |
| `0x4786B0` | HiHook | 动作执行入口：开始执行 `action` 字段（动画/伤害/回合推进） | **同址单壳**：宿主执行诊断 + 移植层「单次接管人工动作消费」 |

- `0x4746B0` 的面板吞并手法：面板存活时把鼠标移动消息的坐标改成离屏（清 hover）、吞 0-9 快捷施法键，
  判定命中返回 `NO_EXEC_DEFAULT`，否则 `EXEC_DEFAULT`；**面板存活分支必须判定后直接 return，不得穿透**
  到下面的主动作提交分支。
- `0x4744D0` 的介入条件：只在原版返回 0（本会交给玩家）时介入；原版非 0（自带自动战斗、蛊惑、AI 侧）
  直接透传原返回值。移植层在 `orig==0` 且该部队有配置时代发动作，仍返回 0，由消息入口提交 `action`。

## 2. 同址钩子的单壳合并（本轮核心机制）

宿主与源插件在同一地址各挂一只钩子时，**必须合并成一只壳**（双挂会各自拿到自己的
`GetDefaultFunc()` 链，原版函数行为与调用次数都不可控）。落地规则：

1. **单一注册点**：地址在宿主 `Entry.inc.cpp` 里只写一次 `WriteLoHook/WriteHiHook`；
   源插件原来的那次注册连同它的 `DllMain` 一起丢弃。
2. **段函数化**：源回调里若自带 `hook->GetDefaultFunc()` 调用，必须摘掉，改成只做自己那段判定的
   段函数（本项目：`HH_OnBattleActionExecute` → `AutoOnActionExecuteSegment_(_BattleMgr_*, int)`，
   末尾的 `THISCALL_2(int, h->GetDefaultFunc(), This, flags)` 删除），**原版调用由宿主壳在 `__try` 之外
   恰好调用一次**（源侧本来也是在调原函数之前判定 `This->action`，段序天然一致）。
3. **调用顺序**：0x600430 壳 = 宿主段（画悬浮条）→ 移植段（面板帧/自动推进）；
   0x4786B0 壳 = 宿主前段诊断 → 移植段（消费单次接管）→ `THISCALL_2(orig)` → 宿主后段诊断。
4. **铠甲各自独立**：两段各自 `__try` + 各自 `GuardCrashFilter_(各自的 id, ...)`，互不吞对方故障；
   壳本身不加 `__try`。
5. **对象视图转换**：源用裸结构视图 `_BattleMgr_`（`Compat.inc.cpp` 里按绝对偏移锚定：`action`@0x3C、
   `hero_casted`@0x54B4、`stack[2][21]`、`active_stack`@0x132C8 附近、`dlg`），宿主用 H3API 的
   `H3CombatManager`，二者是同一对象。转换处用 `reinterpret_cast`，并在宿主 TU 顶层加
   `static_assert(offsetof(H3CombatManager, action) == 0x3C, ...)` 钉住布局一致。
6. 宿主的 `0x4786B0` 注册用 `SPLICE_, EXTENDED_, THISCALL_`（源用 `SPLICE_, THISCALL_`）——保留宿主
   既有签名与 splice 更安全，源段的参数按同一调用约定透传即可。

## 3. 铠甲 id 映射（源枚举 → 宿主字符串键）

源插件用枚举下标索引铠甲表，宿主用字符串键（`GuardRegisterHook_(const char*) -> int`）。合并做法：
保留源侧枚举名，把值改为宿主注册返回值，于是所有钩子入口的
`__except (GuardCrashFilter_(GHID_X, GetExceptionInformation()))` 一字未改。

| 源枚举 | 宿主 id | 用途 |
|--------|---------|------|
| `GHID_BLT` | `AutoAssist.AfterBlt` | 0x600430 每帧段 |
| `GHID_MSGPROC` | `AutoAssist.BattleMsgProc` | 0x4746B0 战斗消息段 |
| `GHID_SHOULD_AUTO` | `AutoAssist.ShouldAuto` | 0x4744D0 接管判定 |
| `GHID_ACTION_EXEC` | `AutoAssist.ActionExec` | 0x4786B0 动作执行段 |
| `GHID_KB` | `AutoAssist.CombatHotkey` | 战斗热键 WH_KEYBOARD 回调 |
| `GHID_PANEL_KB` / `GHID_PANEL_MOUSE` / `GHID_PANEL_ITEM` | `AutoAssist.PanelKeyboard` / `PanelMouse` / `PanelItem` | 面板输入钩子与 item 屏障 |

`kMaxGuardHooks` 16 → 32（宿主自用 14 + 移植 8）。注册发生在静态初始化期（`s_guard_hooks` 零初始化），
早于 `DllMain`，单线程安全。

## 4. 跨插件协作 → 同 TU 直连

合并前靠 patcher 变量跨越 DLL 边界（加载顺序无关，未加载时退化为原行为）：

| 原协作键 | 宿主符号（合并后直连） |
|----------|------------------------|
| `H3BattleStore.RestoreEpoch.v1`（读档纪元，变值即通知） | `battlestore::g_storeRestoreEpoch`（`Variable*`，空则视为 0） |
| `H3BattleStore.BusyQuery.v1`（忙态查询，无参 BOOL） | `battlestore::StoreAutomationBusy_()` |
| `H3BattleStore.BeforeAutoAction.v1`（动作前首档玩家窗口，`BOOL(void* mgr)`） | `battlestore::StoreBeforeAutoAction_(void*)` |

语义保持：忙态（保存中/自动保存中/恢复排队/恢复致命）期间不推进自动施法与部队命令；纪元变化时
切手动控制、清自动状态机、重绑部队追踪；首档窗口未建立时本回合不推进，**保存失败也消费本回合尝试、
不重试**。直连后原来的 `VarInit` 注册仍保留（兼容旧版 H3Auto 同时加载的情况只会被纪律禁止，不靠它工作）。

## 5. 纪律与边界

- **不要再同时加载 H3Auto.dll**：同址双挂 + 面板素材/热键会重复（用户已决定只留合并版）。
- 版本门卫：SoD 数据指纹不符时**不挂任何钩子**（含移植钩子），只保留日志；移植钩子注册在门卫之后。
- 打包日志（LogPack）**不在合并范围**：宿主 `LogPack.inc.cpp` 是唯一属主；源插件帮助页的「打包日志」
  按钮与其 7 个 `help.pack_*` 文案键已删除（与宿主悬浮条第一行原有的打包按钮是两回事，后者保留）。
- 面板/自动化素材与文案：`img\HA_*.pcx`（9 个）、`lang\zh-CN.ini`；方案库走 JSON **v7**，路径
  `<游戏根>\Games\<地图名>\Auto\<16位hex>.json`（回退 `Games\Auto` → DLL 同目录），LRU 保留 30 场。
  注意源插件文档里的「JSON v5」是过时说法。

## 6. 本轮踩到并已修的两个编译期坑

1. **残留 `static void Log*(const char*, ...);` 前向声明 → C2129**（不是 LNK）：移植后这些声明落在子
   命名空间里，遮蔽宿主的全局同名日志实现，域内调用绑到永不定义的实体。每加一批模块都要重扫一遍
   （本项目批次二清 3 个文件、批次三又冒出 6 行）。
2. **源适配器里的 `::Foo()` 全局限定 → C2039**：`::ResetPanelDrafts();` 原本表示「调全局自由函数」，
   移植后自由函数已在子命名空间内 → 改 `autoassist::ResetPanelDrafts();`；**不能裸调用**，同名成员
   函数在场时会自我递归。
