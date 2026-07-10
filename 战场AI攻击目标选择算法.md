# 英雄无敌3 战场 AI 攻击目标选择（逆向记录）

> 只记录已通过反汇编确认的事实。未确认的标注为"待验证"。

## 已确认的调用链

| 地址 | 功能 |
|------|------|
| 0x476DA0 | 战场 AI 回合决策主函数 |
| 0x469F30 | 威胁评估（使用 hit_points +0x4C） |
| 0x469B00 | 当前 stack 状态/动作准备 |
| 0x469BC0 | 候选整理/过滤 |
| 0x469C50 | 候选生成 + 有序容器插入 |
| 0x41B440 | 8字节条目数组容器维护（搬移/插入/压缩） |
| 0x4E32E0 | 合法性/可行性过滤 |
| 0x4E2FC0 | 候选删除/压缩 |
| 0x4AF570 | 区间搬移（memmove 封装） |
| 0x522AF0 | 带计数区间搬移 |
| 0x4AF240 | 空操作（ret 8） |
| 0x46AD50 | 返回容器元素个数 |

## 0x476DA0 中从生物表读取的字段

在 0x476DA0 函数体内，生物表指针 `*(0x6747B0)` 被加载后，只访问了 `+0x4C`（hit_points）：

- `0x476F06: mov ecx, [0x6747B0]`
- `0x476F1E: mov ecx, [ecx + eax*4 + 0x4C]` → hit_points
- `0x476F5D: mov edx, [0x6747B0]`
- `0x476F63: mov eax, [edx + eax*4 + 0x4C]` → hit_points

## BattleValueInfo 中 fight_value 的来源（源码确认）

`D:\GitHub\H3\H3BattleValueInfo` 里显示的 **Fight Value** 不是 `AI_value(+0x40)`，而是 `_CreatureInfo_::fight_value`。

源码证据：

- `deps\homm3.h` 的 `_CreatureInfo_` 字段顺序中：
  - `fight_value` 位于 `_CreatureInfo_ + 0x3C`；
  - `AI_value` 位于 `_CreatureInfo_ + 0x40`；
  - `_CreatureInfo_` 条目大小为 `0x74`。
- `modules\FightValue.inc.cpp` 的 `GetCreatureFightValueById()` 明确读取：

```cpp
char* table = *(char**)0x6747B0;
return *(int*)(table + creature_id * 0x74 + 0x3C);
```

因此，BattleValueInfo 插件里显示的单只生物 fight value 来源是：

```text
*(int*)(*(char**)0x6747B0 + creature_id * 0x74 + 0x3C)
```

`_BattleStack_` 内部嵌入了一份 `_CreatureInfo_ creature`，起始偏移为 `+0x74`。所以从 `_BattleStack_` 指针看：

| 字段 | `_CreatureInfo_` 偏移 | `_BattleStack_` 偏移 |
|------|----------------------|----------------------|
| fight_value | `+0x3C` | `+0xB0` |
| AI_value | `+0x40` | `+0xB4` |
| hit_points | `+0x4C` | `+0xC0` |
| speed | `+0x50` | `+0xC4` |

这修正了此前只按“全局生物表 `+0x3C` 直接访问”搜索的局限：战场代码如果操作的是 `_BattleStack_`，可能会读取 `stack + 0xB0`，而不是重新从 `0x6747B0` 全局表读取 `creature_id * 0x74 + 0x3C`。

## 0x43AC50 读取的字段

- `0x43AC50: mov ecx, [0x6747B0]`
- `0x43AC56: mov esi, [ecx + edx*4 + 0x4C]` → hit_points(+0x4C)
- `0x43AC64: imul eax, [ebx + 0x4C]` → hit_points

**0x43AC50 读取的是 hit_points，不是 fight_value。**

## 0x42DBFC 读取的字段（战略层军队价值评估）

- `0x42DBF4: mov eax, [0x6747B0]`
- `0x42DBFC: imul ecx, [eax + edx*4 + 0x40]` → **AI_value(+0x40)**

## fight_value(+0x3C) 的全局搜索结果

### 搜索方法

1. 全局搜索生物表指针 `0x6747B0` 的所有引用（`mov eax/ecx/edx, [0x6747B0]`），共找到约 90 处。
2. 在这些引用中，搜索 `[base + creature_id * 0x74 + 0x3C]` 的访问模式。
3. x86 编码：`[reg + idx*4 + 0x3c]` 对应的字节序列（如 `8b44813c`、`8b4c813c` 等）。

### 结果

**没有找到任何通过全局生物表 `*(0x6747B0) + creature_id * 0x74 + 0x3C` 直接读取 fight_value 的原版 exe 代码。**

注意：这只说明“没有命中全局生物表直读模式”，不等于 fight_value 不被战场代码使用。战场内更常见的对象是 `_BattleStack_`；若从 `_BattleStack_` 读取同一字段，偏移应为 `+0xB0`。

### 待验证

- 继续追踪战场 AI 链路中是否存在 `_BattleStack_ + 0xB0` 或先取 `_BattleStack_ + 0x74` 后访问 `_CreatureInfo_ + 0x3C` 的读取。
- 用 x32dbg 对具体战场中某个 stack 的 `+0xB0` 设硬件读断点，可以直接确认战场 AI 是否读了该 stack 的 fight_value。

## 生物表访问模式说明

生物表条目大小 = 0x74 字节。

代码中使用的寻址公式：

```
lea edx, [creature_id * 8]    ; edx = creature_id * 8
sub edx, creature_id           ; edx = creature_id * 7
lea eax, [creature_id + edx*4]; eax = creature_id + creature_id*28 = creature_id*29
; 最终地址 = base + creature_id * 29 * 4 + offset = base + creature_id * 0x74 + offset
```

所以 `[base + eax*4 + 0x4C]` = `base + creature_id * 0x74 + 0x4C` = hit_points。
同理 `[base + eax*4 + 0x40]` = AI_value。
而 `[base + eax*4 + 0x3C]` = fight_value —— **但这个模式在全局搜索中没有命中**。

## 战场代码段（0x46xxxx-0x47xxxx）中生物表引用

以下地址加载了生物表指针，但访问的都不是 +0x3C：

| 地址 | 访问的偏移 | 对应字段 |
|------|-----------|---------|
| 0x46468B | +0x14, +0x18 | UI 相关（名称？） |
| 0x464895 | +0x14, +0x18 | UI 相关 |
| 0x465249 | +0x14 | UI 相关 |
| 0x4652EB | +0x18 | UI 相关 |
| 0x46582C | +0x08 | 城镇类型 |
| 0x46687A | +0x0C | 资源相关 |
| 0x464A84 | +0x14, +0x18 | UI 相关 |
| 0x476F06 | +0x4C | hit_points |
| 0x476F5D | +0x4C | hit_points |

**战场代码段中没有找到直接访问生物表 fight_value(+0x3C) 的证据。**

## 补充：总战斗价值与英雄攻防加成的已确认链路

### 1. `fight_value(+0x3C)` 不是目前已确认的目标选择直接字段

继续搜索 `_BattleStack_ +0xB0` 和全局生物表 `+0x3C` 后，当前确认结果是：

- 未在战场目标选择主链中确认直接读取 `fight_value(+0x3C)`。
- 已命中的 `_BattleStack_ +0xB0` 读点（如 `0x41A8AA`、`0x407937`、`0x457790`）属于显示/析构/资源相关上下文，不是目标评分。
- `0x477940` 位于战场 AI 行动链路附近，但它累加的是生物表 `+0x38 * count`，不是 `+0x3C`。
- `0x469F30` 的威胁评估读取的是生物表 `+0x4C`（hit_points），不是 `fight_value`。

### 2. 确认存在“受英雄/状态攻防影响”的伤害估算链

虽然尚未确认 `fight_value` 参与最终目标排序，但已确认战场伤害估算会读取战斗中的总攻击/总防御：

```text
0x443C60  Calc_Damage_Bonuses 包装入口
  -> 0x443560
    -> 0x443040  基础伤害估算
      -> 0x442130  取攻击方 attack_total
      -> 0x4422B0  取防御方 defence_total
```

关键指令：

```asm
0x0044213d  mov ebx, dword [esi + 0xc8]    ; attacker 基础 attack
0x004422d2  mov ebx, dword [edi + 0xcc]    ; defender 基础 defence
0x004430d1  sub esi, eax                   ; attack_total - defence_total
0x004430df  fmul qword [0x63ac58]          ; 0.05
0x0044310f  fmul qword [ebp - 0x1c]        ; base_damage * multiplier
```

`0x4E6390` 会把英雄/特长/状态等加成累入 stack 的派生攻防/伤害字段：

```asm
0x004e63bd  mov edx, dword [esi + 0x54]
0x004e63c0  add edx, eax
0x004e63c2  mov dword [esi + 0x54], edx
0x004e63e1  mov ecx, dword [esi + 0x58]
0x004e63e4  add ecx, eax
0x004e63e6  mov dword [esi + 0x58], ecx
```

因此可确认的算法形态是：

```c
attack_total  = attacker.creature.attack  + 战斗中攻击修正;
defence_total = defender.creature.defence + 战斗中防御修正;
diff = attack_total - defence_total;

if (diff > 0) {
    damage = round(base_damage + base_damage * min(diff * 0.05, 3.0));
}
```

这说明：如果 AI 目标评估使用这条伤害估算链，那么评估结果会受英雄/状态攻防影响。这里不要写成“fight_value 本身被英雄攻防修正”；目前确认的是**伤害估算链受攻防修正影响**。

