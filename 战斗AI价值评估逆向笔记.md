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

## 十四、战场伤害/价值评估中的攻防加成（已确认）

> 目标：确认“每支部队的总战斗价值是否会受到英雄/生物攻防加成”。本节只记录反汇编已经看到的字段与公式，不把未追完的函数命名为最终 AI 目标分数。

### 1. `_BattleStack_` 构造时复制基础生物表字段

`0x43D450` 构造/初始化 `_BattleStack_` 时，会从全局生物表复制整条 `_CreatureInfo_` 到 `stack + 0x74`：

```asm
0x0043d463  mov dword [ebx + 0x34], eax      ; creature_id
0x0043d466  mov dword [ebx + 0x4c], ecx      ; count_current
0x0043d477  mov ecx, dword [0x6747b0]        ; creature table
0x0043d47f  lea edi, [ebx + 0x74]            ; stack.creature
0x0043d488  lea esi, [edx + ecx]
0x0043d48b  mov ecx, 0x1d                    ; 29 dwords = 0x74 bytes
0x0043d490  rep movsd                        ; copy _CreatureInfo_
```

因此 `stack + 0xB0` 确认为 `stack.creature.fight_value`，但这里是整条生物信息复制，不是 AI 评分公式。

### 2. 攻防修正字段的位置

`0x4E6390` 会把英雄/特长/状态等加成写入 `_BattleStack_` 的攻击、防御、伤害等派生字段，确认写点：

```asm
0x004e63bd  mov edx, dword [esi + 0x54]
0x004e63c0  add edx, eax
0x004e63c2  mov dword [esi + 0x54], edx      ; 攻击加成累加
0x004e63e1  mov ecx, dword [esi + 0x58]
0x004e63e4  add ecx, eax
0x004e63e6  mov dword [esi + 0x58], ecx      ; 防御加成累加
...
0x004e648d  mov edx, dword [esi + 0x54]
0x004e6498  mov dword [esi + 0x54], edx
0x004e649b  mov edx, dword [edi + 0xc]
0x004e64a0  mov dword [esi + 0x58], eax
0x004e64a8  mov eax, dword [esi + 0x60]
0x004e64b3  mov dword [esi + 0x60], eax
```

结合 `deps\homm3.h` 中 `_BattleStack_` 字段布局：

```text
stack +0xC8 = creature.attack     ; 生物基础攻击
stack +0xCC = creature.defence    ; 生物基础防御
stack +0xD0 = creature.damage_min
stack +0xD4 = creature.damage_max

stack +0x54 / +0x58 / +0x5C / +0x60 是战斗中用于派生攻防/伤害的字段；0x4E6390 会累加英雄/特长/状态带来的修正。
```

### 3. 伤害估算函数会读取派生攻防字段

`0x443C60` 是 `_BattleStack_::Calc_Damage_Bonuses` 包装入口；它先调用 `0x443560`，后续再乘其它倍率。`0x443560` 先调用 `0x443040` 得到基础伤害估计。

`0x443040` 中确认会调用：

```asm
0x004430b5  mov ecx, dword [ebp + 0xc]
0x004430b8  push ecx
0x004430b9  push edi
0x004430ba  mov ecx, ebx
0x004430bc  call 0x442130                  ; 取攻击方攻击值
0x004430c1  push 1
0x004430c3  push ebx
0x004430c4  mov ecx, edi
0x004430c8  call 0x4422b0                  ; 取防御方防御值
0x004430cd  cmp esi, eax
0x004430d1  sub esi, eax                   ; 攻防差
```

`0x442130` 以攻击方 stack 为 `ecx`，直接读取：

```asm
0x0044213d  mov ebx, dword [esi + 0xc8]    ; 基础 attack
...
0x00442148  mov eax, dword [esi + 0x248]
0x00442152  mov eax, dword [esi + 0x468]
0x0044216a  add ebx, eax                   ; 状态修正
```

`0x4422B0` 以防御方 stack 为 `ecx`，直接读取：

```asm
0x004422d2  mov ebx, dword [edi + 0xcc]    ; 基础 defence
...
0x004422e8  fild dword [ebp + 0xc]
0x004422f1  fmul dword [0x63b8b0]
0x00442307  fmul dword [0x63b8ac]
```

`0x443040` 中的攻防差参与伤害估算：

```asm
0x004430d1  sub esi, eax                   ; attack_total - defence_total
0x004430dc  fld qword [ebp - 0x1c]
0x004430df  fmul qword [0x63ac58]          ; 常量 0.05
0x00443106  fild dword [ebp + 8]           ; base damage
0x0044310f  fmul qword [ebp - 0x1c]
0x00443118  fadd qword [ebp - 0x2c]
0x0044311b  call 0x617f94                  ; round
```

已确认的核心公式形态：

```c
attack_total = attacker.creature.attack + attacker战斗修正;
defence_total = defender.creature.defence + defender战斗修正;
diff = attack_total - defence_total;

if (diff > 0) {
    // 反汇编确认正向分支按 0.05 * diff 增伤，并有上限钳制到 3.0 倍附近
    damage = round(base_damage + base_damage * min(diff * 0.05, 3.0));
}
```

注意：本节确认的是**伤害估算/伤害加成算法读了战斗中的总攻防**。这可以解释“AI 对一支部队的价值/威胁评估会间接受英雄攻防影响”的路径：AI 如果用 `0x443C60/0x443560/0x443040` 估算打击收益，则已包含攻防修正。

### 4. 当前仍未确认的点

- 还没有确认“战场目标选择最终 score 直接读取 `fight_value(+0x3C)`”。
- 已确认的 `_BattleStack_ +0xB0` 读点中，`0x41A8AA`、`0x407937`、`0x457790` 分别属于显示/对象释放/资源显示链路，不是目标选择评分。
- `0x477940` 在战场 AI 行动链路中按数量累加全局生物表 `+0x38` 字段，不是 `fight_value(+0x3C)`。
- `0x469F30` 在战场威胁评估中读取全局生物表 `+0x4C`（hit_points），并乘以数量/差值，不是 `fight_value(+0x3C)`。

## 十五、候选收益值的数据类型与排序方式（阶段性确认）

### 1. score 的存储类型

`0x469C50` 中每个候选条目是 **8 字节结构**：

```text
[offset +0x00] DWORD  目标/槽位标识（或目标指针/索引）
[offset +0x04] DWORD  目标关联数据（第二个字段）
```

在插入时，函数反复执行：

```asm
mov eax, [ebp - 0x1c]
mov edx, [ebp - 0x18]
mov [edi], eax
mov [edi + 4], edx
```

这说明候选信息不是单纯的 `int score` 数组，而是**两个 DWORD 组成的条目**。当前能确认的是：它们以 8 字节为单位搬移、插入、压缩。

> 注意：目前还没有在这段里直接读出“哪个 DWORD 就是收益分数”，因此不要把这两个 DWORD 直接等同为 score+target；这里只能确认它们是容器条目字段。

### 2. 结果排序不是“遍历找最大”，而是有序插入

`0x469C50` 的后半段没有看到完整的“扫描完再 `if (score > best)`”模式，而是：

- 通过 `call 0x617492` 扩容；
- 通过 `call 0x4af570` / `0x522af0` 进行区间搬移；
- 通过 `call 0x4af240`、`call 0x46ad50` 维护容器边界；
- 通过 `cmp edi, eax` / `cmp eax, edi` / `sar ecx, 3` 这些位置关系判断插入点。

因此目前更稳妥的结论是：

```text
候选不是“最后再找最大值”，而是在生成过程中就保持某种有序状态；
最终从排序后的首项/优先项取目标。
```

### 3. 收益值的具体数值类型

已确认：

- 伤害估算函数 `0x443040` / `0x443560` / `0x443C60` 的中间结果经过 `call 0x617f94`，返回值是 **int**（四舍五入后的整数伤害）。
- `0x469F30` 的威胁评估中，最终 `call 0x617f94` 之后把结果写回 `[ecx]`，也是 **int**。

未确认：

- `0x469C50` 自身的候选条目第二个 DWORD 是否就是 score；
- 容器内部比较函数到底比较的是 int、符号位拼接值，还是别的打包格式。

### 4. 当前可写成的阶段性伪代码

```c
// 0x469C50：对每个候选槽位生成/更新条目并插入有序容器
for each candidate_slot:
    if slot invalid: continue
    if !passes_filter(candidate): continue

    entry = { field0, field1 }   // 8-byte item
    insert_into_sorted_container(entry)

// 最终选择：从容器前端/优先项取一个目标
best = container.first()
attack(best)
```

### 5. 目前不能写死的结论

- 不能写成“score = float”；证据显示中间和最终结果都被 `round` 成 int。
- 不能写成“best by max loop”——当前看到的是插入排序/容器有序维护。
- 不能写死 `field0/field1` 哪个是 score，哪个是目标标识；需要再看 `0x4afa00`、`0x617492`、`0x46ad50` 或容器内部比较逻辑。

