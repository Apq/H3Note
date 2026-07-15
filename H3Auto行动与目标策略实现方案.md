# H3Auto 行动与目标策略实现方案

> 更新时间：2026-07-14
> 适用项目：`D:\GitHub\H3\H3Auto`
> 关联逆向笔记：[战争机器控制权逆向笔记.md](战争机器控制权逆向笔记.md)、[H3Auto设置对话框逆向笔记.md](H3Auto设置对话框逆向笔记.md)
> 状态：本文以**当前实际代码**为准重写；实现与设计一致，个别执行细节在文中标注。

---

## 1. 定位与原则

H3Auto 的目标是**为玩家提供长时战斗的助力，减少重复操作**，不是接管电脑 AI 的全部决策。
玩家为每支部队预设一条「行动 + 目标」规则，战斗中该部队轮到行动时由 H3Auto 自动提交，
省去反复手点。

配置模型拆成两个正交部分：

- **行动策略（action）**：这支部队「做什么」。
- **目标策略（target）**：行动「作用于哪支部队或哪个战场位置」。

核心原则：

1. 只生成动作和参数，交原版执行器完成动画、伤害、重绘、状态记账和回合推进；
   不自行替换整个战斗循环。
2. 目标可以是**己方部队、敌方部队或战场位置**。
3. 攻击区分**近战攻击**（站立格 + 攻击格模拟点击）和**远程攻击**（选目标部队）。
4. 主动执行失败时，普通部队可按配置**降级为防御**；战争机器不降级。
5. 除明确的战争机器回退场景外，普通部队绝不交回原版 AI。
6. 所有方案只驻留进程内存，不写回 INI（INI 仅提供 UI 标签与热键等静态配置）。
7. UI 只呈现合法组合，无效选项直接隐藏而非置灰。

---

## 2. 数据结构（源：`modules/ConfigLog.inc.cpp`）

### 2.1 枚举

```cpp
enum AutoActionKind : uint8_t {
    AA_MANUAL = 0,        // 手动（不干预）
    AA_DEFEND,            // 防御
    AA_WAIT,              // 等待（枚举保留，UI 下拉暂不提供）
    AA_MOVE,              // 移动（UI 文案「循环移动」）
    AA_MELEE_ATTACK,      // 近战攻击
    AA_RANGED_ATTACK,     // 远程攻击
    AA_FIRST_AID,         // 急救帐篷疗伤
    AA_CATAPULT,          // 投石车攻击城墙
    AA_COUNT
};

enum AutoTargetKind : uint8_t {
    AT_NONE = 0,          // 无目标
    AT_STACK,             // 部队目标
    AT_POSITION,          // 战场位置目标
    AT_COUNT
};

enum AutoTargetSide : uint8_t {
    ATS_OWN = 0,          // 己方（UI 文案「自己」）
    ATS_ENEMY,            // 敌方
    ATS_EITHER,           // 双方（执行前仍受兼容矩阵约束）
    ATS_COUNT
};

enum AutoTargetSelector : uint8_t {
    SEL_FIXED = 0,        // 指定部队 / 指定位置
    SEL_RANDOM,           // 随机
    SEL_SEQUENTIAL,       // 顺序轮换
    SEL_NEAREST,          // 最近
    SEL_FARTHEST,         // 最远
    SEL_RANGED_SPEED,     // 远程优先 + 高速
    SEL_COUNT_HIGH,       // 数量最多
    SEL_COUNT_LOW,        // 数量最少
    SEL_MOST_WOUNDED,     // 损失生命最多（帐篷急救）
    SEL_NONE,             // 无：不按选择器挑目标（追加到末尾）
    SEL_COUNT
};
```

> **枚举稳定性约定**：枚举值一经分配不再移动。新增项一律追加到末尾（如 `SEL_NONE`）。
> UI 标签数组、INI 的 `[Actions]/[Sides]/[Selectors]` 段严格**按枚举下标**排列；
> 「下拉里显示哪些项、什么顺序」完全由 `GetAllowed*` 构建器控制，与枚举下标解耦。
> （历史教训：曾因 INI 标签顺序停留在旧模型，导致下拉显示「近战攻击」实为「等待」。）

### 2.2 规则结构

```cpp
struct AutoTargetRule {
    AutoTargetKind kind;
    AutoTargetSide side;
    AutoTargetSelector selector;
    int8_t  fixedSide;         // 固定部队：0/1，-1=未设
    int8_t  fixedSlot;         // 固定部队：0..20，-1=未设
    int16_t fixedCreatureId;   // 跨战斗指纹，-1=未设
    int16_t fixedHex;          // 固定位置 hex 0..186，-1=未设
    int16_t meleeStandHex;     // 近战站立/接近格，-1=未设
    int16_t meleeAttackHex;    // 近战攻击点击格，-1=未设
};

struct AutoStackRule {
    AutoActionKind action;
    AutoTargetRule target;
    bool allowDefendFallback;  // 允许降级为防御（仅普通部队）
};
```

### 2.3 方案存储

```cpp
AutoStackRule g_profiles[5][21];   // 5 套已确认方案 × 21 槽位，仅驻留内存
int           g_active_profile;    // 当前生效方案序号
AutoStackRule g_active_rules[21];  // 运行时视图（执行端读取）
```

- 5 套方案供玩家切换预设；每套 21 个槽位对应一方部队栏位。
- 默认全为 `AA_MANUAL`（不干预）。

---

## 3. 行动可选集（源：`CellControl_GetAllowedActions`）

按单位类型过滤，只呈现合法行动：

| 单位类型 | 可选行动 |
|---|---|
| 弹药车（AMMO_CART） | 手动（实际不进入面板） |
| 急救帐篷（FIRST_AID_TENT） | 手动、急救治疗 |
| 投石车（CATAPULT） | 手动、投石车攻击 |
| 弩车 / 箭塔（BALLISTA / ARROW_TOWER） | 手动、远程攻击 |
| 普通远程部队 | 手动、防御、循环移动、近战攻击、远程攻击 |
| 普通近战部队 | 手动、防御、循环移动、近战攻击 |

- 「等待」枚举保留但下拉不提供。
- `is_ranged` 由面板打开时按 `stack.info.shooter` 精确判定并存入 `CellData.is_ranged`，
  切换方案时复用该值，不再用 `creature_type` 粗判（否则射手如大法师会丢失远程选项）。

---

## 4. 目标可选集（源：`CellControl_GetAllowedSelectors`）

### 4.1 选择器

- **近战攻击**：不走选择器，固定 `SEL_FIXED`（站立格 + 攻击格）。
- **其它需要目标的行动**：统一提供 4 项 —
  `无(SEL_NONE) / 远程高速优先(SEL_RANGED_SPEED) / 数量最多(SEL_COUNT_HIGH) / 随机(SEL_RANDOM)`。

> 精简为 4 项符合「减少重复操作」的定位，不追求覆盖全部 AI 策略。

### 4.2 阵营行（源：`CellControl_ShowsSideRow` / `FixedSideHint`）

| 行动 | 阵营行 |
|---|---|
| 循环移动 | 显示阵营下拉（自己 / 敌方 / 双方，作为靠近锚点） |
| 近战攻击 | 固定说明「站立格+攻击格」 |
| 远程攻击 | 固定说明「敌方部队」 |
| 急救治疗 | 固定说明「己方伤员」 |
| 投石车攻击 | 固定说明「城墙位置」 |

### 4.3 是否需要目标区（源：`CellControl_ActionNeedsTarget`）

需要目标：移动、近战攻击、远程攻击、急救治疗、投石车攻击。
不需要（隐藏目标区）：手动、防御、等待。

---

## 5. 规则规范化（源：`CellControl_NormalizeRule`）

行动变化或加载方案时调用，保证规则自洽：

1. 若当前 `action` 不在单位允许集内，回退到允许集首项（或 `AA_MANUAL`）。
2. 不需要目标的行动：目标区清空，`allowDefendFallback=false`。
3. 各行动设定默认目标 `kind/side`（见 `DefaultTargetForAction`）：
   - 近战：`AT_POSITION` + `SEL_FIXED`，校验站立/攻击 hex 范围。
   - 远程：`AT_STACK` + 敌方。
   - 急救：`AT_STACK` + 己方。
   - 投石车：`AT_POSITION` + 敌方。
   - 移动：`AT_STACK`/`AT_POSITION`。
4. **选择器收敛**：非近战行动，若当前 `selector` 不在 `GetAllowedSelectors` 结果内，
   吸附到该集合首项，防止显示/保存非法选择器（旧配置残留的「最近」等会被纠正）。
5. 不显示降级复选框的行动：`allowDefendFallback=false`。

---

## 6. 设置面板 UI（源：`modules/SettingsDlg.inc.cpp` + `CellControl.inc.cpp`）

### 6.1 渐进式布局

每个己方部队一张卡片：左侧生物图标 + 位置，右侧动态控件区，按「行动 → 目标」顺序展开：

```text
行1：行动:   [远程攻击 ▾]
行2：阵营/说明（视行动而定）
行3：选择器: [数量最多 ▾]     （近战时为「攻击: A07 ▾」）
底部：□ 允许降级为防御（仅普通部队主动行动）
```

- 无目标行动（手动/防御）只显示行1。
- 近战攻击行2 = 站立格下拉，行3 = 攻击格下拉（攻击格候选仅站立格相邻）。

### 6.2 下拉展开几何（源：`CellControl_GetExpandListTopY`）

每个下拉从**其所在行的下边缘**展开：
行动→行1底、阵营→行2底、选择器→行3底、站立→行2底、攻击→行3底。
绘制（`DrawDropdownItem` 接 `list_top_y`）与命中（`HitExpandVisibleIndex`）使用同一基准，避免错位。

### 6.3 标签来源（源：`LoadLabels_`）

从 `H3Auto.ini` 的 `[Actions]/[Sides]/[Selectors]` 按枚举下标读取；缺失时用 `DEFAULT_*_LABELS` 兜底。
当前标签：

- Actions：手动/防御/等待/循环移动/近战攻击/远程攻击/急救治疗/投石车攻击
- Sides：自己/敌方/双方
- Selectors：指定目标/随机/顺序/最近/最远/远程高速优先/数量最多/数量最少/伤最重/无

---

## 7. 方案保存流程（源：`SettingsDlg.inc.cpp`）

目标行为：打开界面自动加载上次设置；调整过程中不影响已保存设置；仅点「确定（勾）」才真正写入。

- 打开面板：`memcpy(g_profiles → s_p.draft_rules)`，进入**草稿副本**编辑，原方案不动。
- 编辑格子：改动只写 `s_p.cells[].data.rule`（内存草稿）。
- 切换方案（`SelectProfile_`）：先 `SaveCurrentCellsToDraft_` 存回草稿，再 `LoadSelectedProfileIntoCells_` 载入目标方案。
- 点确定（`CommitAndCloseSettingsPanel_`）：`SaveCurrentCellsToDraft_` → `CommitProfiles` 一次性提交全部 5 套到 `g_profiles`。
- 点取消 / ESC：直接关闭，草稿丢弃，`g_profiles` 不变。

---

## 8. 执行分发（源：`modules/AutoExecute.inc.cpp`）

### 8.1 接管判定（`DecideTakeover`）

| 单位 | 判定 |
|---|---|
| 弹药车 | 保持原版 |
| 急救帐篷 | 配了急救→执行，否则原版 |
| 投石车 | 配了投石→执行；否则有弹道学→原版，无→交 AI |
| 弩车/箭塔 | 配了远程→执行；否则有炮术→原版，无→交 AI |
| 普通部队 | 手动→保持原版；否则 H3Auto 执行（绝不交回 AI） |

### 8.2 动作提交（`TrySubmitConfiguredAction_`）

根据 `rule.action` 分发到对应 `Submit*`，普通部队失败且允许时降级 `SubmitDefend_`：

- **防御** `SubmitDefend_`：写 `action=BA_DEFEND`。
- **等待** `SubmitWait_`：写 `action=BA_WAIT`。
- **移动** `SubmitMove_`：`ResolvePositionTarget_` 求目标 hex，写 `action=BA_WALK`。
- **近战** `SubmitMelee_`：攻击格上有敌人（头或尾）才出手；写 `mouse_coord/attacker_coord/move_type=7`，
  `action=BA_WALK_ATTACK`，param=站立格，target=攻击格。
- **远程** `SubmitRanged_`：`SelectStackTarget_` 选敌方目标，写 `action=BA_SHOOT`。
- **急救** `SubmitFirstAid_`：选己方伤员，写 `action=BA_FIRST_AID`。
- **投石** `SubmitCatapult_`：城墙位置。

写入后由原版主循环（`FUN_004786b0` 等）接管动画/伤害/回合推进。

### 8.3 目标选择（`SelectStackTarget_` / `PickBySelector_`）

先按 `side` 过滤双方 `stack[2][21]` 得候选，再按选择器挑一个：

- `SEL_NEAREST/FARTHEST`：按 `hex_ix` 距离。
- `SEL_COUNT_HIGH/LOW`：按存活数量。
- `SEL_MOST_WOUNDED`：按损失生命（`(count_at_start-count_current)*1000 + lost_hp`）。
- `SEL_RANGED_SPEED / SEL_RANDOM / 其它`：当前实现取随机候选。
  > 注：`SEL_RANGED_SPEED` 尚未实现「远程优先+速度」排序，暂等价随机；后续补。

---

## 9. 待完善

- `SEL_RANGED_SPEED` 的真实排序（远程优先→速度降序）。
- 移动的完整原版寻路可达性校验（当前固定位置优先，否则靠近目标格）。
- `SEL_NONE` 在执行端的语义细化（当前不需目标的行动本就不查选择器）。
