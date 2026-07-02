# H3API.hpp 迁移方案

> 将 5 个 HoMM3 插件项目从旧 `homm3.h` + `patcher_x86.hpp` 迁移到 `H3API.hpp`

## 背景

旧 deps（base.h / homm3.h / HoMM3_*.h|cpp / patcher_x86.hpp）存在以下问题：
- 偏移定义错误（如 `power` 和 `attack` 同在 +1142）
- 手动维护、缺乏文档
- 无类型安全

H3API.hpp（1.18MB 单头库）提供：
- 完整的类型安全 C++ 封装
- 内置 patcher_x86（通过 `_H3API_PATCHER_X86_` 宏启用）
- 方法调用替代裸偏移访问（如 `hero->GetPower()`）
- 已在 H3FontExtension 项目中验证可行

## 旧→新 API 映射

### 头文件
| 旧 | 新 |
|---|---|
| `#include "homm3.h"` | `#include <H3API.hpp>` |
| `#include "HoMM3_Base.h"` | （合并入 H3API.hpp） |
| `#include "HoMM3_GUI.h"` | （合并入 H3API.hpp） |
| `#include "HoMM3_Res.h"` | （合并入 H3API.hpp） |
| `#include "HoMM3_ids.h"` | `h3::NH3Spells::eSpell` 等枚举 |
| `#include "base.h"` | （不需要） |
| `#include "patcher_x86.hpp"` | `_H3API_PATCHER_X86_` 宏 |

### Patcher
| 旧 | 新 |
|---|---|
| `Patcher* _P = GetPatcher();` | `h3::H3Patcher patcher;` |
| `PatcherInstance* _PI = _P->CreateInstance("name");` | 不需要，直接用 `H3Patcher::NakedHook5()` 等 |
| `_PI->WriteSizedHook(...)` | `patcher.NakedHook5(addr, func)` |

### 核心类型
| 旧 | 新 |
|---|---|
| `_Hero_*` | `h3::H3Hero*` |
| `_Spell_` | `h3::H3Spell` |
| `_BattleMgr_*` | `h3::H3CombatManager` |
| `_Dlg_*` | `h3::H3Dlg` |
| `_BattleStack_*` | `h3::H3BattleStack` |
| `_Creature_*` | `h3::H3Creature` |

### 全局变量
| 旧 | 新 |
|---|---|
| `o_Spell` | `h3::H3Spell::GetSpell(id)` 或 `h3::H3Spell::Get()` |
| `o_GameMgr` | `h3::H3GameManager::Get()` |
| `o_BattleMgr` | `h3::H3CombatManager::Get()` |
| `o_DD` | `h3::H3DirectDraw::Get()`（需确认） |
| `o_DDSurfaceBackBuffer` | （需确认 H3API 对应） |

### 英雄数据访问
| 旧 | 新 |
|---|---|
| `hero->power` (偏移错误) | `hero->GetPower()` → 调用 0x427650 |
| `hero->second_skill[HSS_SORCERY]` | `hero->secSkill[HSS_SORCERY]`（+0xC9） |
| `hero->spell[id]` | `hero->spells[id]`（+0x320, H3SpellsBitset） |
| `hero->GetSpell_Specialisation_Bonuses(...)` | `hero->GetSpellSpecialtyEffect(...)` |
| `*(int*)((char*)hero + 0x1a)` | `hero->id`（+0x1A） |
| `*(short*)((char*)hero + 0x55)` | `hero->level`（+0x55） |

### 法术数据
| 旧 | 新 |
|---|---|
| `o_Spell[id].eff_power` | `spell.spEffect`（+0x30） |
| `o_Spell[id].effect[level]` | `spell.baseValue[level]`（+0x34） |
| `o_Spell[id].level` | `spell.level`（+0x18） |
| 手动计算 `effect[lv] + eff_power * power` | `spell.GetBaseEffect(level, spellPower)` |

### 常量
| 旧 | 新 |
|---|---|
| `SPL_ICE_BOLT` 等（来自 HoMM3_ids.h） | `h3::NH3Spells::eSpell::ICE_BOLT` 等 |
| `HSS_SORCERY` 等 | `h3::NSSkills::eSkill::SORCERY` 等（需确认命名） |

### DirectDraw
H3API.hpp 是否封装了 DirectDraw 操作需确认。如果没有：
- 保留 `<ddraw.h>` + 手动 `LPDIRECTDRAW` 调用
- 这不影响整体迁移，DD 操作通常很少

### 兼容层策略（MegaDesc / BattleValueInfo 实践结果）

对于大量裸偏移访问的项目，不强行把所有旧类型改成 H3API 类型安全封装。实际可行策略是：

- 用 `#define _H3API_PATCHER_X86_` + `#include <H3API.hpp>` 替换旧头文件。
- 保留单翻译单元 `modules/*.inc.cpp` 结构。
- 对 `_Pcx8_`、`_Dlg_`、`_Hero_`、`_Spell_`、`_BattleMgr_`、`_BattleStack_` 等只补插件实际用到的最小兼容结构。
- 裸偏移逻辑先保留，避免一次性重写已验证算法。
- `CALL_*` 逐步替换为 `THISCALL_*`，或在兼容层中提供旧宏转发。
- DirectDraw 后台缓冲区路径继续手动定义，H3API 不负责该渲染路径。

当前验证：
- `H3PngSupport`：完整迁移，0 error 0 warning。
- `H3MegaDesc`：完整迁移，0 error 0 warning，已提交 `0f2efb7`。
- `H3BattleValueInfo`：迁移完成，0 error 0 warning，最小游戏加载验证通过，已提交 `286f095`。
- `H3BattleCrashFix`：迁移完成，0 error 0 warning，最小游戏加载验证通过，已提交 `416df82`。

### CALL 宏
| 旧 | 新 |
|---|---|
| `CALL_3(int, __thiscall, 0x4E52F0, hero, id, mod)` | `hero->GetSpellExpertise(id, mod)` |

## 迁移策略

1. **每个项目独立迁移**，不改变功能，只换 API
2. **保留模块文件结构**（modules/*.inc.cpp）
3. **保留所有功能逻辑**，只替换类型和调用
4. **编译通过即视为该步骤完成**，后续在游戏中验证
5. **旧 deps 文件最后删除**，确保编译通过后才清理

## 风险与注意事项

- H3API.hpp 的某些封装可能有性能开销（虚拟调用等），但插件场景影响可忽略
- DirectDraw 操作可能不在 H3API 中，需保留手动代码
- `CALL_*` 宏 → H3API 方法调用时，需确认 thiscall 约定一致
- 多模块单翻译单元模式（`#include "*.inc.cpp"`）需要确保 H3API 只 include 一次
