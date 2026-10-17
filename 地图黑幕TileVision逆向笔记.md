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
