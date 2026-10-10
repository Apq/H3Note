# H3Auto 智能攻击施法接口考证

> 主题：H3Auto 部队卡片的智能攻击类施法（敌方目标 / 战场落点）
>
> 目标版本：Heroes3.exe Shadow of Death（SoD，`SOD = 0xFFFFE403`），x86。
>
> 来源性质：本篇记录本轮对 `Heroes3Src/src/decompiled/all_functions_named.c`、H3API 与 NH3API 的静态源码对照。**本篇没有实机断点、动态参数抓取或游戏内施法验证。** 静态能确认调用关系和候选机制的内容写入“静态确认”；ABI 细节、命中结果、抵抗及具体目标语义仍按“待实机验证”处理。
>
> 相关项目：H3Auto。本文只写接口考证，不修改 H3Auto 源码。

## 1. 结论速览

H3Auto 当前部队卡片上的施法选项本质是 SoD_SP 快捷施法数字键序列。智能攻击施法应另走“法术 ID + 目标敌人或目标 hex”的路径，不能继续把攻击法术伪装成数字快捷键：快捷槽中已有目标信息，但它代表玩家预先配置的槽位状态，不是 H3Auto 每次行动重新计算的目标。

静态证据支持两类智能目标：

1. **单体攻击法术**：枚举敌方候选部队，得到其所在 hex，经过原版坐标/目标规则检查后调用直接施法。
2. **位置型范围攻击法术**：枚举候选中心 hex，用原版范围生成/收集逻辑得到覆盖的战斗单位，再按 H3Auto 自己的评分选择中心 hex。这里的“范围攻击”是选一个施法位置后影响周围格子，不等于对全体部队施法。

本轮建议纳入智能攻击白名单的法术 ID 为：

| ID | H3API 名称 | 目标形态（当前静态分类） |
|---:|---|---|
| 15 | `MAGIC_ARROW` | 单体敌方部队 / 目标 hex |
| 16 | `ICE_BOLT` | 单体敌方部队 / 目标 hex |
| 17 | `LIGHTNING_BOLT` | 单体敌方部队 / 目标 hex |
| 18 | `IMPLOSION` | 单体敌方部队 / 目标 hex |
| 19 | `CHAIN_LIGHTNING` | 原版链式目标路径，首目标仍需选择；后续跳转由原版决定 |
| 20 | `FROST_RING` | 范围中心 hex；半径 1，不含中心 |
| 21 | `FIREBALL` | 范围中心 hex；半径 1，含中心 |
| 22 | `INFERNO` | 范围中心 hex；半径 2，含中心 |
| 23 | `METEOR_SHOWER` | 范围中心 hex；半径 1，含中心 |
| 57 | `TITANS_LIGHTNING_BOLT` | 单体敌方部队 / 目标 hex |

明确排除：

- `13 FIRE_WALL`：需要完整确认空 hex 段、连续阻挡与落点规则，暂不纳入通用智能攻击白名单。
- `24 DEATH_RIPPLE`、`25 DESTROY_UNDEAD`、`26 ARMAGEDDON`：原版全场作用路径，不属于本功能的“选择敌人或选择范围中心”模型，排除出本版通用智能目标。

白名单只表示“可以进入智能目标候选”，不表示英雄必然学会、当前地形可用、法力足够、原版必然命中或不会被抵抗。

## 2. 当前快捷施法路径与智能路径的边界

H3Auto 当前快捷施法实现位于 `H3Auto/modules/AutoExecute.inc.cpp` 的 `TriggerQuickSpellDigit_`：

- 数字 `1..9/0` 映射到 SoD_SP 快捷槽；
- 从 SoD_SP 槽表读取 `{spellId, targetHex, targetStackPtr}`；
- 向游戏窗口投递数字键 `WM_KEYDOWN/WM_KEYUP`；
- 等待 `hero_casted` 翻转或英雄魔力下降；
- 无论成功、失败还是超时都推进快捷施法游标。

这条路径能复现玩家预先设置的快捷施法，但智能攻击需要在每次行动时重新决定：

```text
法术 ID
  → 目标敌方部队或候选中心 hex
  → 原版坐标/目标合法性检查
  → 直接施法入口
  → 观察施法状态和战场结果
```

快捷施法的 `targetHex/targetStackPtr` 不应成为智能施法的长期配置字段，也不应让智能目标覆盖玩家的 SoD_SP 快捷槽。两种模式应在配置、执行状态和日志中分开。

## 3. 直接施法接口

### 3.1 H3API `CanCastSpellAtCoord`

源文件：[`H3API/include/h3api/H3Managers/H3CombatManager.cpp`](../H3API/include/h3api/H3Managers/H3CombatManager.cpp)，第 21–24 行。

```cpp
_H3API_ BOOL8 H3CombatManager::CanCastSpellAtCoord(
    INT32 spell_id, INT32 spell_expertise, INT32 coordinates)
{
    return THISCALL_7(BOOL8, 0x5A3CD0, this,
        spell_id, spell_expertise, coordinates,
        currentActiveSide, 1, 0);
}
```

静态可确认：

- SoD 地址为 `0x5A3CD0`；
- `this` 为 `H3CombatManager*`，调用约定是 thiscall；
- 显式参数是 `spell_id`、`spell_expertise`、`coordinates`；
- H3API 包装器把当前 `currentActiveSide`、`1`、`0` 作为后续参数传入；
- 返回类型是 `BOOL8`，不能按 C++ `bool` 或 BOOL32 的大小习惯臆测 ABI。

该函数适合在候选中心或目标 hex 上作原版坐标合法性检查，但“合法”不等价于“施法最终命中”。它不能替代施法后效果验证，也不能证明范围评分的伤害预测正确。

### 3.2 H3API `CastSpell`

同一 H3API 文件第 33–35 行：

```cpp
_H3API_ VOID H3CombatManager::CastSpell(
    INT32 spell_id, INT32 hex_ix, INT32 cast_type_012,
    INT32 hex2_ix, INT32 skill_level, INT32 spell_power)
{
    THISCALL_7(VOID, 0x5A0140, this,
        spell_id, hex_ix, cast_type_012,
        hex2_ix, skill_level, spell_power);
}
```

SoD 直接入口为 `0x5A0140`。原版英雄施法路径的调用形态可在 [`Heroes3Src/src/decompiled/all_functions_named.c`](../Heroes3Src/src/decompiled/all_functions_named.c) 的 `FUN_005a0140` 定义及其调用点对照：函数定义从约第 325114 行开始，函数体签名包含 this 加 6 个显式参数。

本轮对原版调用约定采用以下静态口径：

```text
CastSpell(spell, hex, 0, -1, 0, 3)
```

其中 `type=0`、`hex2=-1` 是英雄单目标/位置目标路径的原版调用形态；`skill_level=0`、`spell_power=3` 不是 H3Auto 智能施法最终应硬编码的配置，而是原版调用点给出的参数形态。原版英雄路径会在内部重算等级/力量、计算并扣除法力，并置位 `heroCasted`；具体参数是否对每一个智能攻击法术、每种目标形态都等价，仍需实机验证。

`CastSpell` 返回 `VOID`，因此“函数返回”不能当作命中成功。至少需要区分：

- 调用没有异常；
- `heroCasted` 是否置位；
- 英雄魔力是否按预期下降；
- 单体目标状态/生命是否变化；
- 范围中心的实际受影响部队是否变化。

### 3.3 NH3API 对照

源文件：[`NH3API/nh3api/core/combat.hpp`](../NH3API/nh3api/core/combat.hpp)。

- 第 530–531 行：

  ```cpp
  [[nodiscard]] bool can_cast_spells(int32_t side, bool hero_spell) const
  { return THISCALL_3(bool, 0x41FA10, this, side, hero_spell); }
  ```

  这是 `0x41FA10` 的战斗层施法能力检查，显式参数是 side 和 hero_spell。源代码声明返回 C++ `bool`；不要把它与 `H3CombatManager::CanCastSpellAtCoord` 的 `BOOL8` 包装器混为同一个 ABI。

- 第 629–630 行：

  ```cpp
  [[nodiscard]] static int32_t get_distance(int32_t start, int32_t stop)
  { return FASTCALL_2(int32_t, 0x469250, start, stop); }
  ```

  这是 SoD 六角战场距离函数 `0x469250`。范围候选评分应复用这个原版距离语义，不自行用方格曼哈顿距离替代。

NH3API 本段只作为接口对照，不表示 H3Auto 可以直接引入 NH3API 的容器或结构。范围函数的内部候选列表属于原版 `exe_vector` 等 ABI，H3Auto 不应新造同 ABI 容器并传给原版函数。

## 4. 英雄学法与施法资格

### 4.1 learned 与 artifact available

H3API [`H3API/include/h3api/H3Heroes/H3Hero.hpp`](../H3API/include/h3api/H3Heroes/H3Hero.hpp) 第 243–246 行给出：

```cpp
/** @brief [3EA] Spells the hero has learned*/
BOOL8 learnedSpells[70];
/** @brief [430] Spells the hero has access to through artifacts*/
BOOL8 availableSpell[70];
```

因此：

- `learnedSpells` 位于英雄对象 `+0x3EA`，长度 70；
- `availableSpell` 位于 `+0x430`，长度 70；
- H3API `H3Hero::HasSpell`（[`H3API/include/h3api/H3Heroes/H3Hero.cpp`](../H3API/include/h3api/H3Heroes/H3Hero.cpp)，第 83–86 行）实际为：

  ```cpp
  return learnedSpells[spell] | availableSpell[spell];
  ```

  这是 OR 语义，表示学会或由宝物提供访问权。

智能攻击施法的“严格 learned”白名单资格不能用 `GetSpellExpertise(spell) > 0` 替代，也不能只调用 `HasSpell`：

- `GetSpellExpertise` 返回的是等级/专精相关值，不是 `learnedSpells` 原始位；
- `HasSpell` 会把 artifact available 也算进去；
- 本版要求白名单攻击法术严格检查 `learnedSpells[spell_id]`，宝物可用但英雄未学会不自动纳入。

### 4.2 等级、地形与费用

H3API `H3Hero::GetSpellExpertise` 在 [`H3API/include/h3api/H3Heroes/H3Hero.cpp`](../H3API/include/h3api/H3Heroes/H3Hero.cpp) 第 53–55 行调用 `0x4E52F0`：

```cpp
return THISCALL_3(INT32, 0x4E52F0, this, spell_id, special_terrain);
```

H3API `H3Hero::CalculateSpellCost` 在同文件第 294–296 行调用 `0x4E54B0`：

```cpp
return THISCALL_4(INT32, 0x4E54B0,
    this, spell, opponentArmy, specialTerrain);
```

静态可确认这两个接口都接受地形相关参数；费用接口还接受敌方 army。智能施法执行前应使用真实 hero/terrain/target 上下文计算资格和费用，不能以“魔力大于某个固定常量”替代。具体函数返回值对所有白名单攻击法术的实战含义仍需要动态确认。

### 4.3 原版 `FUN_005a3cd0` 目标坐标路径

[`Heroes3Src/src/decompiled/all_functions_named.c`](../Heroes3Src/src/decompiled/all_functions_named.c) 第 327244 行开始是 `FUN_005a3cd0 @ 0x005a3cd0`。其静态代码显示：

- 先限制 `coordinates` 在原版战场索引范围内；
- 从法术表读取法术标志；
- 对带特殊位置/范围语义的法术进入对应逻辑；
- 普通目标会读取战场格结构并检查边界、占用/阻挡等条件。

这支持“先生成候选 hex、再调用原版合法性检查”的设计，但不能从该函数单独推出每个攻击法术的最终命中效果。

## 5. 原版攻击法术分支与范围形状

### 5.1 单体与范围分支

`FUN_005a0140 @ 0x005a0140` 的原版反编译定义位于 `all_functions_named.c` 约第 325114 行。其法术分派在约第 325603 行可见：

```c
case 0x14:
case 0x15:
case 0x16:
case 0x17:
    FUN_005a4c80(param_3, spell, expertise, out);
    break;
```

法术 ID `0x14..0x17` 即 20..23，进入范围处理；链式法术 19 走不同分支；15..18 和 57 属于单体目标候选路径。

范围处理函数 `FUN_005a4c80 @ 0x005a4c80` 的定义在约第 327912 行，函数体约第 327950–328014 行显示：

```c
FUN_005a4a00(param_2,
    (spell == 0x16) + 1,
    spell != 0x14,
    out);
```

对应关系：

- `FROST_RING (20)`：`center_radius = 1`，不含中心；
- `FIREBALL (21)`：半径 1，含中心；
- `INFERNO (22)`：半径 2，含中心；
- `METEOR_SHOWER (23)`：半径 1，含中心。

这只是原版范围生成参数的静态解释。实际覆盖仍由 `FUN_005a4a00`、战场格状态、双格部队和原版目标处理共同决定。

### 5.2 范围候选收集、双格去重

`FUN_005a4a00 @ 0x005a4a00` 位于 `all_functions_named.c` 约第 327777 行。静态代码显示它会遍历范围结果中的 hex，调用 `FUN_004e7230` 取得格上的战斗单位，并以战斗单位的内部标记写入范围命中记录。

原版会对双格部队做去重/合并处理；H3Auto 不应自行构造 `exe_vector` ABI 或把自有容器传进这些原版内部函数。较稳妥的实现是：

1. H3Auto 自己枚举 0..186 的候选 hex；
2. 用已经确认的 hex 距离和项目侧战斗单位结构计算候选；
3. 对双格部队按稳定的战斗单位指针/槽身份去重；
4. 只把最终选定的 `spell_id + center_hex` 交给直接施法适配器；
5. 不把 H3Auto 容器作为原版函数参数。

“自己计算候选”与“调用原版执行”应分层，避免把原版内部 vector ABI 当成公开接口。

### 5.3 链式闪电与友军风险

原版分派在 `case 0x13`（十进制 19）调用 `FUN_005a6670 @ 0x005a6670`，见约第 325599–325600 行及第 329037 行起的函数体。后续链式跳转在约第 329069–329138 行通过游戏内部 `FUN_005a6500` 推进；智能施法负责选择首目标。

范围处理中的 `spell == 0x3b`（十进制 59）调用 `FUN_005a4b20`，属于狂暴的另一路范围处理，不是连锁闪电19，不能混用。

链式法术可能跳到友军。范围攻击也可能包含友军。**本版不承诺自动避免友军伤害**，除非后续逐法术完成动态验证并明确加入目标评分规则。玩家若选择启用智能攻击，应在 UI/说明中明确这个边界，不要把“候选范围最大”写成“安全范围最大”。

## 6. 不能复用为通用过滤器的接口

### 6.1 `CanReceiveSpell / FUN_004477a0`

`FUN_004477a0 @ 0x004477a0` 位于 `all_functions_named.c` 约第 58094 行。其内部先调用 `FUN_005a3f90`，再按法术类型检查目标部队状态、战争机器/生物类别、免疫和当前战斗字段。

静态上它同时混入：

- 目标能否接受某类法术；
- 已有状态/已有作用的检查；
- 原版当前路径的其它门卫条件；
- AI 施法价值/判定所需状态。

因此不能把它当成所有智能攻击候选的统一、无副作用过滤器。对于具体攻击法术，应先按该法术的静态目标形态筛选，再调用已确认的坐标合法性接口；是否调用更深层原版目标门卫，需要逐项验证其参数和副作用。

### 6.2 `FUN_005a8950 @ 0x005a8950`

该函数位于约第 330540 行：先调用 `FUN_005a83a0`，再比较返回/计算结果。静态关系显示它可能进入随机抵抗路径。它不是纯查询；调用它做候选预筛可能额外消耗 RNG 或改变战斗状态。

因此智能目标评分阶段不应调用 `0x5A8950` 作为“是否会抵抗”的预检查，更不能对每个候选循环调用来挑最优目标。抵抗留给原版实际施法。

### 6.3 `FUN_005a83a0 @ 0x005a83a0`

该函数位于约第 330354 行，反编译代码包含英雄、地形、目标阵营、生物类别、免疫、法术强度等多段条件，并有浮点返回路径。虽然它是原版施法目标/价值相关的重要函数，但当前没有完成稳定的 C++ ABI 对照，不能直接从 H3Auto 调用作为通用过滤器。尤其不能仅凭反编译参数数量拼一个调用签名。

## 7. 智能目标选择的建议边界

### 7.1 单体攻击法术

单体白名单法术可采用：

```text
遍历敌方存活部队
→ 过滤无效槽、无有效 hex、非目标阵营和明确不适用目标
→ 对目标 hex 调 CanCastSpellAtCoord
→ 计算候选评分
→ 选择一个首目标
→ CastSpell(spell, target_hex, 0, -1, ...)
```

候选评分属于 H3Auto 策略，不属于本篇已确认的原版 AI 价值公式。第一版应只提供可解释的策略，例如“预计伤害最大”“可击杀优先”，并把目标槽、目标 hex、候选数和最终结果写入 debug 日志。

`CHAIN_LIGHTNING` 只能保证首目标候选；后续跳转目标由原版决定，不能把首目标选择结果扩展为整条链路的保证。

### 7.2 范围攻击法术

范围法术可采用：

```text
枚举候选 center hex
→ 原版 CanCastSpellAtCoord 检查坐标
→ 按该法术形状生成覆盖集合
→ 双格单位去重
→ 统计敌方/己方覆盖与预计收益
→ 按策略选择一个 center hex
→ CastSpell(spell, center_hex, 0, -1, ...)
```

冰环选中心时，中心 hex 本身不属于伤害范围，所以若策略要求至少命中一名敌人，中心附近必须存在受击敌格；不能把冰环中心直接当成“被攻击队伍所在格”而跳过邻格检查。火球、流星中心包含在范围内，烈焰半径是 2。

范围候选的战场索引必须遵循 SoD 实际战场布局和原版边界。原版源码在 `FUN_005a3cd0` 中检查 `coordinates <= 0xBA`，即有效上界包含 186；不能把 15×11 的 165 个连续格索引当作完整游戏 hex 域。边界/侧栏 hex 是否候选，须以原版合法性检查和战斗单位位置字段过滤。

双格单位的命中集合必须去重。不能因为两个占用格都在范围内就把同一部队伤害乘二。

## 8. 与 H3Auto 现有施法通道的接线原则（设计建议，不是本轮代码改动）

H3Auto 当前已有 `g_cast_in_flight`、`CastSideGuardEnter_/Leave_`、`heroCasted` 去重和插件侧 SEH。智能攻击应复用施法保护层，但增加独立的请求类型：

```text
AttackSpellRequest {
    spell_id;
    target_hex;
    target_stack;       // 单体调试/验证可用，直接入口是否需要它待确认
    target_mode;        // 单体 / 范围中心
    score;
}
```

优先级仍需与现有力盾、保活、保持状态、召唤通道协调。攻击类智能施法不应覆盖快捷施法配置，也不应在保活/保持状态/召唤尚未决定时抢占本回合唯一施法机会。具体优先级属于 H3Auto 设计决策，不在本篇静态考证中宣称已完成。

## 9. 静态证据索引

以下是本轮实际核对过的源文件与区间：

| 内容 | 源路径 | 位置 |
|---|---|---|
| H3API 坐标合法性检查与直接施法 | `H3API/include/h3api/H3Managers/H3CombatManager.cpp` | 21–24、33–35 |
| H3API 法术等级/费用/HasSpell | `H3API/include/h3api/H3Heroes/H3Hero.cpp` | 53–55、83–86、294–296 |
| H3API learned/available 字段 | `H3API/include/h3api/H3Heroes/H3Hero.hpp` | 243–246 |
| NH3API can-cast 与六角距离 | `NH3API/nh3api/core/combat.hpp` | 530–531、629–630 |
| SoD 施法入口定义及英雄路径 | `Heroes3Src/src/decompiled/all_functions_named.c` | `FUN_005a0140` 约 325114 起；英雄路径约 325191–325228 |
| 坐标合法性函数 | 同上 | `FUN_005a3cd0` 约 327244 起 |
| 范围分派 | 同上 | 约 325603–325614 |
| 范围收集与形状参数 | 同上 | `FUN_005a4c80` 约 327912 起，约 327950–328014 |
| 范围候选收集 | 同上 | `FUN_005a4480` 约 327561 起、`FUN_005a4a00` 约 327777 起 |
| 六角距离 | 同上 | `FUN_00469250` 约 84783 起 |
| 链式法术分支 | 同上 | `FUN_005a4b20` 约 327837 起 |
| 目标/免疫/价值相关函数 | 同上 | `FUN_004477a0` 约 58094 起、`FUN_005a83a0` 约 330354 起、`FUN_005a8950` 约 330540 起 |

## 10. 待实机验证

以下事项不能由本轮静态源码直接定稿：

1. `CastSpell` 对 15–23、57 每一类法术的 `hex_ix` 实参是否都采用目标部队格/范围中心格的同一语义。
2. 单体法术是否需要额外的目标部队指针、`hex2_ix` 或其它施法类型值；当前只确认 H3API 包装签名和原版英雄路径形态。
3. `CanCastSpellAtCoord` 返回真后，实际施法是否仍可能因地形、禁魔、魔法书、抵抗、免疫或其它战斗状态失败。
4. `heroCasted` 置位、法力扣除与“实际命中”之间的全部组合，尤其是 VOID 返回、阻止框和静默失败。
5. 冰环、火球、烈焰、流星对双格部队的精确覆盖；静态代码显示原版有处理，但 H3Auto 侧评分集合仍需与游戏画面逐例对拍。
6. 范围法术对己方部队、战争机器、障碍物和边界 hex 的实际影响。
7. 链式闪电后续跳转的目标排序、重复目标规则及友军跳转条件。
8. `FUN_005a83a0`、`FUN_005a8950`、`FUN_004477a0` 是否存在任何可安全复用的纯查询子路径；在 ABI 和副作用未确认前不从插件直接调用。
9. `FIRE_WALL (13)` 的完整空段、占用和持续伤害语义。
10. SoD_SP 快捷槽目标结构是否能安全地被智能施法临时复用；当前设计按不复用处理。

本篇结论只覆盖静态考证。完成上述验证前，智能攻击施法只能作为设计候选，不能在 H3Auto 文档中写成“已实机确认命中”或“自动避免友伤”。
