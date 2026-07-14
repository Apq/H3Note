# 战场自动化 — 战斗界面逆向笔记

> 调查时间：2026-07-10
> 目的：找到"自动战斗"按钮的 Hook 方案

---

## 1. 关键 H3API 接口

### H3Msg 消息结构体

```
位置: H3API.hpp 第10864行
大小: 0x20 字节

字段:
  command  (eMsgCommand)   — 消息大类：KEY_DOWN=0x1, LBUTTON_UP=0x10, RBUTTON_UP=0x40 等
  subtype (eMsgSubtype)   — 按钮子类型：LBUTTON_CLICK=0xD, RBUTTON_DOWN=0xE
  itemId  (INT32)         — 控件 ID ← 识别按钮的关键字段
  flags    (eMsgFlag)     — SHIFT=1, CTRL=4, ALT=32
  position (H3POINT)      — 鼠标相对坐标 (x, y)
  parameter (VOID*)       — 附加参数
  parentDlg (PVOID)       — 对话框指针
```

### eMsgCommand 关键值

| 值 | 含义 |
|---|---|
| 0x0010 | `LBUTTON_UP`（左键抬起）|
| 0x0020 | `RCLICK_OUTSIDE`（右键点击在对话框外）|
| 0x0040 | `RBUTTON_UP`（右键抬起）|
| 0x0001 | `KEY_DOWN`（键盘按下）|

### eMsgSubtype 按钮相关

| 值 | 含义 |
|---|---|
| 0xD | `LBUTTON_CLICK`（左键点击）|
| 0xE | `RBUTTON_DOWN`（右键按下）|

> **注意**：`RBUTTON_UP` 没有单独的 subtype 值；右键弹起是通过 `command == RBUTTON_UP (0x40)` 加上 `itemId` 来识别的。

---

## 2. 战斗对话框结构

### H3CombatDlg（H3API.hpp 第17087行）

```
大小: 0x8C 字节，继承自 H3BaseDlg

关键字段:
  bottomPanel (H3CombatBottomPanel*)  — 底部面板（含自动战斗按钮）
  leftHeroPopup / rightHeroPopup      — 英雄悬浮框
  leftMonsterPopup / rightMonsterPopup — 怪物信息悬浮框
```

### H3CombatBottomPanel（H3API.hpp 第17111行）

```
大小: 0x40 字节，继承自 H3DlgBasePanel

已知字段:
  commentBar  (H3DlgTextPcx*)      — 提示条
  commentUp   (H3DlgCustomButton*) — 注释上翻
  commentDown (H3DlgCustomButton*) — 注释下翻
```

> "自动战斗"按钮的实际 ID 待实测获取。需要在战斗中 Hook 0x41B120，打印 `msg.itemId` 确认。

---

## 3. Hook 方案

### 方案 A：Hook 对话框 DefProc（推荐）

```
地址: 0x41B120
类型: LoHook
目标: 战斗对话框的 DefaultProc

实现逻辑:
1. Hook 每次消息都收到通知（LoHook = 前置通知）
2. 判断: msg.command == RBUTTON_UP (0x40)
3. 获取: msg.itemId → 对比已知的"自动战斗"按钮 ID
4. 如果是"自动战斗"按钮的右键抬起:
   a. 调用原函数（原函数会弹出帮助窗口）
   b. 然后弹出设置窗口
5. 否则返回 EXEC_DEFAULT，继续传递消息
```

### 方案 B：Hook 战斗动画循环（辅助）

```
地址: 0x495C50
类型: HiHook
目标: 每帧检测设置窗口是否应弹出
```

---

## 4. 行动提交（eBattleAction 枚举）

```
H3API.hpp 第2485行

enum eBattleAction:
  CANCEL         = 0
  CAST_SPELL     = 1
  WALK           = 2
  DEFEND         = 3   ← 防御
  RETREAT        = 4   ← 撤退
  SURRENDER      = 5   ← 投降
  WALK_ATTACK    = 6   ← 行走攻击
  SHOOT          = 7   ← 射击
  WAIT           = 8   ← 等待
  CATAPULT       = 9   ← 投石车
  MONSTER_SPELL  = 10
  FIRST_AID_TENT = 11
  NOTHING        = 12
```

---

## 5. "自动战斗"按钮 ID 获取方法

**待实测：** 在 `Hook_DefProc` 中打印所有 `command == 0x40`（RBUTTON_UP）的 `msg.itemId`。

预期日志格式：
```
[RBUTTON_UP] itemId=XXX x=YYY y=ZZZ
```

在战斗画面右键点击"自动战斗"按钮时，输出的 `itemId` 即为按钮 ID。

---

## 6. SettingsDlg 实现规划

- **背景图**: `img\HA_bg.pcx`，尺寸 680×480
- **布局**: 7行（A~G）× 3列（下方、中、上方）
- **控件**: 每格一个下拉框（5个策略选项）
- **关闭按钮**: 右上角，ID 待定
- **渲染方式**: 参考 BattleValueInfo 的 `_Pcx16_` + GDI BitBlt 架构
