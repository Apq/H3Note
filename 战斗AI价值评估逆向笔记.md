# 战斗 AI 价值评估逆向笔记

> 基于 `D:\Heroes3\Heroes3_2026.05.01\Heroes3.exe` 反汇编确认。
> radare2 路径：`D:\Programs\radare2-6.1.6-w64\bin\radare2.exe`

## 九、可攻击目标评分的真实链路（阶段性确认）

### 1. 0x469BC0：候选目标槽位的扫描、过滤与容器搬移

`0x469BC0` 不是双目标分数比较器；它更像“候选列表的整理器”。证据：

- 入口处先按 `ecx + 0x546`、`ecx + 0x53CC` 定位两组候选槽位。
- 两段循环都按 0x13 个槽位遍历。
- 每个槽位先读 `stack_id`，过滤掉 `0xFFFFFFFF / 0 / 2 / 3 / 4 / 5 / 6` 等特殊值。
- 之后调用：
  - `0x4E32E0`：对当前 side/对象集合做状态检查与筛选；
  - `0x4E2E40`：清理/更新某个目标槽；
  - `0x4E2FC0`：把一个目标从候选集合中移除；
  - `0x41B440`：把条目批量搬到另一段连续数组；
  - `0x4AF570`、`0x522AF0`、`0x4AF240`、`0x46AD50`：容器维护、区间挪动和尾部修正。

`0x469BC0` 自身看到的分支主要是过滤、遍历和维持数组一致性，并没有出现明确的 `if (scoreA > scoreB)` 式比较。

### 2. 0x469C50：候选生成 + 插入排序主干

`0x469C50` 才是战场内“攻击哪支部队”链路的主函数。它的行为已经可以较清楚地拆成三段：

#### 第一段：生成候选槽并预处理

- `arg_8h` 作为 side 参数；
- `0x14F4 - side` 用来定位一侧候选集合首地址；
- `arg_ch` 指向另一侧的候选数组/计数；
- 循环 19 个槽位，过滤掉无效 `stack_id`；
- 对每个有效候选调用 `0x4E32E0`；若返回失败则跳过。

#### 第二段：刷新/删除旧候选

- 通过 `0x4E2FC0` 删除某个槽位的旧条目；
- 通过 `0x4E2E40` / `0x41B440` / `0x4AF570` / `0x522AF0` / `0x4AF240` / `0x46AD50` 调整容器布局。

#### 第三段：把新候选插入到有序区间

这一段是关键：

- `0x00617492(eax*8)` 分配/扩展目标数组空间；
- `edi` / `eax` / `ebx` 三者在数组区间内移动；
- 通过 `cmp edi, eax`、`cmp ecx, edx`、`jl/jge/jne` 这种区间搬移逻辑，把新条目插进中间位置；
- 这说明“比较后排序”的最终效果是通过**插入/搬移**实现，而不是在 `0x469C50` 中看到一个单独的 `scoreA > scoreB` 大 if 分支。

### 3. score 写在哪里

目前能确认的写入点是：

- `0x469C50` 调用 `0x4E32E0` 后，候选信息被写入 `0x469C50` 自己维护的临时局部结构；
- 紧接着通过 `0x522AF0`、`0x4AF570`、`0x4AF240`、`0x46AD50` 把条目写入/搬移到目标容器中；
- `0x469C50` 结束时，`[esi + 8]`、`[esi + 4]` 等指针被重新调整，说明最终候选表存放在 `esi` 指向的容器里。

结论：**score 不是单独写到某个全局“分数数组”，而是写进 `0x469C50` 维护的候选条目结构，再通过容器插入排序固化顺序。**

### 4. score 的字段构成：已确认/未确认

**已确认：**

- 战场威胁评估 `0x469F30` 使用 `hit_points(+0x4C)`，不是 `level`；
- `0x42C86A` / `0x42DBFC` 一类战场外/战略层逻辑会使用 `AI_value`；
- `0x469C50` 的候选筛选并不直接显示 `fight_value`、`AI_value`、`hit_points` 的线性加权公式。

**未确认：**

- 目前没有证据能把 `0x469C50` 的候选 score 直接定成 `fight_value(+0x3C) + AI_value(+0x40) + hit_points(+0x4C)` 三项相加；
- 也没有在 `0x469C50` 主体里看到这三个字段的固定求和。

因此，当前更稳妥的结论是：**这三个字段可能在更下层的评估函数里参与，但还不能把它们当作已确认的 score 组成。**

### 5. 真正比较两个候选目标 score 的分支

目前能定位到的“比较”主要有两类：

1. **候选筛选比较**：
   - `0x469BC0` / `0x469C50` 中大量 `cmp` 只是判断槽位是否有效、是否越界、是否已存在。

2. **容器插入排序比较**：
   - `0x469C50` 后半段通过区间搬移实现有序插入；
   - 真正决定“这个候选插在前还是后”的比较逻辑，**更可能隐含在 `0x4AF570` / `0x522AF0` / `0x4AF240` 这些容器维护例程里**，而不是在 `0x469BC0` 里显式出现。

### 6. 最终如何选中攻击目标

阶段性链路可写成：

1. `0x476DA0` 进入战斗 AI 回合决策；
2. 调 `0x469BC0` 清理/整理候选目标集合；
3. 调 `0x469C50` 生成候选并插入有序容器；
4. 容器维护例程完成位置排序；
5. 最终执行阶段从排序后的首项/优先项中取出攻击目标并下发动作。

**更准确地说：选中目标不是“先算一个 score 数组再遍历找最大”，而是“在生成候选时就维持有序，最后取排在前面的条目”。**

### 7. 0x43AC50 的位置

`0x43AC50` 仍然没有进入这条战场目标选择主链；当前证据不足以把它并入“攻击哪支部队”的主流程。

## 十、阶段性算法（更新版）

```text
1. 枚举战场候选目标槽位
2. 过滤无效/死亡/特殊状态目标
3. 对可攻击目标生成候选条目
4. 调用容器维护函数插入到有序区间
5. 通过搬移维持候选顺序
6. 从排序后的首项中选定攻击目标
```

## 十一、已确认事实

- `0x469BC0`：候选整理/过滤/搬移，不是最终双目标分数比较器。
- `0x469C50`：候选生成与有序插入的主干函数。
- `0x4E32E0`：用于候选状态检查/筛选。
- `0x4E2FC0`：移除候选槽旧条目。
- `0x4E2E40`：辅助更新候选状态。
- `0x41B440`、`0x4AF570`、`0x522AF0`、`0x4AF240`、`0x46AD50`：参与容器搬移/排序维护。
- `0x469F30` 的威胁评估使用 `hit_points(+0x4C)`。
- `D:\GitHub\H3\H3BattleValueInfo` 中显示的 `fight_value` 来源已经由源码确认：全局生物表 `*(char**)0x6747B0`，条目大小 `0x74`，字段偏移 `+0x3C`。
- `_BattleStack_` 在 `+0x74` 嵌入 `_CreatureInfo_`，所以同一个 `fight_value` 从 `_BattleStack_` 指针读取时偏移是 `+0xB0`。

## 十一补：fight_value 字段来源修正

此前只按“全局生物表 `+0x3C` 直接读取”搜索 fight_value，范围太窄。BattleValueInfo 源码确认了字段布局：

```cpp
// modules\CreatureDialog.inc.cpp
char* table = *(char**)0x6747B0;
return *(int*)(table + creature_id * 0x74 + 0x3C);
```

`deps\homm3.h` 中 `_CreatureInfo_` 字段顺序为：

```text
_CreatureInfo_ +0x3C = fight_value
_CreatureInfo_ +0x40 = AI_value
_CreatureInfo_ +0x4C = hit_points
_CreatureInfo_ +0x50 = speed
```

`_BattleStack_` 中 `_CreatureInfo_ creature` 起始于 `+0x74`，因此：

```text
_BattleStack_ +0xB0 = creature.fight_value
_BattleStack_ +0xB4 = creature.AI_value
_BattleStack_ +0xC0 = creature.hit_points
_BattleStack_ +0xC4 = creature.speed
```

这意味着：战场 AI 若操作的是 `_BattleStack_`，应重点搜索 `+0xB0`，或搜索“先定位 `_BattleStack_ + 0x74` 的 `_CreatureInfo_`，再访问 `+0x3C`”的组合，而不能只搜 `*(0x6747B0) + creature_id * 0x74 + 0x3C`。

已确认的 `H3BattleValueInfo` 使用点：

- 生物信息窗口：`GetCreatureFightValueById()` 读取全局表 `+0x3C`，显示 `fight_value * count`。
- 远程力量对比：`Hook_RangedPower()` 遍历 `mgr->stack[2][21]`，对 `count_current > 0 && creature.shots > 0` 的 stack 累加 `s.creature.fight_value * s.count_current`。这里是从 `_BattleStack_` 内嵌 `_CreatureInfo_` 读取同一字段。

## 十二、新证据

- `0x469C50` 中存在明显的“区间搬移 + 插入”逻辑：
  - `call 0x00617492` 申请/扩展空间；
  - `cmp edi, eax` / `cmp ecx, edx` 驱动搬移；
  - 说明排序结果不是单点 `cmp`，而是容器级插入维护。
- `0x469BC0` 的 `cmp eax, ecx`、`je 0x469c40` 等只是函数内局部检查，不是 score 比较主分支。

## 十三、修改的笔记文件

- `D:\GitHub\H3\H3Note\战斗AI价值评估逆向笔记.md`
