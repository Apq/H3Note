# HD_SOD 完整背包弹窗模态与 LoHook 接入逆向笔记

记录日期：2026-10-13。任务范围：H3RndNew 仓库 UI 阶段 B/C/D 生产接线所需的 HD_SOD 完整背包弹窗函数指令级事实与 patcher LoHook ABI 验证。不启动游戏，全部结论来自本机文件字节与受控离线回归。

目标：`D:\Heroes3\Heroes3_2026.10.09\HD_SOD.dll`（preferred base `0x01000000`，大小 1451520，FileVer 0.2.0.92）。本文 RVA 均指该文件 `.text`；不适用于其它 HD_SOD 版本。

## 1. RVA 到文件偏移换算（先踩的坑）

- `.text`：VA `0x1000`、raw size `0x12F400`、raw ptr `0x400`。
- 正确换算：`file = 0x400 + (rva - 0x1000)`。
- 坑：早期把 RVA 直接加 `0x400`（漏掉节区 VA 基），读出的"机器码"完全错位，导致一度误判 `0x039E66` 的指令边界。任何字节级结论必须先解析 PE 节区表再换算。

## 2. 完整背包弹窗函数（已验证）

- 函数体 `RVA 0x039A00`..`0x039EC0`，`C2 18 00`（`ret 0x18`）：六栈参、callee 清栈（stdcall 形态）。
- dialog 对象由工厂 `0x010FB180` fastcall(x,y,w,h,flags,callback) 分配，大小 `0x9C`；完整背包为全屏 (0,0,width,height)。
- 对象字段：`+0x70` callback、`+0x74` 状态栏、`+0x78` hero 指针、`+0x7C` result（`-2` = 请求重建重开）、`+0x80` override。dialog 指针在函数栈 `[ebp-8]`。
- 原生背包控件：hit item ID `1000+i`（i=0..63）、DEF item ID `2000+i`；hero 背包在 `hero+0x1D4`（64×8 字节）与 `hero+0x3D4`（int8 计数）。

## 3. 模态调用窗口指令流（0x1A 字节，字节级已验证）

```
0x039E66: 6A 00              push 0            ; ShowAndRun mode 栈参
0x039E68: BA 04 00 00 00     mov edx, 4
0x039E6D: 6B C2 06           imul eax, edx, 6  ; = 0x18 vtable 偏移
0x039E70: 8B 4D F8           mov ecx, [ebp-8]  ; dlg
0x039E73: 8B 11              mov edx, [ecx]    ; vtable
0x039E75: 8B 4D F8           mov ecx, [ebp-8]  ; this
0x039E78: 8B 04 02           mov eax, [edx+eax]; vtable+0x18 = ShowAndRun
0x039E7B: FF D0              call eax          ; 寄存器间接调用！
0x039E7D: 8B 4D F8           mov ecx, [ebp-8]
------ 0x39E66..0x39E80 共 0x1A 字节 ------
0x039E80: C7 41 08 00 00 00 00  mov [ecx+8], 0 ; dlg+8 = 0
后续 0x039E9C 读 [dlg+0x7C] 结果族；0x039EB8 析构；0x039EC0 ret 0x18
```

- `ShowAndRun`（`0x005FFA20`）fastcall 形态：ECX=this、EDX=mode、一个栈参，callee `ret 4` 清栈；调用返回后 ESP 回到 `ebp-8`。
- 弹窗 callback（`0x0395D0`，内部 `0x0399FA`）为 `__stdcall(this, msg)`、`ret 8`。

## 4. patcher LoHook ABI（真实 patcher_x86.dll 受控实证）

用逐指令复刻上述 0x1A 字节的 naked 夹具 + 真实 patcher 验证，全部 PASS：

1. **`FF D0` 不能装 CALL_**：patcher `CALL_` 契约仅支持 `E8`/`FF 15`。`FF D0` 是寄存器间接调用，普通 HiHook 不可用（这不是猜测，是契约边界）。
2. **LoHook 可以**：挂 `0x039E66` 起点、`EXEC_DEFAULT`。displaced 前缀为 `push 0; mov edx,4`（7 字节），`FF D0` 仍在原地执行，恰一次。
3. **执行顺序**：钩子回调先于 displaced 指令执行。site+7 观察钩实测：EDX 已变为 4、ESP=ebp-12（push 0 已执行），EAX/ECX/EBX/ESI/EDI/EBP/EFLAGS 仍为进入时种子值——即 EXEC_DEFAULT 完整恢复寄存器上下文，displaced 前缀的合法副作用在后续指令前可见。
4. **上下文访问**：`HookContext::Local(2)` 读 `[ebp-8]`（dlg；Local(n)=ebp-4n）；`Arg(1..6)` 依次读六个 stdcall 栈参；EFLAGS 通过 push/mov 前缀在回调前后存活。
5. **ESP/SEH**：整个窗口执行前后外层 ESP 平衡；show 内抛异常时 SEH 默认传播，两钩与 show 各恰一次；callback `ret 8` 直调与替换均正确清栈。
6. **`0x039E80` 后置钩**：该点 dialog 仍存活（析构在 `0x039EB8`），可安全恢复 callback 指针；displaced 指令 `mov [ecx+8],0` 7 字节。

## 5. 完整背包视觉构成（2026-10-13 追加，构造函数反汇编实测）

相对弹窗 405×459 视觉区原点 `(x, y)`：

| 元素 | 位置(相对 x,y) | 尺寸 | 资源/ID |
| --- | --- | --- | --- |
| 外框阴影 | 右/底边缘 | 见下 | `0x01006620(x,y,w,h)` 画 4 条暗化条 |
| 标题文本 | `(0, 18)` | 405×30 | `bigfont.fnt`，文案从 `HD.Ini.Txt` 节读、默认 `"Backpack"` |
| 背景网格图 | `(18, 50)` | 369×369 | **`BkPack.pcx`**（DLL 内字符串实为 .pcx；H3API `HDassets::BIG_BACKPACK` 注释写 .bmp 与实际不符） |
| hit item | `(18+col*46, 50+row*46)` | 47×47 | ID `1000+row*8+col`（8×8，步距 46） |
| DEF 图标 | `(20+col*46, 51+row*46)` | 44×44 | ID `2000+row*8+col`；卷轴 `def.SpScrArt` 帧=subtype（法术ID），普通 `artifact.def` 帧=artifactId |
| 状态条 | `(8, 441)` | 389×18 | ID 84，默认文案 RVA 0x13EA2D，item 存 `dlg+0x74` |

- 字符串表位置：`"Backpack"` RVA 0x1426A4、`"BkPack.pcx"` 0x1426B0、`"def.SpScrArt"` 0x1426BC、`"artifact.def"` 0x1426CC（.rdata）；创建代码在构造函数 `0x039B72..0x39DB5` + 状态条 `0x039DD3`（`H3DlgPcx` 走 `0x01005E40`，文本走 `0x00617492`+thiscall `0x005BC6A0` 即 `H3DlgText`）。
- **`0x01006620` 不是画底图**：它读 `[0x6992D0]+0x40` 绘制对象，4 次 thiscall `0x0044E2C0`（暗化/阴影条）：右 `(x+w, y+9, 7, h-9)`、`(x+w, y+8, 8, h-8)`、底 `(x+9, y+h, w-2, 7)`、`(x+8, y+h, w, 8)`；stdcall ret 0x10，可被插件直接转发调用（H3RndNew 已在 attach 时同款调用画仓库面板阴影）。
- 卷轴/普通宝物分支由全局 `0x01157FB8` 判别；空槽（`hero+0x1D4+index*8` 首 4 字节为 0）不建 DEF。
- 未 dump 段：构造函数 `0x039E1B..0x039E66`（状态条后续/模态前收尾约 0x4B 字节）。

## 6. 生产消费方式（H3RndNew 阶段 B/C/D 及 2026-10-13 同构改版）

- `0x039E66` LoHook：attach（布局锚点取 `GetList()` 中 ID 1000 控件实际坐标）、保存并在 `dlg+0x70` 写入 `__stdcall(this,msg)` 包装。
- `0x039E80` LoHook：detach（恢复原 callback 指针、关闭 session）。
- 事务成功后置 `dlg+0x7C = -2` 并 `CloseDialog`，走原生"重建背包"重开路径，icon/hit/tooltip/状态栏由游戏自己重建。
- 验证入口：`tests/warehouse_ui_abi.inc.cpp`（离线 0x1A 复刻 + 真实 patcher）与 `tests/warehouse_ui_flow_test.cpp`（纯布局/事务模型），全量回归 PASS；游戏内行为留给用户实机验收。
- 2026-10-13 用户实机反馈"面板过宽、无背景"后改版：仓库面板固定 405 宽与完整背包一致，`BkPack.pcx` 背景放网格原点，标题条 405×30 用 `bigfont.fnt`，64 槽（8×8，步距 46，DEF 44×44 偏 +2,+1）与原生网格同构；锚点 = `GetList()` 中 ID 1000 控件坐标 − (18,50)。布局最小屏宽 834，不足 fail closed。
- 2026-10-13 第二轮（用户裁定"抄整个扩展界面，比它高一点点"）：面板高 459→**523**（+顶部 Tab 行 32 预留 +底部 32 分页行）；网格原点下移 (18,82)；attach 时直接转发调用 `HD_SOD+0x6620` 画同款右/底阴影（Install 缓存函数指针，CrashGuard __try 内）；最小屏高门槛随之 459→523（800×600 仍可显示，宽 834 fail）。
- 2026-10-13 第三轮（用户反馈"格子外空白"）：完整背包非格子区显示的是原画面+阴影，而仓库面板区底下是黑边；补 H3DlgPcx16 整块底板 405×523：`BackgroundRegion`(diboxback.pcx 256×256 平铺) + `FrameRegion`(dialogbox.def 玩家色边框，色=hero->owner)，原版对话框标准做法。

## 7. 待验证（不混入确认段）

- `Arg(1)/Arg(2)` 的参数语义（生产代码仅作锚点缺失时的回退，不依赖）。
- `-2` 重开链路、Esc/右键/联机关闭路径、HeldArtifact 与第一击拦截的实机交互。
