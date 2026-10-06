# 打铁助手 — 战斗界面逆向笔记

## 2026-10-06：重打后输入屏障旧指针污染资源树

### 已确认的日志、静态与目标 EXE 证据

- 本次 HD 5.7 RC7 崩溃发生于 22:59:21。报告：[HD_CRASH_LOG.txt](D:/Heroes3/Heroes3_2026.05.01/HD_CRASH_LOG.txt)，原始编码 GBK；插件日志：[H3Auto 日志](D:/Heroes3/Heroes3_2026.05.01/_HD3_Data/Packs/打铁助手/H3Auto_20261006_225655.log)。
- `0x55E38F` 指令为 `mov [eax+0x20],ecx`，前一条 `0x55E38D` 为 `mov eax,[esi]`。异常上下文 `ESI=0x080B3D20 / EAX=0x63BA24 / ECX=1`，尝试写入 `0x63BA44`。目标 EXE 的 `.rdata=0x63A000..0x65D968` 只读。
- `0x63BA24` 是透明控件 `H3DlgTransparentItem` 的虚表，不是资源树空节点。来源：[声明](../H3API/include/h3api/H3DialogControls/H3DlgTransparentItem.hpp:25)，[构造器](../Heroes3Src/src/h3/uncategorized/blk_440000.c:38224)。
- `0x55DF20` 是全局资源管理器红黑树的删除/再平衡，节点首 DWORD 是 left child，`+0x20` 是颜色；因此这里把节点首 DWORD 中的控件虚表误当 child 指针。来源：[H3ResourceManager::RemoveItem](../H3API/include/h3api/H3Assets/H3ResourceManager.cpp:34)，[反编译](../Heroes3Src/src/h3/uncategorized/blk_550000.c:33285)。
- 原始故障栈是障碍 DEF 释放 → DEF 帧资源解除引用 → 资源树删除；`0x463135` 是遍历 `mgr+0x13D5C/0x13D60`、步长 `0x18` 并调用每项 DEF `vtable+4` 的返回地址，不是普通对话框删除。来源：[清理函数](../Heroes3Src/src/h3/uncategorized/blk_460000.c:6520)。
- 日志 22:58:09 安装屏障 `item=080B3D20`，22:58:11 关闭面板仍保留引用；22:58:36 取消重打；22:59:00.605 新开面板仍对 `080B3D20` 执行「旧输入屏障已隐藏」。当时旧实现只比较 BattleUI 指针相等，直接写 `*oldItem=original_vtable` 并调用 HideDeactivate，没有确认当前窗口控件列表归属。重打前后 BattleUI 同为 `1EEB4B98`。
- `HideDeactivate` 还会写控件 state，不能把“隐藏旧对象”当只读安全动作。窗口地址相同不证明它还是同一生命周期，关闭后保留 item 原始指针存在确定的释放后访问风险。
- fatal 当前 `EBP-ESP=0x2C` 符合该函数正常栈帧；没有证据支持“错误 API 的 ret8 已使 ESP 漂移”。CrashGuard 的报告器栈不等于 fault 栈，以 HD 原始异常上下文优先。fatal 报告之后的 DETACH 不能视为正常退出。

### 高置信归因，仍待动态首次写入验证

最可能的链条是：上场屏障释放后，`080B3D20` 被资源树节点复用；重打新开面板误把旧控件虚表写入该节点首 DWORD。此后资源树删除走到同一地址，将 `0x63BA24` 当 child 指针，最终写只读虚表 `+0x20` 崩溃。旧指针地址、写入常量、fault 节点地址三者一致，是当前最强证据链；未抓首次写入断点，不能宣称已完成动态复现或排除其它树写坏者。

### 修复与复测范围

- 关闭面板还原合法控件虚表/隐藏后立即清空屏障引用；游戏仍拥有并销毁旧控件，不由插件重复释放。
- 安装/关闭前先从当前活动 BattleUI 的 `GetList()` 比较 owned 指针；未找到旧 item 不解引用也不写入，只丢弃引用。找到后才检查 parent/id/vtable。防止相同窗口地址导致跨重打误认。
- `H3BaseDlg::AddItem` 先把 item 加入拥有的向量，再调用原版 LoadItem；其返回不能当 BOOL 成功标志，加入后不能因为返回值再自行 DestroyItem。已删除这条可能留下悬挂向量项的旧失败分支；不是本次日志确证的首次破坏点。[AddItem 源码](../H3API/include/h3api/H3Dialogs/H3BaseDialog.cpp:84)，[原版 LoadItem](../Heroes3Src/src/h3/uncategorized/blk_5f0000.c:27201)。
- 首次打开面板检查 Install 返回；找不到窗口/创建失败立即取消打开并执行 Close 清理，与系统模态恢复失败处理一致，避免无屏障继续点选透传。上述安装失败问题属独立静态风险，不定为本次已证根因。
- 纯回归覆盖当前归属、同窗口地址但旧 item 不在列表、不同窗口、空列表/空 item/异常 count；不替代实机窗口析构、内存复用、完整安装/移除顺序或点选验收。
- 优先实机路径：开关面板多次 → 完成战斗 → 取消重打 → 再开面板设点 → F9 → 正常结束，至少重复数次。施法预检未恢复，不能由本次控件修复推导无预检力盾安全性。


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
