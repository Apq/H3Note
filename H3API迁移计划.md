# H3API.hpp 迁移计划

> 对应 [H3API迁移方案.md](H3API迁移方案.md)

## 阶段 0：准备（共享）

- [x] 研究 H3API.hpp 的关键 API（H3Spell、H3Hero、H3Patcher 等）
- [x] 编写旧→新 API 映射表
- [x] 编写迁移方案文档

## 阶段 1：H3PngSupport（试点，最小项目）

**代码量**：~397 行 | **复杂度**：低

- [x] 1.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [x] 1.2 修改 PngSupport.cpp：替换 include 和全局变量
- [x] 1.3 修改 modules/Entry.inc.cpp：替换 Patcher 初始化（无需改动，GetPatcher 在 H3API.hpp 中）
- [x] 1.4 修改 modules/PngSurface.inc.cpp：替换 DirectDraw 类型（保留手动 DD 全局变量）
- [x] 1.5 修改 modules/ConfigLog.inc.cpp（无需改动，不依赖 homm3.h）
- [x] 1.6 修改 .vcxproj（移除旧 deps 编译项，升级 stdcpp20）
- [x] 1.7 编译通过，0 error 0 warning
- [ ] 1.8 游戏内验证功能
- [x] 1.9 提交并推送

## 阶段 2：H3MegaDesc

**代码量**：~954 行 | **复杂度**：中
**特殊依赖**：`_Pcx8_*`（图像量化/合成）、`_Dlg_*`（窗口控件遍历）、`CALL_2`
**阻塞点**：H3API 不包含 `_Pcx8_` 封装，需保留手动定义或从旧 homm3.h 提取最小子集

- [x] 2.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [x] 2.2 修改 MegaDesc.cpp：替换 include 和全局变量
- [ ] 2.3 提取 `_Pcx8_` 最小定义（从旧 homm3.h）保留在模块内
- [ ] 2.4 修改 modules/CreatureDialog.inc.cpp（_Dlg_→H3Dlg + CALL_2→THISCALL_2）
- [ ] 2.5 修改 modules/PatchesAndImages.inc.cpp（_Pcx8_ 保留，o_ 全局变量检查）
- [ ] 2.6 修改 .vcxproj（已完成 stdcpp20 升级）
- [ ] 2.7 编译通过，0 error 0 warning
- [ ] 2.8 游戏内验证功能
- [ ] 2.9 提交并推送

## 阶段 3：H3BattleValueInfo

**代码量**：~1186 行 | **复杂度**：高（大量偏移访问、spell 计算）

- [ ] 3.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [ ] 3.2 修改 BattleValueInfo.cpp：替换 include 和全局变量
- [ ] 3.3 修改 modules/Entry.inc.cpp
- [ ] 3.4 修改 modules/ConfigLog.inc.cpp
- [ ] 3.5 修改 modules/CreatureDialog.inc.cpp（最大工作量）
  - [ ] 3.5.1 替换 _Hero_ → H3Hero，修正所有成员访问
  - [ ] 3.5.2 替换 _Spell_ → H3Spell，使用 spEffect/baseValue
  - [ ] 3.5.3 替换 _BattleMgr_ → H3CombatManager
  - [ ] 3.5.4 替换 hero->GetSpell_Specialisation_Bonuses → GetSpellSpecialtyEffect
  - [ ] 3.5.5 替换 CALL_* 宏 → H3API 方法
  - [ ] 3.5.6 修正 DirectDraw 相关代码（可能保留手动）
  - [ ] 3.5.7 替换 spec 表访问方式
- [ ] 3.6 修改 .vcxproj
- [ ] 3.7 编译通过，0 error 0 warning
- [ ] 3.8 游戏内验证魔法输出计算（对比 2995）
- [ ] 3.9 提交并推送

## 阶段 4：H3BattleCrashFix

**代码量**：~1920 行 | **复杂度**：高（大量 hook）

- [ ] 4.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [ ] 4.2 修改 BattleCrashFix.cpp：替换 include 和全局变量
- [ ] 4.3 修改所有 modules/*.inc.cpp
- [ ] 4.4 修改 .vcxproj
- [ ] 4.5 编译通过，0 error 0 warning
- [ ] 4.6 游戏内验证功能
- [ ] 4.7 提交并推送

## 阶段 5：H3SaveLoadEnhance

**代码量**：~2040 行 | **复杂度**：高

- [ ] 5.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [ ] 5.2 修改 SaveLoadEnhance.cpp：替换 include 和全局变量
- [ ] 5.3 修改所有 modules/*.inc.cpp
- [ ] 5.4 修改 .vcxproj
- [ ] 5.5 编译通过，0 error 0 warning
- [ ] 5.6 游戏内验证功能
- [ ] 5.7 提交并推送

## 阶段 6：清理

- [ ] 6.1 确认所有项目编译通过
- [ ] 6.2 确认所有项目游戏内验证通过
- [ ] 6.3 更新 H3Note 中的迁移记录
- [ ] 6.4 更新各项目 README（如有）

## 执行原则

1. **一个项目一个项目来**，完成一个再开始下一个
2. **每步完成后打勾**（编辑此文件）
3. **编译通过**是该步骤完成的标志
4. **游戏验证**后才能提交
5. **遇到 H3API 缺失的功能**（如 DirectDraw），保留手动代码并记录
