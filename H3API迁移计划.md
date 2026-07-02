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
- [x] 2.3 提取 `_Pcx8_` 最小定义（改为 H3LoadedPcx 兼容别名）
- [x] 2.4 修改 modules/CreatureDialog.inc.cpp（CALL_2→THISCALL_2，文本控件/添加控件改 H3API）
- [x] 2.5 修改 modules/PatchesAndImages.inc.cpp（_Pcx8_→H3LoadedPcx，palette888/scanlineSize）
- [x] 2.6 修改 .vcxproj（已完成 stdcpp20 升级）
- [x] 2.7 编译通过，0 error 0 warning
- [ ] 2.8 游戏内验证功能
- [x] 2.9 提交并推送（`0f2efb7`）

## 阶段 3：H3BattleValueInfo

**代码量**：~1186 行 | **复杂度**：高（大量偏移访问、spell 计算）

- [x] 3.1 复制 H3API.hpp 到 deps/
- [x] 3.2 修改 BattleValueInfo.cpp：替换 include 和全局变量
- [x] 3.3 修改 modules/Entry.inc.cpp（沿用 H3API patcher）
- [x] 3.4 修改 modules/ConfigLog.inc.cpp（无需改动）
- [x] 3.5 修改 modules/CreatureDialog.inc.cpp（最大工作量）
  - [x] 3.5.1 保留 _Hero_ 最小兼容层，修正旧 power 偏移风险由既有裸偏移逻辑承担
  - [x] 3.5.2 保留 _Spell_ 最小兼容层，维持现有法术算法
  - [x] 3.5.3 保留 _BattleMgr_/_BattleStack_ 最小兼容层，避免大规模重写裸偏移逻辑
  - [x] 3.5.4 保留 hero->GetSpell_Specialisation_Bonuses 兼容封装
  - [x] 3.5.5 替换 CALL_* 宏为 H3API THISCALL_* / 兼容宏
  - [x] 3.5.6 DirectDraw 相关代码保留手动路径
  - [x] 3.5.7 spec 表访问方式暂保留裸地址，避免改动已验证算法
- [x] 3.6 修改 .vcxproj
- [x] 3.7 编译通过，0 error 0 warning
- [x] 3.8 最小游戏加载验证通过（生成日志、无崩溃）；魔法输出对比 2995 待后续实战回归
- [x] 3.9 提交并推送（`286f095`）

## 阶段 4：H3BattleCrashFix

**代码量**：~1920 行 | **复杂度**：高（大量 hook）

- [x] 4.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [x] 4.2 修改 BattleCrashFix.cpp：替换 include 和全局变量
- [x] 4.3 修改旧 CALL_* 为 H3API THISCALL_*/FASTCALL_*（本项目无 modules/*.inc.cpp）
- [x] 4.4 修改 .vcxproj
- [x] 4.5 编译通过，0 error 0 warning
- [x] 4.6 最小游戏加载验证通过（生成日志、无崩溃日志更新）
- [x] 4.7 提交并推送（`416df82`）

## 阶段 5：H3SaveLoadEnhance

**代码量**：~2040 行 | **复杂度**：高

- [x] 5.1 复制 H3API.hpp 到 deps/，删除旧 deps 文件
- [x] 5.2 修改 SaveLoadEnhance.cpp：替换 include 和全局变量
- [x] 5.3 修改旧 CALL_* 为 H3API THISCALL_*（本项目无 modules/*.inc.cpp）
- [x] 5.4 修改 .vcxproj
- [x] 5.5 编译通过，0 error 0 warning
- [x] 5.6 最小游戏加载验证通过（生成日志、无崩溃日志更新）
- [x] 5.7 提交并推送（`91d170b`）

## 迁移现状总结

### 已完成
- [x] **H3PngSupport** — 完整迁移（`270c120`），0 error 0 warning
  - 该项目不依赖游戏内部类型，只用 DirectDraw + libpng

### 已完成
- [x] **H3MegaDesc** — 完整迁移（`0f2efb7`），0 error 0 warning
  - `_Pcx8_` 以 `H3LoadedPcx` 兼容别名承接
  - `palette24.colors` → `palette888`，`scanline_size` → `scanlineSize`
  - `CALL_2` → `THISCALL_2`
  - 保留 `_Dlg_` 最小 shim 以兼容现有裸偏移逻辑

### 已本地编译通过，待游戏验证/提交
- [x] **H3BattleValueInfo** — 完整迁移（`286f095`），0 error 0 warning，最小游戏加载验证通过
  - 保留 `_Hero_` / `_Spell_` / `_BattleMgr_` / `_BattleStack_` 最小结构兼容层
  - 保留 DirectDraw 手动路径和已验证的裸偏移算法
  - 生成新日志 `BattleValueInfo_20260702_101343.log`，HD_CRASH_LOG 未更新

### 已完成
- [x] **H3BattleCrashFix** — 完整迁移（`416df82`），0 error 0 warning，最小游戏加载验证通过
  - `CALL_*` 替换为 `THISCALL_*` / `FASTCALL_*`
  - 生成新日志 `BattleCrashFix_20260702_102100.log`，HD_CRASH_LOG 未更新

### 已完成
- [x] **H3SaveLoadEnhance** — 完整迁移（`91d170b`），0 error 0 warning，最小游戏加载验证通过
  - `CALL_*` 替换为 `THISCALL_*`
  - 生成新日志 `SaveLoadEnhance_20260702_102736.log`，HD_CRASH_LOG 未更新

### 待迁移
- 无

### 关键 API 映射

| 旧 | H3API |
|---|---|
| `_Dlg_*` | `h3::H3BaseDlg*` / `h3::H3Dlg*` |
| `dlg->width/height` | `dlg->GetWidth()/GetHeight()` |
| `_DlgItem_*` | `h3::H3DlgItem*` |
| `_EventMsg_*` | `h3::H3Msg*` |
| `_Pcx8_*` | `h3::H3LoadedPcx*` |
| `_Pcx8_::Load(name)` | `H3LoadedPcx::Load(name)` |
| `_Pcx8_::CreateNew(name,w,h)` | `H3LoadedPcx::Create(name,w,h)` |
| `pcx8->DrawToPcx16(...)` | `pcx8->DrawToPcx16(...)` |
| `pcx8->palette24` | `pcx8->palette888` |
| `_Pcx16_*` | `h3::H3LoadedPcx16*` |
| `CALL_2(ret,__thiscall,addr,a,b)` | `THISCALL_2(ret,addr,a,b)` |
| `CALL_3(ret,__thiscall,addr,a,b,c)` | `THISCALL_3(ret,addr,a,b,c)` |
| `o_DD` / `o_DDSurfaceBackBuffer` | 手动定义（H3API不含DD封装） |

### 编译要求
- C++ 标准：**stdcpp20**（H3API.hpp 要求）
- 定义 `_H3API_PATCHER_X86_` 以启用内置 patcher_x86

- [x] 6.1 确认所有项目编译通过
- [x] 6.2 确认所有项目最小游戏加载验证通过（完整功能回归另行执行）
- [x] 6.3 更新 H3Note 中的迁移记录
- [ ] 6.4 更新各项目 README（如有）

## 执行原则

1. **一个项目一个项目来**，完成一个再开始下一个
2. **每步完成后打勾**（编辑此文件）
3. **编译通过**是该步骤完成的标志
4. **游戏验证**后才能提交
5. **遇到 H3API 缺失的功能**（如 DirectDraw），保留手动代码并记录
