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
- 切 debug 的途径：面板 → 帮助说明 → 日志级别，落盘 `[Config] 日志级别切换为 debug（已写入 user.ini）`。

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

## 5. 待办与候选修法（**未实施**，需用户裁定）

1. 诊断可见性：把「该救不救」的原因（非全自动 / `heroCasted` 挡板 / 未学法术 / 法力不足 / 方式=不保活 / 阈值未达 / 未绑定 / 无尸体格）提到 `info` 级并按回合限频；`g_control != CM_AUTO` 分支目前完全无日志。
2. 行为候选：
   - a. 消息入口在 `decision == CD_EXECUTE_H3AUTO` 且 `mgr->action == 0`（动作未落地）时，先判一次施法通道再 `TrySubmitConfiguredAction_`；风险：消息入口每帧调用，需靠「一回合一次」+ `g_cast_in_flight` 守卫去重（改钩子入口前必须先加载技能 `h3-plugin-crash-guard`）。
   - b. F9 切到 `CM_AUTO` 成功后（`SetControlMode_` / `PollControlHotkeys_` 路径）立即补判一次施法通道；频率低、时序自然（玩家此刻正等输入）。
   - c. 只改文档/提示：说明「保活只在全自动下生效；切换后需下一次部队行动（或先手动『等待』）才补施」。
3. `[Track] identity lost slot=%d expect=0x%X got=0x%X` 打印的两个值都是 `creature_id`（本次日志 3 次，`expect=0x38 got=0x38`），看不出究竟哪个身份分量不等 → 应改为打印完整身份元组（kind/cid/occurrence/hex/…）。该日志不影响保活（`identity lost` 只清 `alive/count_alive/hex`，不清 `bound`）。
4. 合并版同代码同日志级别（本次核对：`H3BattleStore\modules\AutoExecute.inc.cpp` 的 `1400/1442/1496/1507/1538` 仍为 `LogDebug`，`:1554` 为 `LogInfo`），任何修法应落在 H3BattleStore。

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
