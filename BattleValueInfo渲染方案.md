# BattleValueInfo 远程对比面板渲染方案

## 概述

BattleValueInfo 的远程对比面板（RangedOverlayPanel）是一个**纯被动显示**的覆盖层，不处理任何用户输入。它完全通过 LoHook/HiHook 驱动，在每帧战斗循环中自动绘制。

## 渲染架构

### 核心思想
- **不拦截鼠标/键盘消息**
- **不创建独立窗口**
- **不子类化游戏窗口**
- 在游戏渲染完成后（backbuffer Blt 完成）的回调中，直接向 backbuffer 写入像素

### Hook 布局

| 地址 | 类型 | 作用 |
|------|------|------|
| `0x495C50` | HiHook | 战斗动画循环，每帧调用原函数后画面板 |
| `0x600430` | LoHook | backbuffer Blt 完成后的回调，画板时机最稳 |
| `0x4781C0` | HiHook | 进入战斗事件，触发面板激活 |
| `0x464F10` | HiHook | 施法事件，标记面板脏等待重算 |

### 渲染时机

```
每帧渲染流程:
1. HiHook 0x495C50: 游戏渲染本帧战场
   - 先调用原函数 h->GetDefaultFunc() 完成渲染
   - 然后调用 UpdateRangedPanel() 画面板
2. LoHook 0x600430: backbuffer Blt 完成后
   - 再次调用 UpdateRangedPanel() 确保面板被渲染
```

### 绘制方式（两种模式）

**模式 A：直接写入 backbuffer（HD OpenGL 版本使用）**
```cpp
// 锁定 backbuffer
DDSURFACEDESC desc = {};
o_DDSurfaceBackBuffer->Lock(nullptr, &desc, DDLOCK_WAIT, nullptr);

// 计算像素格式
int bpp = (pf.dwRGBBitCount == 32) ? 32 : 16;

// 逐像素写入（RGB565 或 ARGB8888）
for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
        if (bpp == 32) {
            d[x*4+0] = blue;
            d[x*4+1] = green;
            d[x*4+2] = red;
        } else {
            d[x] = RGB565(red, green, blue);
        }
    }
}

// 解锁 backbuffer
o_DDSurfaceBackBuffer->Unlock(nullptr);
```

**模式 B：通过 screenPcx16（H3WindowManager 内部缓冲区）**
```cpp
H3LoadedPcx16* screen = o_WndMgr->screenPcx16;
screen->FillRectangle(x, y, w, h, r, g, b);
screen->DrawFrame(x, y, w, h, r, g, b);
screen->TextDraw(font, text, x, y, w, h, color, align);
```

### 面板坐标计算

```cpp
// 面板居中于战场对话框顶部
int panel_w = cfg.ranged_panel_width;
int panel_h = cfg.ranged_panel_height;

int x = dlg->x + (dlg->width - panel_w) / 2;
int y = dlg->y - panel_h;  // 面板底部对齐到对话框顶部
```

### 关键代码片段

**HiHook 战斗循环：**
```cpp
int __stdcall Hook_CycleCombatScreen(HiHook* h, _BattleMgr_* mgr)
{
    // 先调用原函数（渲染本帧）
    THISCALL_1(int, h->GetDefaultFunc(), mgr);
    // 在渲染完成后画面板
    if (s_ranged_overlay_panel.Active() && o_BattleMgr) {
        UpdateRangedPanel(o_BattleMgr);
    }
    return 0;
}
```

**LoHook Blt 完成：**
```cpp
int __stdcall Hook_AfterBlt(LoHook* h, HookContext* c)
{
    (void)h; (void)c;
    if (s_ranged_overlay_panel.Active() && o_BattleMgr) {
        UpdateRangedPanel(o_BattleMgr);
    }
    return EXEC_DEFAULT;
}
```

**进入战斗事件：**
```cpp
int __stdcall Hook_CombatStartBattle(HiHook* h, _BattleMgr_* mgr)
{
    int result = THISCALL_1(int, h->GetDefaultFunc(), mgr);
    BeginRangedPanelManualBattle(mgr, "combat start");
    return result;
}
```

## 绘制组件

### 1. 背景图
- 从 PCX 文件解码：8-bit PCX → RGB565/ARGB8888
- PCX 解码：RLE 压缩解码 + 调色板读取
- 背景图贴在对话框顶部

### 2. 文字
```cpp
_Fnt_* font = GetRangedPanelTextFont();
font->TextDraw(
    bg_composite_,      // 目标 surface
    "12345",            // 文本
    x, y, w, h,         // 矩形区域
    NH3Dlg::eTextColor::WHITE,
    NH3Dlg::eTextAlignment::MIDDLE_RIGHT
);
```

### 3. 文字遮罩（用于 GDI 渲染）
```cpp
// 用特殊颜色填充遮罩
TEXT_MASK_SENTINEL_565 = 0xF81F;  // 纯红紫色，在渲染时跳过
TEXT_MASK_SENTINEL_8888 = 0xFFFF00FF;

// DrawPcx16TextWithGDI 只渲染非 sentinel 像素
if (c != TEXT_MASK_SENTINEL) {
    dst_row[x*3+0] = r;
    dst_row[x*3+1] = g;
    dst_row[x*3+2] = b;
}
```

### 4. 刷新通知
```cpp
// 强制刷新面板区域
o_WndMgr->H3Redraw(x, y, panel_w, panel_h);
```

## 数据驱动

### 脏检查（避免每帧重算）
```cpp
unsigned int checksum = ComputeStackChecksum(mgr);
if (checksum == stack_checksum_ && !dirty_) {
    return;  // 数据没变，跳过重算
}
// 否则重新计算远程输出能力...
```

### 战场状态追踪
```cpp
// mgr->dlg 可能在某些阶段为 NULL
// 改用 BUILD hook 传入的 battle_dlg_（更早可用）
if (!dlg && battle_dlg_) dlg = battle_dlg_;
```

## H3Auto 的借鉴

H3Auto 的设置面板渲染可以完全照搬 BattleValueInfo 的方案：
1. 使用 LoHook 0x600430 在 backbuffer Blt 完成后画面板
2. 面板使用 FillRectangle + DrawFrame + TextDraw 绘制
3. 不需要窗口子类化、不需要拦截消息

**但输入捕获问题仍然存在**——BattleValueInfo 不需要输入，所以没有问题。

## 下一步：寻找自动战斗按钮的右键弹窗

战场上的自动战斗按钮右键会弹出一个游戏内置窗口（如"防御"、"主动"等选项）。
如果能 Hook 到这个窗口的关闭/隐藏事件，就可以在那个时刻弹出我们的设置面板。
