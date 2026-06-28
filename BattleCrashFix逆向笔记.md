# 逆向笔记 — BattleCrashFix

本项目集中修复英雄无敌3 SoD HD Mod 战斗中的已确认崩溃问题。

当前包含两个修复：

1. `[Obstacle]` 驱除障碍 / RemoveObstacle 二次移除崩溃
2. `[Aura]` 独角兽抗魔光环与被丧心病狂/蛊惑单位交互崩溃

---

# [Obstacle] 驱除障碍崩溃

## 关键地址

| 地址 | 函数/用途 |
|------|----------|
| 0x466710 | `RemoveObstacle(CombatManager*, int ObstacleNum)` — thiscall |
| 0x466813 | RemoveObstacle 内 `mov ecx,[edi]`（读取 obstacle.def） |
| 0x466815 | `mov edx,[ecx]`（读 DEF 虚表）— 崩溃点 |
| 0x466817 | `call [edx+4]`（DEF->Release） |
| 0x46681A | `mov [edi],0`（置 def=NULL），函数即将返回 |
| 0x466826 | `ret 4` — 函数返回 |
| 0x475800 | 战斗回合障碍物清理函数 |
| 0x475A90 | 清理循环体：检查 duration，递减，到 0 调用 RemoveObstacle |
| 0x5A0140 | `CastSpell` — 施法总函数 |
| 0x59FE50 | 检查 hex 障碍位 → 调用 RemoveObstacle |
| 0x59FFE0 | 类似 0x59FE50 的另一个路径 |
| 0x5A1A00 | CastSpell 内部遍历障碍物循环（有 def NULL 检查） |
| 0x5A1FC3 | CastSpell 内另一个 RemoveObstacle 调用点 |
| 0x5A2011 | CastSpell 内另一个 RemoveObstacle 调用点 |

## RemoveObstacle 调用者（5 处）

| 地址 | 说明 |
|------|------|
| 0x475ABF | 战斗回合清理（duration 到期移除）— **无 def NULL 检查** |
| 0x59FF5E | 函数 0x59FE50 内（被 0x46A150 调用） |
| 0x5A1A5D | CastSpell 内障碍物遍历（**有 def NULL 检查**） |
| 0x5A1FC3 | CastSpell 内（Force Field 移除路径） |
| 0x5A2011 | CastSpell 内（投石机/地震路径） |

## H3Obstacle 结构（0x18 = 24 字节）

| 偏移 | 类型 | 字段 |
|------|------|------|
| +0x00 | DWORD | def（H3LoadedDef*） |
| +0x04 | DWORD | info（H3ObstacleInfo*） |
| +0x08 | BYTE | anchorHex |
| +0x09 | BYTE | ownerSide |
| +0x0A | BYTE | featureTriggered |
| +0x0B | padding | — |
| +0x0C | DWORD | featureDamage |
| +0x10 | DWORD | featureDuration |
| +0x14 | DWORD | animationIndex |

## RemoveObstacle 执行流程

1. 参数检查：ObstacleNum < 0 → 返回
2. 边界检查：ObstacleNum >= vector.size() → 返回
3. 遍历 obstacleInfo 的 relativeCells，清除每个 hex 的 obstacleBits/obstacleIndex
4. 清除 anchorHex 的 obstacleBits bit 0（anchor 位）
5. **读取 obstacle.def，调用 Release，置 def=NULL**
6. 返回

**不清除的字段**：info、anchorHex、featureDamage、featureDuration、animationIndex

## H3CombatSquare（hex）障碍位

| 位 | 含义 |
|----|------|
| 0x01 | anchor |
| 0x02 | localObstacle |
| 0x04 | quicksand |
| 0x08 | landMine |
| 0x10 | firewall |
| 0x20 | forcefield（也设置 localObstacle → 0x22） |

## 崩溃机制

```text
Force Field 施放 → obstacle 条目创建，duration=N
  ↓
玩家施放 Remove Obstacle → RemoveObstacle 调用
  → 清除 hex bits
  → def->Release()，def=NULL
  → duration 不变（仍为 N）
  ↓
回合清理循环 → 发现 duration > 0 → 递减
  ↓
duration 到 0 → 再次调用 RemoveObstacle
  → mov ecx,[edi] = NULL
  → mov edx,[ecx]    ← 崩溃！访问地址 0x00000000
```

## 魔法障碍物 Spell ID

| ID | 名称 |
|----|------|
| 10 | Quicksand（流沙） |
| 22 | Land Mine（地雷） |
| 23 | Force Field（力场） |
| 24 | Fire Wall（火墙） |
| 34 | Remove Obstacle（驱除障碍） |
| 35 | Dispel（驱散） |

## CombatManager 中 obstacleInfo 的偏移

- `+0x13D5C`：H3Vector begin pointer
- `+0x13D60`：H3Vector end pointer
- `+0x13D64`：H3Vector endCapacity pointer

> ⚠️ 曾因代码写成 `+0x13D58/+0x13D5C`（提前 4 字节）导致力盾/火墙/流沙无法消失。反汇编确认正确偏移为 `+0x13D5C/+0x13D60`。

H3Vector 元素大小 = 0x18（24 字节，即 sizeof(H3Obstacle)）。

## 清理循环逻辑（0x475A70 区域）

```text
edi = obstacleInfo.begin
loop:
  if edi == obstacleInfo.end → break
  eax = obstacle.duration (+0x10)
  if eax <= 0 → skip, next
  dec eax
  obstacle.duration = eax
  if eax != 0 → skip_remove, next
  // duration 到 0
  call RemoveObstacle(obstacle_index)
  // 检查 animationIndex，清理动画
  ...
  edi += 0x18
  goto loop
```

**注意**：清理循环**没有**检查 obstacle.def 是否为 NULL。

## 当前修复

- **HiHook SPLICE_ THISCALL_** 包裹 `RemoveObstacle @ 0x466710`（整个函数，非内部 LoHook）
- 标签：`[Obstacle]`
- 行为：包裹原函数，调用前检查 obstacle 的 def 有效性
  - 若 `def == NULL` 或不可读，清除 `duration=0`，跳过原函数
  - 若有效，正常调用原函数

---

# [Aura] 独角兽抗魔光环崩溃

## 用户复现场景

- 独角兽挨着己方部队
- 该己方部队处于「丧心病狂」状态
- 此时一定崩溃

中文版本中：

| Spell ID | 名称 |
|----------|------|
| 59 | 丧心病狂 / Berserk |
| 60 | 蛊惑 / Hypnotize |

## 关键地址

| 地址 | 函数/用途 |
|------|----------|
| 0x43E790 | `UpdateAuraLinks`，建立独角兽抗魔光环关联 |
| 0x43E800 | 检查相邻单位 type == 24（Unicorn） |
| 0x43E805 | 检查相邻单位 type == 25（War Unicorn） |
| 0x43E80E | 读取相邻独角兽 `activeSpellsDuration[60]`（蛊惑持续时间） |
| 0x43E818 | 独角兽被蛊惑时取 `1 - side` |
| 0x43E827 | 独角兽未被蛊惑时取自身 side |
| 0x43E82D | 与 target side 比较，判断是否为友军 |
| 0x43E843 起 | 处理独角兽侧 spellsData vector |
| 0x43E870 起 | 处理 target 侧 spellsData vector |

## H3CombatMonster 相关偏移

| 偏移 | 含义 |
|------|------|
| +0x34 | creature type |
| +0x38 | battlefield hex position |
| +0x84 | flags / state bits |
| +0xF4 | side |
| +0x198 | activeSpellsDuration 数组起点 |
| +0x284 | activeSpellsDuration[59]，丧心病狂/Berserk |
| +0x288 | activeSpellsDuration[60]，蛊惑/Hypnotize |
| +0x514 | spellsData 中一个关联 vector |
| +0x524 | spellsData.hypnotized / 关联 vector |

## `UpdateAuraLinks` 行为

入口：

```text
0x43E790:
  ecx = target monster
  edi = ecx
```

主要逻辑：

1. 根据 target 占用情况，遍历周围 6 或 8 个方向
2. 取相邻 hex 上的 monster
3. 如果相邻单位是 Unicorn(24) 或 War Unicorn(25)：
   - 如果独角兽自身被蛊惑，则使用 `1 - unicorn.side`
   - 否则使用 `unicorn.side`
4. 与 target.side 比较，判断是否为友军
5. 若通过，建立双向关联：
   - 将 target 加入独角兽侧 vector
   - 将独角兽加入 target 侧 vector

## 崩溃机制（已确认）

### 崩溃点

- 实际崩溃地址：`0x43E744`（函数 `0x43E720` = Vector::FindAndRemove）
- 调用链：`0x441CC0`（清理/更新关联）→ 操作 `monster.+0x524` vector → `0x43E720`
- 崩溃时寄存器：`EDI = 0xFFFFFFFC`（vector 内部指针损坏）

### 根因

UpdateAuraLinks 维护独角兽与相邻友军之间的双向关联（`_f_514` / `_f_524` vectors）。当单位被丧心病狂(Berserk)或蛊惑(Hypnotize)时：

1. 单位的 side/行为改变，但旧的关联仍残留在 vectors 中
2. 清理函数（0x441CC0）尝试操作这些不一致的 vector 数据
3. vector 内部指针损坏 → 访问非法地址崩溃

### 双格兵因素

独角兽本身是双格兵（占两个 hex）。被丧心病狂的单位如果也是双格兵，关联条目更多，残留脏数据更容易触发崩溃。函数 `0x5242E0`（获取相邻 hex）已通过 `+0x84 bit 0` 和 `+0x44`（朝向/第二格）考虑双格兵，但这不能解决关联残留问题。

### 原版函数的不足

- 原函数只特殊处理了**独角兽自身被蛊惑(60)**时的 side 翻转
- **没有处理 target 被丧心病狂(59)/蛊惑(60)**时的情况
- 被丧心病狂的 target 仍按普通友军逻辑建立关联 → 行为不一致 → 崩溃

## 关联数据结构（H3API 确认）

H3CombatCreature (H3CombatMonster) 中的光环关联 vectors：

| 偏移 | 类型 | 字段 |
|------|------|------|
| +0x514 | H3Vector<ptr> | `_f_514` — 受此独角兽保护的单位列表（独角兽侧） |
| +0x518 | DWORD | _f_514.end |
| +0x51C | DWORD | _f_514.endCapacity |
| +0x524 | H3Vector<ptr> | `hypnotized` — 另一个关联列表 |
| +0x528 | DWORD | hypnotized.end |
| +0x52C | DWORD | hypnotized.endCapacity |
| +0xFC | DWORD | target 侧记录的保护者独角兽指针 |

H3Vector 布局：begin(+0), end(+4), endCapacity(+8)，各 4 字节，共 12 字节。

## UpdateAuraLinks 详细逻辑

### 入口
```
ecx = target monster（被检查的单位）
edi = ecx = target
```

### 方向数量计算
```
bl = [target+0x84] & 1   // 双格兵 flag bit 0
if (bl) → 方向数 = 8
else    → 方向数 = 6
```

### 第一段（0x43E800-0x43E8AD）：以 target 为中心找邻居独角兽

1. 调用 `0x5242E0`(target, position_hex, direction_count) 获取相邻 hex 列表
2. 调用 `0x527233` 获取 hex 上的 monster → esi = 邻居
3. 检查邻居 type：
   - type == 24 (Unicorn) 或 25 (War Unicorn) → 是独角兽
4. **独角兽被蛊惑时的 side 翻转**：
   - 读 `unicorn.activeSpellsDuration[60]`（Hypnotize）
   - 若 > 0：effective_side = 1 - unicorn.side（翻转）
   - 否则：effective_side = unicorn.side
5. 比较 effective_side 与 target.side
6. 若 side 匹配且 flags 通过：
   - `target.+0xFC = unicorn`（记录保护者）
   - 将 target 加入 `unicorn._f_514`（若尚未存在）
   - 将 unicorn 加入 `target._f_524`（若尚未存在）

### 第二段（0x43E8AF-0x43E960）：角色互换

类似第一段，但方向相反。可能是以另一个单位为中心重新检查。

## 施法函数 0x444610

`monster::SetSpellDuration(spellId, ...)`

- 调用约定：thiscall(ecx = monster*)
- `[ebp+8]` = spellId
- `[ebp+0C]` = duration（可选，某些 spell case 不用）
- `ret 10h`（4 个参数，共 16 字节）

### Spell 处理跳转表

函数内根据 `spellId - 47`（范围 0-25，即 spell 47-72）查表跳转：

索引表 @ `0x4450D8`（每项 1 字节 case 编号）→ 跳转表 @ `0x4450CC`（每项 4 字节绝对地址）

| Spell | ID | Case | Duration 设置 |
|------|-----|------|-------------|
| Berserk | 59 | 0 | 强制 255 (0xFF) |
| Hypnotize | 60 | 2 | 设为 1 |
| Frenzy | 56 | 1 | 计算值 |
| 大多数 spell | 47-72 | 2 | 设为 1 |

### 关键写入
```
0x44468E: mov [esi + ebx*4 + 0x198], eax  // 写 duration
0x4446A6: mov [esi + ebx*4 + 0x2DC], eax  // 写 caster power
```
其中 esi = monster，ebx = spellId，eax = duration。

## 当前修复策略（已验证 v3）

### 尝试过的方案

| 版本 | 方案 | 结果 |
|------|------|------|
| v1 | 入口 hook (0x43E790) 跳过被丧心病狂/蛊惑 target | 有一定效果，但旧关联残留导致崩溃 |
| v2 | 入口 hook + 施法 hook (0x444610) + ClearAuraLinks 遍历 vectors | ClearAuraLinks 遍历 vector 导致卡死 (AppHangTransient) |
| v2.1 | v2 + 循环次数限制 (safety<20) | 治标不治本，用户否决 |
| v2.2 | 入口 hook + 内部 hooks (0x43E811, 0x43E8BC) | LoHook 在函数内部安装 trampoline 异常，导致崩溃在 0x43E80E |
| **v3 (当前)** | **入口 hook + 崩溃点 FindAndRemove 保护** | **✅ 已验证有效** |

### v3 三个 Hook

#### Hook 1: [Obstacle] @ 0x466710（HiHook SPLICE_ THISCALL_）

包裹整个 `RemoveObstacle` 函数。调用原函数前检查 obstacle 的 def 有效性；无效则清除 duration 并跳过。

#### Hook 2: [Aura] @ 0x43E790（HiHook SPLICE_ THISCALL_）

- 若 target 的 `activeSpellsDuration[59] > 0`（丧心病狂/Berserk）或 `activeSpellsDuration[60] > 0`（蛊惑/Hypnotize），跳过整个 UpdateAuraLinks
- 作用：防止丧心病狂/蛊惑期间建立新的错误关联

#### Hook 3: [Vector] @ 0x43E720（HiHook SPLICE_ FASTCALL_）

在 Vector::FindAndRemove 函数入口检查 vector 数据有效性：
- begin/end/endCapacity 全为零 → 安全返回
- begin 或 end < 0x10000 → 无效地址，安全返回
- end > endCapacity → 数据不一致，安全返回
- 元素数 (end-begin)>>2 > 40 → 超出合理范围，安全返回

**实测结果**：日志中反复触发 `begin=有效 end=0x00000000` 的拦截，正是旧关联残留导致的不一致 vector。通过安全跳过避免了崩溃。

### 为什么不需要施法 hook

- 入口 hook 阻止建立新关联 ✅
- 旧关联残留在 vectors 中，但 FindAndRemove 保护拦截了崩溃 ✅
- 魔法结束后 UpdateAuraLinks 正常执行，自动重建正确关联 ✅

## 日志区分

- `[Obstacle]`：驱除障碍/RemoveObstacle 修复
- `[Aura]`：UpdateAuraLinks 入口跳过被丧心病狂/蛊惑单位
- `[Vector]`：FindAndRemove vector 有效性保护
- `[Init]`：插件启动和 hook 注册

## 逆向笔记补充

### Vector::FindAndRemove (0x43E720)

- 调用约定：thiscall(ecx = vector 结构指针)
- 参数2 (edx) = 要查找/移除的值
- 逻辑：
  1. esi = [ecx+4]（end）
  2. eax = [ecx+8]（endCapacity）
  3. count = (endCapacity - end) >> 2
  4. 从后往前搜索匹配值
  5. 找到则移除

- 崩溃时：EDI = 0xFFFFFFFC（vector 内部指针损坏后计算出的无效地址）
- 调用者：0x441CC0（清理/更新关联函数），操作 monster.+0x524 vector

### LoHook 在函数内部使用的限制

HD Mod 的 LoHook 在**函数边界**（标准 prologue: push ebp; mov ebp,esp）安装 trampoline 可靠。但在**函数内部**的任意指令上安装时，trampoline 的指令长度分析可能出错，导致 CPU 跳转到指令中间执行。

实测：在 0x43E811 和 0x43E8BC 安装 LoHook 后，崩溃在 0x43E80E（jne 指令的第 4 字节），且 hook 函数从未被触发（日志无记录）。结论：避免在函数内部使用 LoHook。
