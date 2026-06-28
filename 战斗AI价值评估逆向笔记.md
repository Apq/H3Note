# 战斗 AI 价值评估逆向笔记

> 基于 `D:\Heroes3\Heroes3_2026.05.01\Heroes3.exe` 反汇编确认。  
> radare2 路径：`D:\Programs\radare2-6.1.6-w64\bin\radare2.exe`  
> 本文只记录已确认事实；未确认内容明确标注为待验证。

## 一、核心结论

1. `H3BattleValueInfo` 插件显示的 **Fight Value** 不是 `hit_points`。
2. 插件显示值来自 `_CreatureInfo_ +0x3C = fight_value`，显示公式是 `fight_value * count`。
3. 原版战场 AI 当前已确认的目标评估链使用的是 `_CreatureInfo_ +0x4C = hit_points`，不是 `fight_value(+0x3C)`。
4. 当前已确认的整数评估链是：

```text
0x476DA0 -> 0x469F30 -> 0x4E4AB0 -> 0x617F94 -> 0x4E3620 -> 候选容器流程
```

5. 伤害估算链：

```text
0x443C60 -> 0x443560 -> 0x443040 -> 0x442130 / 0x4422B0
```

目前未见接入 `0x469C50 / 0x4E32E0 / 0x469F30` 的目标收益主链。

## 二、Fight Value 与 Hit Points 字段区别

`H3BattleValueInfo` 源码确认插件读取的是：

```cpp
*(int*)(*(char**)0x6747B0 + creature_id * 0x74 + 0x3C)
```

结构字段确认：

```text
_CreatureInfo_ +0x3C = fight_value
_CreatureInfo_ +0x40 = AI_value
_CreatureInfo_ +0x4C = hit_points
_CreatureInfo_ +0x50 = speed
```

`_BattleStack_` 内嵌 `_CreatureInfo_` 起点是 `+0x74`，因此从 stack 指针看：

```text
_BattleStack_ +0xB0 = creature.fight_value
_BattleStack_ +0xB4 = creature.AI_value
_BattleStack_ +0xC0 = creature.hit_points
_BattleStack_ +0xC4 = creature.speed
```

已确认插件使用点：

1. 生物信息窗口：读取全局生物表 `+0x3C`，显示 `fight_value * count`。
2. 远程力量对比：遍历战场 stack，对远程部队累加 `s.creature.fight_value * s.count_current`。

结论：插件显示的 Fight Value 与 AI 链路里已确认使用的 `hit_points(+0x4C)` 不是同一个字段。

## 三、BattleStack 初始化与 fight_value 复制

`0x43D450` 构造/初始化 `_BattleStack_` 时，从全局生物表复制整条 `_CreatureInfo_` 到 `stack + 0x74`：

```asm
0x0043d477  mov ecx, dword [0x6747b0]
0x0043d47f  lea edi, [ebx + 0x74]
0x0043d48b  mov ecx, 0x1d
0x0043d490  rep movsd
```

这证明 `stack +0xB0` 确实是 `fight_value`，但这里只是结构复制，不是 AI 评分公式。

## 四、已确认的基础评估值：0x469F30

`0x469F30` 是当前已确认的整数评估函数。它的主体逻辑是：

```text
value = 0
遍历 20 个对象槽
对有效对象累加 hit_points * 数量差/相关数量
根据状态加减固定值
如存在对应对象上下文，则乘以 0x4E4AB0 返回的倍率
用 0x617F94 转成 int
写回输出指针
```

关键指令：

```asm
0x00469f9c  imul ecx, dword [edi + esi*4 + 0x4c]
0x00469fa1  add ebx, ecx
0x00469fbf  add ebx, 0x1f4          ; +500
0x00469fdc  add ebx, 0xfffffe0c     ; -500
0x00469ff6  add ebx, 0x1f4          ; +500
0x0046a00d  call 0x4e4ab0
0x0046a018  fmul dword [arg_8h]
0x0046a01b  call 0x617f94
0x0046a026  mov dword [ecx], eax
```

当前可安全表述的公式：

```c
base_value = 0;
for each valid_slot:
    base_value += hit_points(creature) * count_related;

base_value += fixed_bonus_or_penalty; // +500 / -500

if (context_exists) {
    base_value = round_to_int(base_value * multiplier_from_0x4E4AB0);
}
```

待验证：`count_related` 的完整业务语义仍需继续细分。

## 五、倍率函数：0x4E4AB0

`0x4E4AB0` 不是伤害函数，而是状态/等级相关的浮点倍率函数。

它读取：

```text
ecx +0xDE  状态/等级字节
ecx +0x1A  分类索引
ecx +0x55  数量/规模相关字段
0x63EA58   倍率表
```

已确认 `0x63EA58` 是浮点常量表，前几项为：

```text
0.0, 0.05, 0.1, 0.15, 0.0, 0.1, 0.2, 0.3, ...
```

关键逻辑：

```asm
0x004e4ab6  mov al, byte [ecx + 0xde]
0x004e4ac1  mov edx, dword [edx*4 + 0x63ea58]
0x004e4af7  fmul dword [0x63eae4]   ; 0.05
0x004e4afd  fadd dword [0x63b6e0]   ; 1.0
0x004e4b09  fld dword [ebp - 4]
0x004e4b0c  fadd dword [0x63b6e0]   ; 最终返回倍率相关 float
```

结论：`0x469F30` 使用的倍率来自 `0x4E4AB0`，倍率表按 5% 级进。

## 六、状态/容量修正：0x4E3620

`0x476DA0` 调用 `0x469F30` 后，会把结果传入 `0x4E3620`：

```asm
0x00477070  lea ecx, [var_14h]
0x00477075  mov ecx, esi
0x00477077  call 0x469f30
0x00477087  mov edx, dword [var_14h]
0x00477095  push edx
0x00477096  call 0x4e3620
```

`0x4E3620` 读取并修正对象状态字段：

```text
edi +0x51
edi +0x55
edi +0x22
```

关键指令：

```asm
0x004e36c3  mov eax, dword [edi + 0x51]
0x004e36c6  mov ecx, dword [arg_8h]
0x004e36c9  lea edx, [eax + ecx]
0x004e36cc  cmp edx, esi
0x004e36d8  mov eax, dword [arg_ch]
0x004e36db  mov dword [edi + 0x51], esi
0x004e36e4  call 0x4da990
```

结论：`0x4E3620` 不是新的基础 score 公式，而是对 `0x469F30` 结果做状态/容量限制与回调处理。

## 七、候选生成、整理与选择

战场 AI 主链在 `0x476DA0` 中串联：

```text
0x469F30  计算基础整数评估值
0x4E3620  修正该值或相关对象状态
0x469B00  维护后续行动状态
0x469BC0  整理候选目标集合
0x469C50  生成候选并维护有序容器
```

关键调用：

```asm
0x00477077  call 0x469f30
0x00477096  call 0x4e3620
0x0047709e  call 0x469b00
0x004770a6  call 0x469bc0
0x004770b2  call 0x469c50
```

`0x469C50` 维护的是候选容器，不是基础分数公式。它处理 8 字节候选条目，过滤 `0xffffffff / 0 / 2 / 3 / 4 / 5 / 6` 等特殊值，并通过插入/搬移维护候选顺序。

已修正：候选条目的第一个 DWORD 不能直接写成 score。它更像候选目标/动作/特殊标识。

当前可写的候选条目形式：

```c
struct CandidateItem {
    int kind_or_target;  // [0]：候选标识，存在特殊值
    int aux;             // [4]：附加字段，语义待细分
};
```

## 八、伤害估算链与 score 链的区别

伤害估算链已确认：

```text
0x443C60 -> 0x443560 -> 0x443040 -> 0x442130 / 0x4422B0
```

`0x443040` 会读取攻击/防御总值，并使用攻防差影响伤害估计：

```asm
0x004430bc  call 0x442130
0x004430c8  call 0x4422b0
0x004430d1  sub esi, eax
0x004430df  fmul qword [0x63ac58]   ; 0.05
```

该链说明伤害估算会受到英雄/状态攻防修正影响，但目前未见它被 `0x469C50 / 0x4E32E0 / 0x469F30` 作为目标收益 score 主链调用。

## 九、fight_value 的 AI 用途现状

已确认：

1. 插件显示的 `fight_value` 来自 `+0x3C`。
2. `_BattleStack_ +0xB0` 是同一字段。
3. 若干 `+0xB0` 命中属于 UI/析构/资源显示链路，不是目标评分。
4. 当前 score 链明确使用 `hit_points(+0x4C)`，未见 `fight_value(+0x3C)`。

因此，截至当前证据，不能写成“战场 AI 目标收益 score 使用 fight_value”。

## 十、当前完整公式版本

当前能被证据支撑的目标评估公式链：

```text
base_value = sum(hit_points(+0x4C) * count_related)
base_value += fixed_bonus_or_penalty(+500 / -500)
base_value = round_to_int(base_value * multiplier_from_0x4E4AB0)
score_state = state_or_capacity_adjust(base_value, fields +0x51/+0x55/+0x22 via 0x4E3620)
候选目标进入 0x469B00 / 0x469BC0 / 0x469C50 容器流程
```

更短地说：

```text
目标评估值 = hit_points 相关基础值 + 固定修正，再乘状态倍率，最后经过目标状态/容量修正进入候选容器。
```

## 十一、仍待验证

1. `count_related` 的精确业务语义。
2. `0x4E4AB0` 中 `ecx+0xDE`、`ecx+0x1A`、`ecx+0x55` 的完整字段命名。
3. `0x4E3620` 中 `edi+0x51` 的具体语义。
4. 候选容器排序与 `0x469F30` 结果之间的精确耦合点。
5. 是否存在其它战场 AI 分支使用 `fight_value(+0x3C)`；当前主链未确认。

## 十二、威胁/站位分支（已撤回）

> 用户确认：目标选择 score 公式不涉及威胁/龙息方向，此前"威胁分支"判断不适用于 score 公式。  
> 以下内容保留作为参考，但不作为 score 公式的组成部分。  
> 这些函数确实在伤害估算和行动判断中存在，但与 `0x469F30` / `0x469C50` 目标选择 score 主链无关。

### 1. 0x4438B0：伤害倍率中的站位/能力修正（伤害链，非 score 链）

`0x4438B0` 会被 `0x443C60` 伤害估算链调用。该函数会检查 `_BattleStack_ +0x84` 的多个能力位，并根据站位关系多次把倍率乘以 `0.5`。

关键指令：

```asm
0x00443933  mov ecx, dword [ebx + 0x84]
0x00443939  shr ecx, 0xa
0x0044393c  test cl, 1
0x00443941  fld qword [ebp - 8]
0x00443944  fmul qword [0x63ac70]   ; 0.5

0x00443999  call 0x4670f0
0x004439a2  fld qword [ebp - 8]
0x004439a5  fmul qword [0x63ac70]   ; 0.5

0x004439b6  call 0x4671e0
0x004439bf  fld qword [ebp - 8]
0x004439c2  fmul qword [0x63ac70]   ; 0.5
```

`0x4670F0` / `0x4671E0` 是站位关系判断函数，会把 hex 编号拆成 17 列坐标，比较相对位置，并检查部分生物/状态例外。

结论：龙息/贯穿/相邻类威胁至少已经确认在**伤害估算倍率链**中体现。

### 2. 0x475DC0：AI 行动/威胁判断中的站位函数

`0x4670F0` / `0x4671E0` 除了被 `0x4438B0` 调用，也被 `0x475DC0` 调用：

```text
0x475DC0 -> 0x4670F0
0x475DC0 -> 0x4671E0
```

这说明站位/贯穿关系不只属于实际伤害结算，也进入了 AI 行动判断分支。

### 3. 0x4746B0 case 2001：另一条威胁/价值分支

`0x4746B0` 调用 `0x475DC0`，并在 case 2001 中出现另一套评估公式。该分支遍历 20 个槽位，使用全局生物表 `+0x38` 乘以数量差累计：

```asm
0x00474942  mov esi, dword [edi - 0x18]
0x00474949  mov eax, dword [edi]
0x0047494f  mov edx, dword [edi + 0x38]
0x00474952  shr edx, 0x16
0x00474955  test dl, 1
0x0047495f  lea edx, [esi*8]
0x00474970  mov esi, dword [0x6747b0]
0x00474976  mov edx, dword [esi + edx*4 + 0x38]
0x0047497a  imul edx, eax
0x0047497d  add dword [arg_8h], edx
```

随后把累计值减半，再乘 `0x4E47F0` 返回的倍率并取整：

```asm
0x0047498f  mov ecx, dword [ebx + ecx*4 + 0x53cc]
0x00474996  call 0x4e47f0
0x0047499e  cdq
0x004749a1  sar eax, 1
0x004749ac  fmul dword [arg_8h]
0x004749af  call 0x617f94
0x004749ba  mov dword [0x695080], eax
```

若该结果超过/达到外部表值，则写入行动状态和值：

```asm
0x00474a45  cmp edx, eax
0x00474a74  mov dword [ebx + 0x3c], 5
0x00474a7b  mov edx, dword [0x695080]
0x00474a81  mov dword [ebx + 0x40], edx
```

当前可写公式：

```c
threat_value = 0;
for each slot:
    if valid and flag_filter_pass:
        threat_value += creature_field_38 * count_delta;

threat_value = round_to_int((threat_value / 2) * multiplier_from_0x4E47F0);

if (threat_value >= threshold_from_ai_table) {
    ai_state = 5;
    ai_value = threat_value;
}
```

### 4. 与 0x469F30 的关系

这不是 `0x469F30` 那条 `hit_points(+0x4C)` 基础评估链，而是另一条 AI 威胁/行动价值分支。

因此当前应把目标选择相关评估拆成至少两类：

1. `0x469F30`：使用 `hit_points(+0x4C)` 的基础整数评估。
2. `0x4746B0 / 0x475DC0 / 0x4438B0`：使用站位、能力位、贯穿/龙息类关系、`field_38` 和数量差的威胁分支。

### 5. 与 fight_value 的关系

该新增威胁分支使用的是生物表 `+0x38`，不是 `fight_value(+0x3C)`。截至当前证据，仍不能写成 fight_value 直接参与该公式。
