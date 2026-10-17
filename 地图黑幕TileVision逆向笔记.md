# 地图黑幕（TileVision 战争迷雾）逆向笔记

主题：黑幕数据结构、全开/恢复的实现口径。2026-10-17 为 H3Space「地图全开 + 恢复」功能调研。

## 1. 数据结构（H3API 对照 + exe 反汇编双重确认）

```cpp
struct H3TileVision {            // sizeof = 2
    H3PlayersBitfield vision;    // +0 每格 1 字节：8 个玩家各占 1 位（该玩家看过此格即置位，常开）
    BOOL8 zoneControl;           // +1
};                               // H3API.hpp:7056（_H3API_GET_INFO_(0x698A48, H3TileVision)）
```

- 数组基址：`*(H3TileVision**)0x698A48`（`DAT_00698a48`），即 `H3TileVision::Get()`；地图未装载时为 0。
- 寻址函数 `FUN_004f8070 @ 0x4F8070`（36 字节，H3API `H3TileVision::GetTile(x,y,z)`）：
  `return DAT_00698a48 + ((DAT_006783cc * z + y) * DAT_006783c8 + x) * 2;`
  —— `0x6783c8`=地图宽、`0x6783cc`=地图高（均为 mapSize）。
- 读写语义（H3API 内联实现，`H3API.hpp:20699-20721`）：
  - `CanViewTile(x,y,z,player=-1)` = `GetTile(x,y,z).vision.bits & (1<<player)`（player<0 取 `H3CurrentPlayerID::Get()`）；
  - `RevealTile(x,y,z,player=-1)` = 同一字节 `|= (1<<player)`，**纯内存位写，不调游戏函数**。
  - 这就是"英雄走到哪里才能看到哪里、看过一次常开"的全部机制：黑幕只是这批位的反相呈现。

## 2. 数组生命周期（换图/读档的重建点 = 快照失效点）

`FUN_004fdb40 @ 0x4FDB40`（`void __thiscall (H3Main* this, int mapSize, char hasUnderground)`，352 字节）：

- `this+0xD4 = mapSize`、`this+0xD8 = hasUnderground`（与 H3API `H3MainSetup.mapSize/hasUnderground` 同偏移）；
- `tiles = ((hasUnderground?2:1) * mapSize * mapSize)`；
- 先释放旧 `DAT_00698a48`，再 `operator_new(tiles*2)` 并**整块清零**（随后由开局逻辑揭示初始区域）；
- 同函数还重建 0x26(38) 字节/格的 `H3MapItem` 数组（`this+0xD0`）。
- 证据：`reversing\Heroes3Src\src\h3\uncategorized\blk_4f0000.c:25763-25990`。
- **含义**：新开/读档/RMG 都会走这里 ⇒ 黑幕备份（恢复用）必须在此点作废。上限尺寸 = 144²×2×2 = 82,944 字节（巨型双层）。

## 3. 全开后的重绘

- `H3AdventureManager::FullUpdate()`（H3API.hpp:30552）= `THISCALL_3(VOID, 0x417380, this, 1, 0)`，冒险地图+小地图全量刷新；`H3AdventureManager::Get()` 来自 `0x6992B8`。
- H3API 无现成"整图揭示"API；逐格 `RevealTile` 等价于直接对数组 OR 当前玩家位（字节 0），字节 1（zoneControl）不动。

## 4. 实现口径（H3Space「地图全开/恢复」）

- **全开**：备份整块 `tiles*2` 字节 → 对每格 byte0 `|= (1<<当前玩家)` → `FullUpdate()`。
- **恢复**：把备份 memcpy 回数组 → `FullUpdate()`，随后丢弃备份。恢复到"全开那一刻"的黑幕；全开期间玩家新探开的格子也会被回滚（符合"恢复"语义）。
- **失效**：HiHook `0x4FDB40`（原函数在 `__try` 外恰好一次调用，之后作废备份）；读档/换图后"恢复"不可用属预期（黑幕随档走）。
- **触发**：热键切换（默认 F10，扫描码 68；`[MapReveal] HotkeyScan` 可配）。不模拟/不调用作弊码 `nwcwhatisthematrix`（用户 2026-10-17 裁定：只参考其语义，实现走内存位写）。
- 只写**当前玩家**位（与作弊码一致）；联机公平性由玩家自担（同作弊码）。

## 5. 待验证（实机）

- 全开后小地图/冒险地图即时刷新是否完整（依赖 FullUpdate 的覆盖面）。
- 全开状态下保存→读档：黑幕保持全开（随档保存），此时本插件备份已失效，恢复不可用。

## 6. 快照进存档（2026-10-17 用户要求：参考随身空间）

用户裁定：全开前的黑幕快照**必须随存档保存**，读档后仍可恢复。复用随身空间同一套接缝（`WarehouseStore.inc.cpp`）：

- 写：`0x4BEB60 SaveGame` 后置（共享壳 `SharedHookShell.inc.cpp` 已排好序：`sle::SaveGameBefore_` → `rndnew::OnSaveGame_`），在游戏写盘成功后**读回 `.GM1` → 边界扫描 → 追加自定义块 → 临时文件原子替换**（与 `whstore::PlanSave` 同一套边界/原子语义）。
- 块格式（独立标签，不与随身空间附件冲突）：`MRVS` + u16 版本 + u16 保留 + u32 地图标识（mapSize | 地下<<16）+ u32 长度 + 原始 `tiles*2` 字节 + u32 校验。
- 读：载入时同一读取器取块；**地图标识不一致即拒绝恢复**（防串档把别的图的雾写回）。
- 失败语义：追加/替换失败一律保持原文件不动（不破坏存档），`LogError` 记录。
- 进程内状态与存档块分离：`0x4FDB40` 只清进程内快照；存档里的块保留，故读档后可恢复。

当前实现状态（round 1 已交付）：热键 X（45，可配）+ 进程内全开/恢复 + `0x4FDB40` 失效 + CrashGuard + 日志，构建部署通过（`3DC5D5B4A1C212553DD2A5683FFE2D562BE74097B4D05E79F95EEB30E3FFE61C`）。存档块（本节）为 round 2 施工项。
## 7. 施工进度与交接（2026-10-17，H3Space 侧）

已完成并验证（部署哈希 `5F44ECA30EC1289E4C641FC6730F672C73EC1AA616AAC076F334442445BC7F92`，Release=部署一致，单测全绿）：

- `modules/MapReveal.inc.cpp`：热键 **X（45，`[MapReveal] HotkeyScan` 可配 / `Enabled=0` 可关）** → 全开↔恢复；全开前整块 TileVision 快照；`0x4FDB40` 地图重建作废快照；`FullUpdate` 重绘；CrashGuard（`MapReveal`/`MapReveal.MapSetup`）+ 决策日志。
- 键盘派发：`SettingsDialog.inc.cpp` 的 `OnKeyMsg_` 在设置窗 `KeyMsg` 返回 false 后转 `MapRevealOnKeyMsg_`。
- 模块包含：`H3Space.cpp` 在 `namespace rndnew`（78-104 行）内包含，**模块文件不得自包 rndnew**（否则 `rndnew::rndnew` → C3861/C2039）。
- `MRVS` 块编解码已就位：magic/版本/地图标识(`mapSize | 地下<<16`)/长度/FNV 校验；`MapRevealBuildBlock_(UINT8** out, …)`（注意不是 `UINT8* const*`，否则 C3892）。

**未完成的关键项**：`MRVS` 块尚未接入存档读写，即"快照进存档、读档后可恢复"未实现。

交接要点（下一步施工顺序）：

1. 读 `WarehouseStore.hpp:42-130`（`Observation` / `SavePlan` / `ValidateObservation` / 两个 `PlanSave` 重载）与 `WarehouseStore.inc.cpp:230-270`、`:373-405`（`OnSaveGame_` / `OnLoadGame_`）；
2. `PlanSave` 是纯函数（原文件字节 + Observation → SavePlan），文件层读回与原子替换在 `OnSaveGame_`；**不要新增第二个 0x4BEB60 钩子**，避免破坏共享壳（`SharedHookShell.inc.cpp`）的既有顺序；
3. 追加 `MRVS` 块失败必须保持原文件不动（存档安全优先，`LogError` 记录）；
4. 载入侧取块 → 校验地图标识一致才允许恢复（防串档）；
5. 补单测（新增测试 TU 需加入 `tests/run-unit-tests.ps1` 的 `rndSources`）、补设计文档、再次统一构建/部署/哈希验收。

阻塞原因（连续多轮相同）：复用存档写入路径必须先完整掌握上述约 200 行的边界语义，而其失败代价是玩家存档；本会话剩余上下文不足以安全完成，故停手而非硬改。
## 8. 存档持久化定案与实现（2026-10-17 完成）

实现落在 H3Space：`modules/MapRevealSave.inc.cpp`（**包含在 `WarehouseStore.inc.cpp` 之后**，复用其文件层 `WhReadFile_` / `WhWriteFileAtomic_`），并在随身空间**同一次**存档/读档后置里调用（**不新增第二个 `0x4BEB60` 钩子**）：

- 文件尾部布局：`[原生存档+其它插件数据][MRVS 块][u32 blockTotal]`；`blockTotal` 用于从尾部定位块起点，块头自带 magic/版本/地图标识/长度/FNV 校验。
- 写：原生存档成功（AL==1）后读回 `.GM1` → 先剥掉旧的尾部 MRVS 块 → 有快照则追加新块，无快照则只写剥离后的内容（**未全开时保存会自动清除旧快照**）→ 原子替换；任何失败保持原文件不动。
- 读：读档成功后从尾部解析并校验（magic/版本/**mapId 与当前地图一致**/长度/校验）→ 装回为可恢复快照；并用 `memcmp(当前黑幕, 快照) != 0` 判定"读档时是否仍处于全开态"，据此决定按 X 是恢复还是全开。
- 顺序要点：`0x4FDB40`（地图重建）先把进程内快照作废，随后读档后置再装回存档那份 —— 因此"读档后按 X 可恢复"成立。
- 前向声明：`MapRevealAfterSave_/MapRevealAfterLoad_` 声明在 `MapReveal.inc.cpp`（第 89 行包含），实现放在后面的 `MapRevealSave.inc.cpp`，否则 WarehouseStore 侧会报 C3861。

验收：构建 0 错误、单测全绿、部署哈希 `268EAC1A8CB255E7A154BD369A3A95089CA9EE0C7D400072FD13CB44C0EBEF62`（Release=部署一致）。设计文档：`H3Space/docs/地图黑幕全开与恢复设计文档.md`。

**已知边界**：尾部块按"本模块最后追加"处理（若别的插件在本模块之后再追加尾部数据，保存时的剥旧块会连带切掉它）；实机行为与联机公平性由用户自担/自验。