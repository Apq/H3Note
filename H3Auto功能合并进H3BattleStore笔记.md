# H3Auto（打铁助手）功能合并进 H3BattleStore 笔记

日期：2026-10-15　范围：把 H3Auto 的功能合并进 H3BattleStore 单一 DLL，**不含** H3Auto 的打包日志（LogPack）。
设计文档：`H3BattleStore\docs\11-H3Auto功能移植.md`；本笔记只记逆向/机制层面的硬事实与落位结论。

## 1. 四个钩子地址的语义（SoD 1.0 / 0xFFFFE403）

| 地址 | 类型 | 原生语义 | 合并后归属 |
|------|------|----------|------------|
| `0x600430` | LoHook | backbuffer Blt 完成（每帧） | **同址单壳**：宿主战斗悬浮条 + 移植层面板帧/自动推进 |
| `0x4746B0` | LoHook | 战斗消息处理入口 `FUN_004746b0`，`this`=H3CombatManager 在 ECX，消息指针在栈上 `[esp+4]`，`msg[0]`=类型（`4`=鼠标移动） | 移植侧独占（宿主本来没挂） |
| `0x4744D0` | HiHook | `FUN_004744d0` 接管判定：返回非 0 = 自动/AI 执行，返回 0 = 等本地人类输入 | 移植侧独占 |
| `0x4786B0` | HiHook | 动作执行入口：开始执行 `action` 字段（动画/伤害/回合推进） | **同址单壳**：宿主执行诊断 + 移植层「单次接管人工动作消费」 |

- `0x4746B0` 的面板吞并手法：面板存活时把鼠标移动消息的坐标改成离屏（清 hover）、吞 0-9 快捷施法键，
  判定命中返回 `NO_EXEC_DEFAULT`，否则 `EXEC_DEFAULT`；**面板存活分支必须判定后直接 return，不得穿透**
  到下面的主动作提交分支。
- `0x4744D0` 的介入条件：只在原版返回 0（本会交给玩家）时介入；原版非 0（自带自动战斗、蛊惑、AI 侧）
  直接透传原返回值。移植层在 `orig==0` 且该部队有配置时代发动作，仍返回 0，由消息入口提交 `action`。

## 2. 同址钩子的单壳合并（本轮核心机制）

宿主与源插件在同一地址各挂一只钩子时，**必须合并成一只壳**（双挂会各自拿到自己的
`GetDefaultFunc()` 链，原版函数行为与调用次数都不可控）。落地规则：

1. **单一注册点**：地址在宿主 `Entry.inc.cpp` 里只写一次 `WriteLoHook/WriteHiHook`；
   源插件原来的那次注册连同它的 `DllMain` 一起丢弃。
2. **段函数化**：源回调里若自带 `hook->GetDefaultFunc()` 调用，必须摘掉，改成只做自己那段判定的
   段函数（本项目：`HH_OnBattleActionExecute` → `AutoOnActionExecuteSegment_(_BattleMgr_*, int)`，
   末尾的 `THISCALL_2(int, h->GetDefaultFunc(), This, flags)` 删除），**原版调用由宿主壳在 `__try` 之外
   恰好调用一次**（源侧本来也是在调原函数之前判定 `This->action`，段序天然一致）。
3. **调用顺序**：0x600430 壳 = 宿主段（画悬浮条）→ 移植段（面板帧/自动推进）；
   0x4786B0 壳 = 宿主前段诊断 → 移植段（消费单次接管）→ `THISCALL_2(orig)` → 宿主后段诊断。
4. **铠甲各自独立**：两段各自 `__try` + 各自 `GuardCrashFilter_(各自的 id, ...)`，互不吞对方故障；
   壳本身不加 `__try`。
5. **对象视图转换**：源用裸结构视图 `_BattleMgr_`（`Compat.inc.cpp` 里按绝对偏移锚定：`action`@0x3C、
   `hero_casted`@0x54B4、`stack[2][21]`、`active_stack`@0x132C8 附近、`dlg`），宿主用 H3API 的
   `H3CombatManager`，二者是同一对象。转换处用 `reinterpret_cast`，并在宿主 TU 顶层加
   `static_assert(offsetof(H3CombatManager, action) == 0x3C, ...)` 钉住布局一致。
6. 宿主的 `0x4786B0` 注册用 `SPLICE_, EXTENDED_, THISCALL_`（源用 `SPLICE_, THISCALL_`）——保留宿主
   既有签名与 splice 更安全，源段的参数按同一调用约定透传即可。

## 3. 铠甲 id 映射（源枚举 → 宿主字符串键）

源插件用枚举下标索引铠甲表，宿主用字符串键（`GuardRegisterHook_(const char*) -> int`）。合并做法：
保留源侧枚举名，把值改为宿主注册返回值，于是所有钩子入口的
`__except (GuardCrashFilter_(GHID_X, GetExceptionInformation()))` 一字未改。

| 源枚举 | 宿主 id | 用途 |
|--------|---------|------|
| `GHID_BLT` | `AutoAssist.AfterBlt` | 0x600430 每帧段 |
| `GHID_MSGPROC` | `AutoAssist.BattleMsgProc` | 0x4746B0 战斗消息段 |
| `GHID_SHOULD_AUTO` | `AutoAssist.ShouldAuto` | 0x4744D0 接管判定 |
| `GHID_ACTION_EXEC` | `AutoAssist.ActionExec` | 0x4786B0 动作执行段 |
| `GHID_KB` | `AutoAssist.CombatHotkey` | 战斗热键 WH_KEYBOARD 回调 |
| `GHID_PANEL_KB` / `GHID_PANEL_MOUSE` / `GHID_PANEL_ITEM` | `AutoAssist.PanelKeyboard` / `PanelMouse` / `PanelItem` | 面板输入钩子与 item 屏障 |

`kMaxGuardHooks` 16 → 32（宿主自用 14 + 移植 8）。注册发生在静态初始化期（`s_guard_hooks` 零初始化），
早于 `DllMain`，单线程安全。

## 4. 跨插件协作 → 同 TU 直连

合并前靠 patcher 变量跨越 DLL 边界（加载顺序无关，未加载时退化为原行为）：

| 原协作键 | 宿主符号（合并后直连） |
|----------|------------------------|
| `H3BattleStore.RestoreEpoch.v1`（读档纪元，变值即通知） | `battlestore::g_storeRestoreEpoch`（`Variable*`，空则视为 0） |
| `H3BattleStore.BusyQuery.v1`（忙态查询，无参 BOOL） | `battlestore::StoreAutomationBusy_()` |
| `H3BattleStore.BeforeAutoAction.v1`（动作前首档玩家窗口，`BOOL(void* mgr)`） | `battlestore::StoreBeforeAutoAction_(void*)` |

语义保持：忙态（保存中/自动保存中/恢复排队/恢复致命）期间不推进自动施法与部队命令；纪元变化时
切手动控制、清自动状态机、重绑部队追踪；首档窗口未建立时本回合不推进，**保存失败也消费本回合尝试、
不重试**。直连后原来的 `VarInit` 注册仍保留（兼容旧版 H3Auto 同时加载的情况只会被纪律禁止，不靠它工作）。

## 5. 纪律与边界

- **不要再同时加载 H3Auto.dll**：同址双挂 + 面板素材/热键会重复（用户已决定只留合并版）。
- 版本门卫：SoD 数据指纹不符时**不挂任何钩子**（含移植钩子），只保留日志；移植钩子注册在门卫之后。
- 打包日志（LogPack）**不在合并范围**：宿主 `LogPack.inc.cpp` 是唯一属主；源插件帮助页的「打包日志」
  按钮与其 7 个 `help.pack_*` 文案键已删除（与宿主悬浮条第一行原有的打包按钮是两回事，后者保留）。
- **打包份数（2026-10-16 用户裁定）**：「改成只限前缀,不限数量」——`LogPackCollectRecent_(out, max_count)`
  （内含 `LogPackEntry all[64]` 上限、只取最近 5 份）改为 `LogPackCollectLogs_(LogPackEntry** out)`：筛选条件只有
  「文件名前缀 = 日志器同源基名 `<基名>_*.log`」（与 H3Auto 等同目录插件互不混入），**份数不限**，收集数组按需
  2 倍扩容（扩容失败就带走已收到的，不假装收全），仍按写入时间降序。组包侧固定数组
  `entries[6]/datas[6]/packs[6]/pack_lens[6]/unpack_sizes[6]/crcs[6]` 改成 `nLogs + 1` 项堆数组（多一项给
  `00_说明.txt`），成功与 `bail` 两条清理路径统一按 `nItems` 释放；压缩成功后立即释放原文件字节（30 份 × 数 MB
  会吃满 32 位进程地址空间）。说明文件文案改为「包含全部 %d 份日志（不限份数，按文件名前缀收集）」，单测夹具
  由「5 份」改为「7 份全进包」。**H3Space 同口径已于 2026-10-15 改过**，但其组包侧直接写 `logs[nLogs]`（说明项）
  而收集器只保证 `total` 项，份数正好等于其扩容容量时越界——本插件移植版单独开 `nLogs + 1` 数组规避。
- 帮助页的**日志级别下拉**于 2026-10-16 按用户裁定移除（同样因为宿主已有：战场存档界面悬浮条第一行的
  日志等级单选列表，点选即写 `[Logging] MinLevel`）；删除范围＝`PanelDraw` 的 `GetHelpLogLevel*` 系列
  + `HELP_DD_*` + `HelpLogLevelOptKey_`、`PanelDraw.hpp` 的两条声明、`SettingsDlg` 的 `s_help_log_dd_open`
  与两个点击分支、双侧 `help.log_level_*` 六个文案键；模态高度 440 → 404，开源地址行上移到原下拉行位置。
- 帮助页开源地址（显示 + 点击复制载荷）2026-10-16 起指向 **`https://github.com/Apq/H3BattleStore.git`**
  （原 `https://github.com/Apq/H3Auto`），改的是 `help.link`/`help.link_flash`/`help.link_url` 三个键。
- 面板/自动化素材与文案：`img\HA_*.pcx`（9 个）、`lang\zh-CN.ini`；方案库走 JSON **v7**，路径
  `<游戏根>\Games\<地图名>\Auto\<16位hex>.json`（回退 `Games\Auto` → DLL 同目录），LRU 保留 30 场。
  注意源插件文档里的「JSON v5」是过时说法。
- **保持状态的「失明（敌方）」（法术 62）2026-10-16 由用户提出补入，同日三轮定案**：
  - 用户口径 ①「自动判断所有可被失明的敌方部队，发现有该补了的就补给它」②「复用『剩余回合≤阈值』补」
    ③「占一个保持状态槽，标签显示『失明（敌方）』」；`StatusMaintainChoice.mass` 对盲为 0（单体）。
  - **第一轮**（日志定案"不在列表"）：`[Panel] 保持状态追加 spell=27` 后玩家又选 `slot=1 spell=54`；当时
    槽位为空 ⇒ 下拉展开、列表看得见，而失明没被选 ⇒ 不在列表。错误地猜成"英雄没学"，玩家纠正
    「我测的就是会双目失明的英雄」，并要求去掉"未学会提示"。
  - **第二轮**（留痕）：`[Panel] status build/cand` 逐候选 debug 留痕。复测日志
    `H3BattleStore_20261016_103406.log`：`status cand spell=62 exp=0 flags=0x41415 ok=0`——书里有、挡在 exp。
  - **第三轮（根因＝概念错误，用户点破）**：「一二级魔法所有英雄都能学会（魔法塔访问即会），不存在学校
    等级这个概念」「会不会以魔法书的显示为准」。**`GetSpellExpertise` 是魔法系别（土/火/水/气系）技能熟练度
    0..3，只决定群体版与效果强度，不是"会不会"**；"会不会"＝`hero->HasSpell()`（learnedSpells|availableSpell，
    +0x3EA/+0x430 位或，装备赋予也算）——`英雄魔法禁施与目标免疫.md` 早已写明"学校 expertise0 不等于未学
    魔法"，attack 通道也是这个口径，保持状态通道用错了判据（这是三轮里真正的教训：**同一判据在隔壁通道
    用对了，不代表这条通道也是对的；改口径前先查项目内已有定案**）。
  - 最终口径：资格只看魔法书（`IsStatusCandidateSpell` 增 `has_spell` 参数）；减速/群体增益仍要专家级
    （群体版是"槽位能不能生效"，不是"会不会"）；失明有书即列；**已选项剔除**（中间一轮曾按「下拉选项
    不用把已选择的去掉」改成不剔除，用户复核后定案改回——同一法术不重复占槽，正在编辑的槽不算）；
    「＋」默认项跳过对敌两项；运行时同步删掉三处 `expertise<=0` 当未学的门槛（buff 循环、盲分支、
    施法前），等级只作施法实参。留痕升级为 `book=%d exp=%d used=%d`。
  - **2026-10-16 晚些时候再演进一次（用户裁定"不区分全体了"）**：`IsStatusCandidateSpell` 定型为
     `(spell, has_spell)`，减速/群体增益的专家级要求整体撤掉；每个保持状态槽新增"全体/指定"两种目标
     （`targetModes`/`targetHexes`，JSON 键，缺键即旧行为、**不升版本号**），页面改成两大列×四行、
     每槽三小列（魔法 / 全体·指定 / 指定哪一队，后者带头像+位置+数量）。详见
     `战斗状态魔法持续与接受判定逆向笔记.md` §9（群体/单体的 flags 判据）与 H3BattleStore 的
     `docs\11-H3Auto功能移植.md` §7.6。
  - 教训：**面板类"选项没有"的反馈，日志留痕先行**——第一轮没留痕只能猜；第二轮一行日志当场定案。
    另：玩家说"会"而代码说"不会"时，先怀疑代码的判据选错，而不是玩家的记忆。

## 6. 本轮踩到并已修的两个编译期坑

1. **残留 `static void Log*(const char*, ...);` 前向声明 → C2129**（不是 LNK）：移植后这些声明落在子
   命名空间里，遮蔽宿主的全局同名日志实现，域内调用绑到永不定义的实体。每加一批模块都要重扫一遍
   （本项目批次二清 3 个文件、批次三又冒出 6 行）。
2. **源适配器里的 `::Foo()` 全局限定 → C2039**：`::ResetPanelDrafts();` 原本表示「调全局自由函数」，
   移植后自由函数已在子命名空间内 → 改 `autoassist::ResetPanelDrafts();`；**不能裸调用**，同名成员
   函数在场时会自我递归。

## 7. 素材目录 `img\` → `pcx\`（2026-10-15 晚，全链路改名）

用户裁定素材目录名应为 `pcx`（与 `H3MegaDesc` 的 `pcx\`、同日 `H3Space` 的 `pcx\`/`png\` 同规）。
改名本身不是重构，但**漏一处就是游戏里整块无图**（素材是运行期按文件名加载，不是编译期嵌入），
所以按引用点清单逐条过。

### 7.1 运行期路径构造（只有两处）

```cpp
// 宿主悬浮条底图（modules\BattleUi.inc.cpp 的 UiLoadBg_）
wchar_t* slash = wcsrchr(wpath, L'\\');              // wpath = <DLL目录>\<相对路径>
const size_t dllDirLen = (size_t)(slash + 1 - wpath);
if (_wfopen_s(&file, wpath, L"rb") != 0 || !file) {   // 调用方传 L"pcx\\HB_bg.pcx"
    const wchar_t* base = wcsrchr(filename, L'\\');   // 兜底：目录段换成 img\ 再试一次
    base = base ? base + 1 : filename;
    if (swprintf_s(wpath + dllDirLen, pathCap - dllDirLen, L"img\\%ls", base) > 0
        && _wfopen_s(&file, wpath, L"rb") == 0 && file) { /* LogInfo 只一次 */ }
}

// 打铁面板素材（modules\PanelGfx.inc.cpp 的 LoadPanelPcx24_）
strcpy_s(slash + 1, remaining, "pcx\\");   // 主路径
strcat_s(path, kPathCap_, asset_name);
...
strcpy_s(slash + 1, remaining, "img\\");   // 打开失败后旧布局兜底
```

- 路径缓冲一律堆分配（`kPathCap_`，宽字符 `kPathCap_/2`）——面板绘制跑游戏线程，栈放不下 4MB。
- 兜底各用 `static bool` → `LogInfo` 只提示一次，避免 9 个素材刷屏。
- 兜底语义：老安装目录没改组时不至于面板整块无图/悬浮条无底图，**不是**版本兼容。

### 7.2 同步清单（缺一即出事）

| 类别 | 位置 | 改动 |
|---|---|---|
| 仓库目录 | `H3BattleStore\img\` → `pcx\` | `git mv`（10 个 `.pcx`，`git status` 显示 `R` 100%，历史保留） |
| 加载路径 | `modules\BattleUi.inc.cpp`、`modules\PanelGfx.inc.cpp` | `pcx\` 为主 + `img\` 兜底 |
| 部署 | `deploy.ps1` | `$pcxDst`、源 `pcx\HB_bg.pcx` 与 `pcx\HA_*.pcx` |
| 打包 | `pack.ps1` | 10 条 entry 的 `热血插件/pcx/…` 与 Local `pcx\` |
| 生成脚本 | `scripts\make_hb_bg.py` | TARGET `pcx\HB_bg.pcx`；SOURCE 由已消失的 `H3Auto\img\HA_bg.pcx` 改本仓库 `pcx\HA_bg.pcx` |
| 文档 | `README.md`、`使用说明.txt`、`docs\11`（§3.3/§7.4/§7.5/§9-7）、`docs\变更记录.md` | 当前口径改 `pcx\`；**历史条目照原样保留**（不改写历史） |

### 7.3 本次验收证据

- 默认与 `H3BS_UI_NULL=1` 两变体构建 exit 0、**0 错误 0 警告**；六组 Catch2 单测 exit 0。
- 默认 `Release\H3BattleStore.dll` **728576 B** SHA256 `E205828B0BC7560FCD1847D14E39D7D422441FE13406DAF8E95FCDA7E3B30B2F`
  （比改名前 727552 B 多 1024 B，即兜底代码），NULL `Release\null\H3BattleStore.dll` 396800 B SHA256 `FCAC84AD…`。
- DLL 字节标记：UTF-16LE `pcx\HB_bg.pcx`=1、`img\%ls`=1（仅兜底）；ASCII `pcx\`=3、`img\`=3
  （2 处字面量 + 1 条日志文案，逐处可解释）。**这类路径必须 ASCII 与 UTF-16LE 双向检索**：
  宽字符串字面量在 ASCII 检索里是假阴性（本仓库早前 `HB_bg.pcx` 审计踩过）。
- `deploy.bat` exit 0：`Packs\热血插件\pcx\` 10 个文件与仓库源**逐一哈希相同**，
  `H3BattleStore.dll`/`使用说明.txt`/`H3BattleStore.default.ini`/`lang\zh-CN.ini` 与仓库源一致。
- 游戏目录里旧 `img\` 不会自己消失（`Copy-Item` 只增不删），加载器优先 `pcx\`，残留无害；
  删除属破坏性操作，**先问用户**。
- 提交：H3BattleStore `0d9d67f`（已推送）。

### 7.4 两个坑

1. **`edit` 工具重写 `.ps1` 会吃掉 UTF-8 BOM**（`deploy.ps1`、`pack.ps1` 本次都中招）。无 BOM 时
   PowerShell 5.1 按 ANSI 读中文路径 → 部署可能建出乱码目录。改完必须复核前三字节 `EF BB BF` 并补回。
2. **包内 entry 路径与部署布局要同时改**，否则发出的 zip 与 DLL 查找路径不匹配。已发出的旧包
   （`Release\战场存档_v0.15.zip`，包内 `热血插件/img/...`）不重打包就与新版 DLL 不配套——能靠兜底显示，
   但会在玩家目录多留一个失效目录。版本号由用户手动维护，agent 不自行 bump、不自行打包。
