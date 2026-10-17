# H3Auto 施法通道判定时机与「保活不施放」排查笔记

日期：2026-10-15　范围：H3Auto（打铁助手）施法通道（力盾/保活/保持状态/召唤/智能攻击）的判定挂点、门槛与静默跳过点。
来源：玩家反馈日志（独立版 v0.13.2026.1012，两轮日志：info 级 + debug 级）+ 源码对照。本文只记机制硬事实与排查结论，未实施的改动单列待办。

## 1. 触发挂点：施法只在 0x4744D0 的「交权」时刻判

| 入口 | 地址/函数 | 是否判施法 |
|---|---|---|
| 接管判定钩子（HiHook） | `0x4744D0` → `HH_ShouldAutoExecute` | **是**：`BattleStoreAllowsAutomation_` → `EnsureForceFieldBeforeAction_`（力盾）→ `TryProtectCast_`（保活→保持状态→召唤）→ `TryAutoStop_` → `TryAttackMagicCast_` |
| 战斗消息入口（LoHook `0x4746B0`） | `TryAutoExecuteActiveStack` | **否**：只有 `PollControlHotkeys_` → `BattleStoreAllowsAutomation_` → `EnsureForceFieldBeforeAction_` → `DecideTakeover` → `TrySubmitConfiguredAction_` |

- `TryProtectCast_` 全局**唯一**调用点：`H3Auto\modules\AutoExecute.inc.cpp:2957`，且只在原版 `0x4744D0` 返回 `orig==0`（本会把控制权交给玩家）时执行。
- 源码证据：`TryAutoExecuteActiveStack`（同文件 2900–2929）没有任何 `TryProtectCast_` / `TryAttackMagicCast_` 调用。
- 因此**按 F9 那一刻（启停热键在消息入口轮询）只会提交动作，不会施法**；要等下一次「控制权交给玩家」才判施法。

## 2. 静默门槛（决定「看不到施法」的可见度）

`TryProtectCast_` 入口依次：

| 门槛 | 不满足时 | 日志级别 |
|---|---|---|
| `g_phase != BP_COMBAT_CLOSED` | return false | 无 |
| `g_control != CM_AUTO` | return false | **无**（全手动/单次接管不判不施，设计如此） |
| `g_cast_in_flight` | return false | 无（施法动画重入守卫） |
| `GetHeroCasted_(mgr, side)`（= `cm->heroCasted[side]`） | return false | **Debug，按回合去重**：`[Protect] heroCasted blocks all channels turn=%d side=%d` |
| `!hero`（玩家方无英雄） | return false | 无 |

逐队扫描（`slot 0..20`）：

| 门槛 | 不满足时 | 日志级别 |
|---|---|---|
| `!te.bound \|\| te.side != side` | continue | Debug（`[Protect] queue …`） |
| `ProtectBaselineCount_ <= 0` | continue | 无（基准取 `hero->army_count[source_army_slot]`，读不到退回 `count_at_start`/`count_current`） |
| 战争机器 / 克隆槽 | continue | 无 |
| `dead && StackHex_(st) < 0`（无尸体格） | continue | 无 |
| `HeroMagicAllowed_`：原版总门卫 `0x41FA10` + 禁魔关卡/毁灭之球/斗篷 + `hero->HasSpell` + 法力 ≥ 原版 `CalculateSpellCost` + `!cm->heroCasted[side]` | continue | 无（**静默**） |
| `TargetMagicAllowed_`（龙王神力 `134`） | continue | 无（静默） |
| `ProtectShouldCast(mode, restorable, wound, count, th)` | continue | Debug（`queue`/`cand` 行） |
| 命中目标 | 施法 | info：`[Protect] cast done spell=%d mana=%d->%d casted=%d->%d` |

- 结论：玩家默认 `info` 级日志里，保活「该救不救」的全过程不可见；**连「当前不是全自动所以不判」都没有任何日志**。
- 切 debug 的途径：**战场存档界面悬浮条第一行**的日志等级单选列表点「调试」，写 `H3BattleStore.user.ini` 的 `[Logging] MinLevel`，落盘 `[Config] 日志等级已切换并写入用户配置：debug`。（2026-10-16 之前还可走打铁面板 → 帮助说明 → 日志级别下拉；该下拉已按用户裁定移除，帮助页只剩开源地址行与关闭按钮。）

## 3. 保活法术选取与判定（本次确认为正确，非问题）

- 目标部队 `undead` → 聚灵 `eSpell::ANIMATE_DEAD = 39`；活体 → 复活 `RESURRECTION = 38`（H3API `H3Constants\H3CstSpells.hpp`：`SHIELD=27`、`RESURRECTION=38`、`ANIMATE_DEAD=39`）。
- `ProtectMode`：`PM_COUNT_BELOW=0`（剩余数量 ≤ 该队阈值才救）、`PM_LOSS_GT_RESTORE=1`（已损 HP 严格大于一次可恢复量才救）、`PM_NONE=2`（默认，永不）。
- `ProtectShouldCast`：`PM_NONE` 恒 false；`wound <= 0` 恒 false；`PM_LOSS_GT_RESTORE` 要 `restorable > 0 && wound > restorable`；`PM_COUNT_BELOW` 要 `count_current <= count_below`。
- 可恢复量：法术表 `baseValue[等级] + 力量 × spEffect`（`0x687FA8` 法术表，`+0x30`/`+0x34`），再叠加英雄法术特长（`0x4E6260`）；读不到表退回 50/75/100×力量。
- 「剩≤」输入框：点击进入编辑时**预填当前阈值**（值 0 预填空，避免「点击即变 0」）；`CellControl_CommitCountEdit_` 逐位解析数字、溢出截到 `2147483647`；提交 info 落盘 `[Panel] 保活阈值=%d 位置=%d`（位置 = 该部队战场格坐标 `ctrl->data.position`）。

## 4. 玩家反馈定案（2026-10-15）

对象：独立版 v0.13.2026.1012，DLL 在玩家机 `E:\【推荐】英雄无敌3 V5.4 热血雄鹰版\_HD3_Data\Packs\热血插件\H3Auto.dll`。

- 反馈：保活不施放（期望亡灵队受损就补聚灵）。
- 第一份日志（**info 级**，22:30 场次）：零 `[Protect] cast done`、零 `[Status]`、零 `[Summon]`、`[Magic]`/`[AttackMagic]` 0 次 → 整场没有任何自动施法；但**无法定位原因**（判定明细全是 Debug）。
- 第二份日志（**debug 级**，23:11–23:14 场次，1,399 行 / debug 1,327 行 / info 68 / warn 3）实证：
  - `[Protect]` 仅 2 行：`[Protect] settings committed; next control hand-in re-checks`（info）与 `[Protect] heroCasted blocks all channels turn=30 side=0`（23:14:15.193，debug）。
  - **零** `[Protect] queue/cand/cast` → 保活逐队扫描**从未运行**。
  - `[Takeover] decision=0 … control=1`（全手动）27 次；`decision=2 … control=0`（全自动）**仅 1 次**（23:14:15.194）。
  - 全份日志 `control=AUTO` 仅 2 次（23:14:01.929、23:14:03.749）；面板一打开即 `[Control] 面板打开：切换为全手动`。
  - 按 F9 后同毫秒走的是消息入口：`[Control] control=AUTO` → `[Auto] dispatch slot=1 cid=0x38 action=1` → `[Auto] submit DEFEND slot=1 creature=0x38` → `[Auto] action consumed wake slot=1 action=3`（**未施加任何法术**）。
  - 队伍与配置本身正常：`[Track] bind attempt=1 slot=1 source=4 idkind=1 cid=0x38 hex=137 alive=1 count=475194/517125 action=1`（格式 `count=当前存活/开战数量`）；`[Panel] 保活阈值=517125 位置=137`（阈值被设成该队开战数量，等价「有损失就救」；`cid=0x38=56=骷髅兵`，亡灵 → 本应选聚灵 39）。
  - 该回合 `heroCasted=1` 与玩家手动施法吻合：骷髅兵 `23:13:54 count=388537` → `23:14:15 count=389048`（+511，聚灵/复活效果）。
- **玩家补充实测（关键复现条件）**：「手动按『等待』操作后，就能自动施法了。」
  - 机制解释：H3 的「等待」让该部队本回合稍后**重新获得行动机会**，游戏因此**再次**走一次 `0x4744D0` 交权判定；这次 `g_control` 已是 `CM_AUTO`，`TryProtectCast_` 得以执行 → 施法成功。
  - 根因推论：**按 F9 切全自动时，当前正在行动的部队当回合不会施法**（那次交权已经过去，且消息入口不判施法）；必须等下一次交权（自己下一支部队行动，或该部队「等待」后再次行动）才会补施。玩家体感「开了自动却不施法」即源于此。
  - 同时反证：法术选取、队伍绑定、阈值、法力、已学法术都没问题（能施放说明这些条件全部满足）。

## 5. 已实施的修法（2026-10-15，A+B+E，**仅合并版 H3BattleStore**，用户裁定）

用户裁定做 A + B + E：「只在 H3BattleStore 项目中修，原 H3Auto 项目不用更新」。改动全在 `H3BattleStore\modules\AutoExecute.inc.cpp`；改前按纪律加载技能 `h3-plugin-crash-guard`。

### 5.1 A：消息入口补判施法通道（每回合一次）

新增 `static bool TryProbeCastChannelFromMsg_(_BattleMgr_* mgr, bool force)`，放在 `TryAutoExecuteActiveStack` 上方：

- 门槛：`!mgr` → 退；`mgr->action != 0` → 退（**施法必须在提交动作之前**，此刻 action 仍为 0）；`mgr->auto_combat || IsHiddenBattle(mgr) || IsTacticsPhase_(mgr)` → 退（与 `TrySubmitConfiguredAction_` 同口径）；`force == false` 时再过**每回合一次**闸门（静态 `s_gate_turn` 与 `GetCurrentBattleTurn_` 比较）。
- 动作：`LogDebug("[Protect] msg-entry cast probe turn=%d force=%d control=%d action=%d", …)` 后按交权路径同序调 `TryProtectCast_(mgr)` → `TryAttackMagicCast_(mgr)`；返回值忽略，施放与否由通道内部静默判定（已施法/无法施法/方式不保活/阈值未达/无尸体格）。
- 调用点：`TryAutoExecuteActiveStack` 内 `DecideTakeover` 之后、`TrySubmitConfiguredAction_` **之前**，条件 `decision == CD_EXECUTE_H3AUTO`。

### 5.2 B：F9 切全自动当帧强制补判

- 新增文件级 `static bool g_cast_probe_pending = false;`（放在 `g_oneshot_return` 之后）。
- `ToggleBattleManual_()` 记录 `const bool to_auto = (g_control == CM_MANUAL);` → `SetControlMode_(to_auto ? CM_AUTO : CM_MANUAL);` → `to_auto` 时置 `g_cast_probe_pending = true`。
- 消息入口在 `PollControlHotkeys_` 之后立即取走该标志并 `force=true` 补判——**不看当前部队是否有配置**，覆盖「当前部队是手动规则/等待中，`DecideTakeover` 不返回代发」的情形。
- 交权路径 `HH_ShouldAutoExecute` 在 `TryProtectCast_(This)` 之后消费该标志（`g_cast_probe_pending = false;`），避免下一帧消息入口重复补判。
- 与 A 的分工：A 只在「判为代发动作」时生效且每回合一次；B 是按键驱动的一次性强制补判，两者都落在消息入口、都在提交动作之前。

### 5.3 E：身份丢失日志打印完整元组

`UpdateStackTracking_` 原 `LogWarn("[Track] identity lost slot=%d expect=0x%X got=0x%X", i, t.creature_id, s->creature_id)`（两值同源、无信息量）改为打印 `attempt=期望/当前`、`cid=期望/当前` 与身份元组 `id(k=kind s=side v=value o=occurrence)` 的「期望/当前」对照。判等口径未改：`StableStackIdentityEquals` 要求 `kind/side/value/occurrence` 全等且任一侧 `STACK_ID_NONE` 即不等（`PolicyCore.hpp:515-521`）；身份结构 `{kind, side, value, occurrence}`（`PolicyCore.hpp:479-484`，kind ∈ NONE/ARMY_SLOT/WAR_MACHINE/SUMMON）。

### 5.4 铠甲与验证

- 补判函数在消息入口既有 `__try` 内调用（与交权路径把 `TryProtectCast_` 放 `__try` 内同规），**不新增钩子、不改钩子入口结构、原版函数调用次数不变**。
- 默认与 `H3BS_UI_NULL=1` 两变体 `build.bat` 各 exit 0、**0 错误 0 警告**；`tests\run-unit-tests.ps1` **七组**全绿（Archive 12/217、Codec 6/4224、LogControls 3/30167、UiPort 3/39、AltTail 7/14、PolicyCore 29/1609、CrashFixTests 5/21），末行 `PASS all unit tests (Catch2, no game, no hooks, no real clipboard)`。
- 产物：默认 `Release\H3BattleStore.dll` **732672 B** SHA256 `08FAF0AA97FDF01AE89CCB499864E2E58C865220A7E440358F9E661249EF6617`（上一轮 732160 B，本次 +512 B）；NULL `Release\null\H3BattleStore.dll` **401408 B** SHA256 `817C67D231B8C922528DD53CF8C37573BDE1DB5CABD3AE81940BF1728E1B86DB`；`deploy.bat` exit 0，部署副本与 `Release\` 源 SHA256 一致（部署到 `D:\Heroes3\Heroes3_2026.10.09\_HD3_Data\Packs\热血插件\`）。
- 文档同步：`H3BattleStore\docs\11-H3Auto功能移植.md` §5.7（新增）、`docs\变更记录.md` 2026-10-15 首条。

### 5.5 仍未做（待用户裁定）

1. **D（诊断可见性）未选**：把「该救不救」的原因（非全自动 / `heroCasted` 挡板 / 未学法术 / 法力不足 / 方式=不保活 / 阈值未达 / 未绑定 / 无尸体格）提到 `info` 级并按回合限频；`g_control != CM_AUTO` 分支目前仍然**完全无日志**——下次玩家默认日志依旧只能证明「没施法」，不能说明原因，排查仍需请玩家切 debug 级。
2. 面板/文档提示（原候选 c）未加：仍没有「保活只在全自动下生效；切换后需下一次部队行动或先手动『等待』才补施」的明示文案。
3. **实机验收归用户**：按 F9 后当回合是否立即补施、「等待」是否不再是必须步骤；自动战斗/隐藏战斗/战术期不应出现施放（本次新增的门槛）。
4. 玩家侧现跑独立版 H3Auto v0.13.2026.1012，本次修法只进合并版 H3BattleStore；是否让玩家改用合并版由用户决定（版本号由用户手动提升，不由 agent bump）。

## 6. 日志取证速查（下次排查直接抄）

```powershell
# 施法成功与通道痕迹（info 级，玩家默认日志就有）
Select-String -Path *.log -Pattern '\[Protect\] cast done|\[Status\] cast done|\[Summon\] 召唤成功|\[AttackMagic\] submit'
# 保活判定明细（需玩家切 debug 级）
Select-String -Path *.log -Pattern '\[Protect\]|heroCasted blocks'
# 控制权与接管决策
Select-String -Path *.log -Pattern '\[Control\] control=|\[Takeover\] decision='
# 队伍绑定与损失基准
Select-String -Path *.log -Pattern '\[Track\] bind|\[Track\] update|identity lost'
```

## 7. 2026-10-17 追加：合并版「等待后」把聚灵卡死（玩家日志定案）

来源：玩家反馈「聚灵还是要按一下等待或防御才会自动施法」+ 日志 `H3BattleStore_logs_20261017_213639.7z`（合并版 v0.17.2026.1017，compiled 2026-10-17 17:09，玩家机 `E:\...\Packs\热血插件\H3BattleStore.dll`，debug 级，主日志 5049 行）。

### 7.1 定案（日志 + 源码对齐）

- 本场聚灵（`ANIMATE_DEAD=39`）**施放了 11 次，全部落在 `control=AUTO` 区间**；手动区间 **0 次**。三证据互证：① 11 条 `[Protect] cast spell=39` / `cast done` 全部在 AUTO 段内；② 手动段只有 25 行 `[Protect] 未执行 … reason=control`；③ mana 3875→3720 完全闭合（11×10 聚灵 + 3×15 玩家在 MANUAL 手动的 `[Cast] spell=14`），全日志 11 条 `[Cast] spell=39` 每条都紧跟自己的 `[Protect] cast`/`cast done`——**玩家从未手动施放过聚灵**。
- **发日志前 25 秒的卡点**：21:36:16.793（turn 28）起连续 4 次 `[CastWait] 等待后拦截：尚未等待且本轮首次交权 turn=28/29/30/31 slot=1`；`[CastWait] 等待后放行` 全日志 **0 行**。起因是 21:36:11.394~21:36:13.505 在面板里把「每回合施法时机」改成**指定部队 + 等待后=1**，21:36:15.039 `PANEL_COMMIT` 生效。
- **「还是要」的来源**：21:36:27.885 玩家把模式改回 0（首次行动），但 21:36:35.158 是 `PANEL_CANCEL` → 草稿丢弃（`CommitAndCloseSettingsPanel_` 未执行，`settings committed` 最后一次是 21:36:15.078）→ 生效配置仍是「指定部队+等待后」，下一场继续要等。cancel 也不恢复 AUTO（其后 `[Takeover] … reason=yield-to-player`，日志结束时仍 MANUAL）。
- **防御救不了**：turn 28/29/30 推走回合的都是 `action=3`（`BA_DEFEND`，见 `AutoExecute.inc.cpp:2323` 的 `BattleActionCode`），这三轮聚灵彻底丢失。

### 7.2 新增机制硬事实

1. **waiting 位只由「等待」置位，防御不置位**：反编译全库仅 `reversing\Heroes3Src\src\h3\uncategorized\blk_470000.c:17268` 一处 `| 0x2000000`，位于 `case 8`（`BA_WAIT=8`）；`case 3`（`BA_DEFEND`）不含该位（它置 bit27 defending）。位在 `creature+0x84 bit25`，`H3CombatCreature::IsWaiting()` 同口径。
2. **`NoteCastTimingHandoff` 的 `acts>=2` 是死代码（2026-10-17 已按用户裁定删除）**：`turn` = `H3CombatManager::turn`（BattleMgr+0x13D6C，`AutoExecute.inc.cpp:1045-1053`）在行动入口 `FUN_00475800` 首句每 action 无条件 +1（`blk_470000.c:9934`，另见本目录《战场等待标志与每回合等待.md》）。因此每次交权 turn 都变 → `acts` 每次清零；同一 turn 内第一次询问后 `on_self=true` 锁死，`acts` 最多 1。日志 turn=28 连问 3 次全写「首次交权」为铁证。→ `after_wait` 实际**只依赖 bit25**。**处置（2026-10-17 用户裁定）**：既然永远凑不满就不该留——已删除 `CastTimingWaitState`/`ResetCastTimingWaitState`/`NoteCastTimingHandoff` 与 `s_cast_wait_state` 及对应单测，`CastTimingAllowsThisHandoff_` 现在只查 `StackWaitedThisRound_`（`IsWaiting()`）。`docs\变更记录.md` 与 `docs\11-H3Auto功能移植.md:354` 已同步改写（旧条目加了「已删除」注记）。提交 H3BattleStore `796989e`。
3. **手动模式无旁路**：全仓唯一写 `CM_AUTO` 的位置是 F9（`AutoExecute.inc.cpp:702`）；单次接管 J 在 MANUAL 下被 `734` 整段跳过；面板打开/提交/重打/读档/store 恢复一律强制 MANUAL。热键钩子只认 F9/J/P（`AutoStore.inc.cpp:728-734`），**等待/防御的按键与鼠标点击都不经这条链**，不可能把控制权变成 AUTO。
4. **消息入口补判有覆盖缺口**：`TryAutoExecuteActiveStack` 只在 `cast_probe_forced`（F9 当帧）或 `decision==CD_EXECUTE_H3AUTO` 时调 `TryProbeCastChannelFromMsg_`（`3306-3323`）；`rule=AA_MANUAL` / `KEEP_ORIGINAL` / 全手动一律不补判（`3324-3325` + `3231-3233`）。
5. **日志-代码对齐缺口**：`CanCastSpellAtCoord` 失败（`1775-1778`）、候选逐槽过滤（`1660-1668`/`1688-1690`/`1720-1724`）、探针因 `mgr->action != 0` 跳过（`3286`）**三处零日志**；`[Protect] heroCasted blocks` 与 `LogDecline_` 的去重键是 `turn`，而 turn 每 action 变 → 文档说的「按回合去重」实为「每 action 一行」。**（2026-10-17 已补齐静默点日志：逐槽跳过原因/选中复核失败/游戏拒施/探针因已有动作跳过，并在 `settings committed` 行与探针行打出生效施法时机快照；`heroCasted blocks` 的去重键问题未改，只是量偏大。）**

### 7.3 待办（未实施，待用户裁定）

1. ~~勾「等待后」时由插件自己代发「等待」~~ **已否决（2026-10-17 用户裁定）**：「等待后」只影响施法时机，插件不代发等待动作，等待由玩家自己做。
2. ~~修 `acts` 判据~~ **已完成（2026-10-17）**：不修而是**直接删掉**，只留 bit25 作唯一判据（用户裁定：凑不满的判据不该留）。
3. ~~拦截后仍要代发配置动作~~ **不做**：与本功能语义无关（手动回合本来就该等玩家操作），本条属误判。
4. ~~三处静默点补 debug + 探针补上下文~~ **已完成（2026-10-17）**：逐槽跳过原因（unbound/no-stack/baseline/cid/war-machine/no-corpse-hex/magic/threshold，走 5 秒收账闸）、选中复核失败、游戏拒施（每回合一行）、探针因已有动作跳过（每回合一行）；`settings committed` 行与探针行都带生效施法时机快照（timing/wait/target/heroCasted）。
5. 面板/HUD 明示当前生效的「每回合施法时机」（含等待后勾选态），避免「以为改回来了其实按了取消」——**仍未做**（用户未表态；本次改为在日志里打生效快照，属于替代取证手段）。
