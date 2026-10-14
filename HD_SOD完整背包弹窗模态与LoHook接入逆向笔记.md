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
| 整窗背景 | `(0, 0)` | 405×459 | RVA `0x039B25` 调 RVA `0x0FADB0`，返回 H3DlgPcx16，DiBoxBck.PCX + dialgbox.def 生成 |
| 状态条 | `(8, 433)` | 389×18 | H3DlgTextPcx，ID 777，HD_TStat.pcx，默认文案 RVA 0x13EA2D，item 存 `dlg+0x74` |

- 字符串表位置：`"Backpack"` RVA 0x1426A4、`"BkPack.pcx"` 0x1426B0、`"def.SpScrArt"` 0x1426BC、`"artifact.def"` 0x1426CC（.rdata）；创建代码在构造函数 `0x039B72..0x39DB5` + 状态条 `0x039DD3`（`H3DlgPcx` 走 `0x01005E40`，文本走 `0x00617492`+thiscall `0x005BC6A0` 即 `H3DlgText`）。
- **`0x01006620` 不是画底图**：它读 `[0x6992D0]+0x40` 绘制对象，4 次 thiscall `0x0044E2C0`（暗化/阴影条）：右 `(x+w, y+9, 7, h-9)`、`(x+w, y+8, 8, h-8)`、底 `(x+9, y+h, w-2, 7)`、`(x+8, y+h, w, 8)`；stdcall ret 0x10，可被插件直接转发调用（H3RndNew 已在 attach 时同款调用画仓库面板阴影）。
- 卷轴/普通宝物分支由全局 `0x01157FB8` 判别；宝物ID有符号比较 `<0`（`jl`）的槽不建 DEF；不是 ID=0。
- 未 dump 段：构造函数 `0x039E1B..0x039E66`（状态条后续/模态前收尾约 0x4B 字节）。

## 6. 生产消费方式（H3RndNew 阶段 B/C/D 及 2026-10-13 同构改版）

- `0x039E66` LoHook：attach（布局锚点取 `GetList()` 中 ID 1000 控件实际坐标）、保存并在 `dlg+0x70` 写入 `__stdcall(this,msg)` 包装。
- `0x039E80` LoHook：detach（恢复原 callback 指针、关闭 session）。
- 事务成功后置 `dlg+0x7C = -2` 并 `CloseDialog`，走原生"重建背包"重开路径，icon/hit/tooltip/状态栏由游戏自己重建。
- 验证入口：`tests/warehouse_ui_abi.inc.cpp`（离线 0x1A 复刻 + 真实 patcher）与 `tests/warehouse_ui_flow_test.cpp`（纯布局/事务模型），全量回归 PASS；游戏内行为留给用户实机验收。
- 2026-10-13 用户实机反馈"面板过宽、无背景"后改版：仓库面板固定 405 宽与完整背包一致，`BkPack.pcx` 背景放网格原点，标题条 405×30 用 `bigfont.fnt`，64 槽（8×8，步距 46，DEF 44×44 偏 +2,+1）与原生网格同构；锚点 = `GetList()` 中 ID 1000 控件坐标 − (18,50)。布局最小屏宽 834，不足 fail closed。
- 2026-10-13 第二轮（用户裁定"抄整个扩展界面，比它高一点点"）：面板高 459→**523**（+顶部 Tab 行 32 预留 +底部 32 分页行）；网格原点下移 (18,82)；attach 时直接转发调用 `HD_SOD+0x6620` 画同款右/底阴影（Install 缓存函数指针，CrashGuard __try 内）；最小屏高门槛随之 459→523（800×600 仍可显示，宽 834 fail）。
- 2026-10-13 第三轮（用户反馈"格子外空白"）：完整背包非格子区显示的是原画面+阴影，而仓库面板区底下是黑边；补 H3DlgPcx16 整块底板 405×523：`BackgroundRegion`(diboxback.pcx 256×256 平铺) + `FrameRegion`(dialogbox.def 玩家色边框，色=hero->owner)，原版对话框标准做法。（第三轮的通用 DIBOXBACK 手工拼板方案已在第 7 节被推翻，见下。）

## 7. 整窗背景生成器更正（2026-10-13，只读逆向已证实）

此前第三轮记录“完整背包非格子区显示原画面+阴影”以及用通用 DIBOXBACK/DLGBOX 拼仓库整窗的描述均不正确，现以完整反汇编 `D:\\logs\\dsh\\scripts\\h3-warehouse-skin\\fadb0-complete.txt` 和资源解析报告 `skin-analysis.txt` 为准：

- 构造函数 RVA `0x039B25` 调 HD_SOD RVA `0x0FADB0`，完整范围 `[0x0FADB0,0x0FB175)`，长度 `0x3C5`。签名 `H3DlgPcx16* __fastcall(x,y,width,height,itemId,statusBar,colorIndex)`；ECX=x、EDX=y，五个栈参数，`ret 0x14`。原生完整背包参数 `(x,y,405,459,0,1,color)`。
- 返回控件 `H3DlgPcx16*` 的 `+0x30` 为 `H3LoadedPcx16*` 画布；画布自己的 `+0x30` 才是像素 buffer。背景由 `DiBoxBck.PCX` 256×256 裁剪平铺和 `dialgbox.def` 11 帧拼成，不是独立 `sb...` 文件。`sb%.4u%.4u%.1u%.1u` 只作为资源管理器运行时缓存 key，参数为宽、高、`!statusBar`、颜色。
- 背景先做底纹四块平铺，再绘制边缘及四角；statusBar 非零选帧 8/9/10（带底部状态槽），零选 2/3/7。资源位于 `Data\\H3bitmap.lod` 与 `Data\\H3sprite.lod`。离线重建 `405×459` 与扩高 `405×523` 对照图在 `D:\\logs\\dsh\\scripts\\h3-warehouse-skin\\background_comparison.png`；未运行游戏，不能据此宣称实机像素验收通过。
- 底部 `389×18` 状态文字另由 H3DlgTextPcx 构造，位置 `(x+8,y+433)`、ID 777，保存至 `dlg+0x74`；不是背景 item。

## 8. 双层交互与消息中和（2026-10-13 第四轮，静态逆向 + 离线回归）

用户裁定交互契约：背包扩展打开时只显示"仓库"按钮；点击后才展开仓库层（同一 dialog owned-items，游戏内顶层模态即"置顶"）；仓库关闭按钮只收起仓库层；**仓库展开时 Esc 只收起仓库层，仓库关闭时 Esc 保持原生关闭背包**。

已确认的静态事实（反汇编 `D:\logs\dsh\scripts\h3-warehouse-toggle\callback-complete.txt`）：

- 原生 callback `0x0395D0..0x0396AB` 先完成 common/网络/超时处理，结果存 `[ebp-0x28]`；`0x0396AB` 起进入消息分发（command=4 hit-test、`0x200/C` 左键按下、`0x200/E` 右键、`command=2/subtype=1` Esc、`0x039987` 未知回退关闭）。
- Esc 关闭路径：`0x0399B5` 处 `cmp [eax],2` / `cmp [ecx+4],1`，命中则写 `dlg+0x78=-1` 并调 vtable `+0x38` 关闭。
- 未知/外部点击回退：`0x039987` 写 `dlg+0x78=-1` 走同一关闭 vtable；`0x0399F4` 为 `mov eax,[ebp-0x28]` 的公共结果出口。
- 生产实现选择：不劫持 `0x0396AB`/`0x039987` 指令流，而是沿用 `dlg+0x70` callback 包装——自有分支处理完成后把被消费的消息中和为 `command=MOUSE_OVER(4)/subtype=0/itemId=0`，再调用原生 callback 恰好一次。原生 callback 对 command=4 只做 hit-test 分发，不进入关闭分支，common/网络/超时处理天然保留。
- save-under：展开前 `H3LoadedPcx16::Create("",w,h)` + `CopyRegion(GetDrawBuffer(),x,y)`；收起时 `DrawToPcx16(x,y,FALSE,screen,0,0)` 回写 + `H3WindowManager::H3Redraw` 局部重绘 + `Destroy(TRUE)`。`HideDeactivate` 只清 ACTIVE|VISIBLE 不还像素，必须靠 save-under 回写。
- 离线契约回归：`SuppressPinnedClose`（expanded + `0x200/C|D` + 非原生 ID 才中和；`0xE`/`0xA`/Esc/网络/超时/未知命令一律透传）已入 `warehouse_ui_flow_test.cpp`（77 checks）。

## 9. 第五轮 UI 素材与批量分类接线（2026-10-13，源码/离线确认）

- `WarehouseUiButtons.inc.cpp` 的自有视觉控件沿用 H3MegaDesc：`H3DlgDefButton(iOkay.def)` 做命中和状态机，`H3DlgPcx(BkPack.pcx)` 做 PCX 层；复制 `H3DlgItem` 的15槽vtable，仅把槽4 Draw 改为四态绑定绘制。Draw在当前 dialog owned-list 中确认对象归属后才读取 DEF/visual，detach 同样先确认归属再恢复原 vtable。
- 四态状态来源：`+0x16` 的 `0x20` 禁用、`0x01` 按下；悬停不写原生 `0x10 SELECTED`，由 `MOUSE_OVER` 的绝对坐标和自有 `hovered` 标记选择亮态。自有 PCX 控件换图前记录 `H3DlgPcx::Create` 的原始 `loadedPcx`，detach 归属仍在时恢复，避免把 PCX 替换指针交给原生析构。
- `H3LoadedPcx::Create` 的缓冲是 4字节对齐；量化完整拷贝 `BkPack.pcx.palette888.color[256]`，再调用 `palette565.InitiateFromPalette888`。运行时纯解码只接受8bit/3-plane PCX，按每 plane 的 `bytesPerLine` RLE 解码并交错RGB。
- 【round-6 修正】素材总数由49改为44：16按钮（4族×4态）+ 24页签（12×2态）+ 4箭头；标题不再用素材，改为原生 `H3DlgText`。按钮背景改为直接以 H3MegaDesc 原始四态 `whui_src/bv_ok0..3.pcx` 为参考，抹掉勾选图形、保留其立体斜面/边框纹理后写中文文字。44张必须全部成功，否则视觉整体回退。
- 【round-6 修正】Tab改为12项而非14项。机械（slot 13..16）与魔法书（slot 17）不会进入背包，也就不会出现在仓库列表里，因此不列页签；`SlotTab` 仍保留 `Machine/Spellbook` 语义但 `kTabOrder` 只含12项，`IsBackpackSlot(slot)` 拒绝 13..17 使 `TabMatches` 对这两类恒为 false。窗口显示4项，箭头只改变 `TabOffsetShift`，所有页签控件归 panel owned-items。常规定义为全部道具入口；scroll artifact id=1优先，id=0魔法书仍查询原生 `GetSlot`。
- 【round-6 废止】`一键取出` ID 30201、`一键放入` ID 30202，只使用活动Tab过滤；`RetrieveAll/DepositAll` 在私有候选完整准备后一次提交 epoch。第五轮曾在成功后按原生 `dlg+0x7C=-2` 重建重开来刷新图标/tooltip/hit；round-6 用户裁定“仓库打开后移动道具不得关闭仓库”，改为活窗口内 `WarehouseUiRefreshAfterMove_` 就地刷新（重算筛选/翻页/图标帧/计数 + 局部重绘），`-2` 与 `CloseDialog` 不再出现在成功路径。

## 10. 第五轮缺陷修复（2026-10-13，机器码证据确认；其中“关闭顺序”条 round-6 已废止）

- **成功事务的关闭顺序（第五轮曾采用，round-6 已废止）**：`H3Msg::CloseDialog()`（H3API 约 29358）实际跳到 `0x00491640`，写入 `command=0x200`、`subtype=0xA`、`itemId=0xA` 并返回 `2`（证据：`D:\logs\dsh\scripts\h3-warehouse-ui\modal-close-shade.txt`）。完整背包 modal loop 只有在 callback 返回 `2` 且消息仍为 `0x200/0xA` 时才退出并读取 `dlg+0x7C`（`modal-loop.txt` 114–124）。第五轮因此让成功事务在原生 callback 返回后写 `dlg+0x7C=-2`、调 `CloseDialog` 并返回 `2`。该机制本身仍然成立，但 round-6 用户要求仓库打开期间移动道具不得关闭仓库，故生产路径不再下发 END_DIALOG；`CloseDialog`/`dlg+0x7C` 只保留为逆向事实记录。
- **布局拒绝而不是假平移**：`MakeLayout` 在两侧空间不足时曾规划把背包放到左缘，但 StageB 没有移动原生背包背景、标题、状态条、命中项或 DEF。因此 Attach 现在要求 `layout.backpack.x/y` 与实际 ID 1000 锚定出的原点完全一致，否则 fail closed 保留原生背包，避免同一 dialog 两套命中项重叠。
- **Hook 安装原子性**：modal attach/end 两只 `WriteLoHook` 必须同时存在；任一失败时对已创建的另一只调用 `LoHook::Destroy()` 并清指针，`g_wh_ui_installed_` 保持 false；attach 入口也检查该标记，避免只安装半套 Hook 后产生永不 detach 的 vtable/PCX 裸指针残留。
- 修复后全量 BAT 回归（18:08 终版）：主 DLL 与测试工程 0 warning/0 error；warehouse UI flow 170（含回调关闭顺序与布局 fail-closed 用例，顺序由生产共用 `WarehouseUiCallback.hpp::CallNativeThenFinalize` 保证）、PCX 286、UI 状态机/11 指纹 77、LoHook ABI、真实 patcher callback/RNG 并发均 PASS；部署 Release 与 Packs SHA256 均为 `C8BFD5AF792DBB2735AAECA1570B816FC8D3561C0697491EF41EDAAD4B3F5DF9`。仍未启动游戏，`-2` 重建、实际重打与存读档循环由用户验收。

## 11. 第六轮：图标层、命中状态位与“移动不关闭”（2026-10-13，机器码 + 生产接线）

用户 round-6 裁定：按钮沿用 H3MegaDesc 原图质感但用文字；标题与原生背包标题同字号/同字体/同亮度；**仓库打开后无论怎么移动道具都不关闭，只有 X 或 Esc 才收起**；关闭控件是极端右上角的小四态 X；页签去掉机械与魔法书（12项），两个一键按钮左右交换。

- **owned-items 命中测试（`0x5FF970` → `0x5FF9A0`，反编译 `blk_5f0000.c`）**：`0x5FF9A0(dlg, x, y)` 先把坐标减去 `dlg+0x18/0x1C`（dialog 客户区原点），再从 owned-list 尾部（`dlg+0x38`）向前逐项（`iVar3 -= 4`）扫描；命中条件是矩形包含 **且** `state(+0x16) & 2` 置位 **且** `(state & 8) == 0` **且** `(state & 0x1000) == 0`。`0x5FF970` 只是把命中项 `+0x10` 的 `INT16` ID 取出来，未命中返回 -1。
- 由此推论并已按此实现：`HideDeactivate()` 清 ACTIVE|VISIBLE，是“既不显示也不参与命中”的正确调用；`Hide()` 只清 VISIBLE，**隐藏但仍会被原生命中**。同一 ID 存在多个控件时（本轮的普通/卷轴双覆盖层），只要非选中的那些都 `HideDeactivate`，逆序扫描就只会命中唯一活动项，重复 ID 是安全的。
- **`H3DlgDef::SetFrame` 只写 `defFrame`，不加载/替换 `loadedDef`**（H3API `0x4EA800` 创建时确定 DEF 资源，`SetFrame` 见 `H3API.hpp` 27545）。因此“同一个背包格可能装普通宝物、也可能装卷轴（`def.SpScrArt` 帧=法术ID）”无法靠 SetFrame 完成资源切换：生产做法是每格创建两个同 ID 控件（`artifact.def` 与 `HDassets::SCROLL_SMALL`），按当前记录只激活其中一个；原生原件自接管起一直停用，否则收起后转移过的格子会显示构造时的旧帧。
- **HD 卷轴模式全局是 `0x01157FB8`（RVA `0x157FB8`）**，非零时卷轴走 `def.SpScrArt`、帧=subtype，否则走 `artifact.def`、帧=artifactId；运行时由 `MakeIconView` 纯函数选择资源族。
- **原生标题参数（反汇编确证）**：`H3DlgText(x, y+18, 405, 30, text, "bigfont.fnt", color = eTextColor::REGULAR (=1), id = 0, align = MIDDLE_CENTER, bkColor = 0)`。仓库标题复用完全相同的尺寸/字体/颜色/对齐，才能保证与原生背包标题同字号、同亮度。
- **原生图标 DEF 几何**：44×44，网格原点相对扩展窗原点 `(+18,+50)`，格内 DEF 偏移 `(+2,+1)`，步距 46。
- **展开态必须自己处理图标 CLICK**：自建覆盖 DEF 与原生命中项共用 ID 区间（`1000..1063` 槽命中、`2000..2063` 宝物图标）。若不适配这些 ID 的 CLICK，原生 callback 会落到 `0x039987` 的未知回退关闭分支并写 `dlg+0x78=-1`，表现为“点一下背包就关窗”。
- **“移动不关闭”的生产语义**：成功转移只调 `WarehouseUiRefreshAfterMove_`（就地重算筛选/翻页/图标帧/计数 + 局部重绘），不再写 `dlg+0x7C=-2`，也不调 `CloseDialog`；收起仓库层只有两条路径——关闭按钮 ID 30060 与展开态 Esc。背包 modal 本身仍由原生 Esc（仓库已收起时）关闭，右键/网络/超时/未知路径继续透传。
- **点击边沿策略**：仓库控件只中和 `LBUTTON_DOWN(0xC)`，动作只在 `LBUTTON_CLICK(0xD)` 执行一次；`IsWarehouseControlId` 覆盖 `30050/30051` 翻页箭头、`30060..30202`（关闭/打开/一键取出/一键放入/30100..30163 槽位）、`30300..30311` 页签，刻意不含背景 ID `30000..30004`。展开态下 `2000..2063` 的 DOWN 与 CLICK 都由本模块接管。

## 12. 待验证（不混入确认段）
- `Arg(1)/Arg(2)` 的参数语义（生产代码仅作锚点缺失时的回退，不依赖）。
- Esc/右键/联机关闭路径、HeldArtifact 与第一击拦截的实机交互。
- round-6 新增待验证：活窗口就地刷新（不重建）后，原生 tooltip/状态栏是否仍与新数据一致；覆盖层 DEF 与原生命中项同 ID 同时存在时，长时间悬停/拖拽是否出现旧帧残留；`0x157FB8` 卷轴开关在运行时是否确实按 HD 设置翻转。
- 必须由用户实机验收：四态按钮观感是否与 H3MegaDesc 一致、中文标题亮度、极端右上小 X 命中范围、12 页签左右滚动、两个一键按钮左右语义、以及“移动道具后仓库保持打开”。
- 双层交互的实机效果：仓库按钮位置/字体渲染（GBK 字节串 + bigfont）、save-under 回写是否残留、展开态外部左键中和后的实际行为、Esc 分流第一击是否真的不关背包——均需用户游戏内验收。
- 消息中和（改写 `H3Msg` 后再调原生 callback）对 command=4 分支的副作用：静态看只做 hit-test，但 `0x396C0` 起 `ItemCommand(dlg,itemId,...)` 仍会执行；若实机出现状态栏/悬停异常，需改为 return_address 重定向方案（`0x0396AB` LoHook + 跳 `0x0399F4` 出口，保留 `[ebp-0x28]` 返回值）。

## 13. 第七轮（2026-10-13）：命中项是覆盖控件的坐标真源

- **错位事故与教训**：第六轮把仓库面板网格原点 `kGridOriginDY=82`（含 Tab 行 +32）误用于背包覆盖图标；原生背包图标实际在窗口 +50，导致物品比网格整体低 32px（用户观感“背包初始位置上移、物品没跟上”）。凡是往原生弹窗里加同位覆盖控件，坐标一律取自原生现存控件的实际 `GetX()/GetY()`，不要从常量推导；本例正确做法：覆盖 DEF = 原生命中项(1000+i) 坐标 + (2,1)（与原生 DEF 图标相对 hit 的格内偏移一致）。新增 `kBackpackGridOriginDY=50` 与仓库原点 82 彻底分开。
- **分页控件 ID 扩展**：底部箭头复用 arrow 素材但为独立实例（ID 30050/30051，与页签行 30310/30311 同素材不同对象）；页码按钮 30400..30403 为 36x22 两态底图 + id=0 的 H3DlgText 数字（文本控件不参与 0x5FF9A0 命中测试，点击落在下层透明命中项——这与原生标题/状态条文本行为一致，round 4-6 从未出现“点标题关窗”即为旁证）。
- **布局配置**：`[WarehouseUI]` 节七键两层 ini（default/user），attach 时重读；超范围钳制回退。仓库控件坐标从此不再写死在源码。
- **语义裁定（非逆向）**：一键=全量（常规页语义）；放入落点无关（面板内任意点击即追加提交）；未完成移动=取消（选择只存模块内存，不写原生数组/held，故天然回原位）。

## 14. 第八轮（2026-10-14）：宝物表 position 是 1-based、空槽按下的关窗路径与消息分类边界

**【第十轮更正，2026-10-14】**本节“1-based”结论只在 raw 1..7 段成立，高段被第十轮实机推翻（见 §17）。保留原文以记录推理链。

- **宝物表 `position` 运行期为 1-based（0 表示无装备位）**——本轮最关键的一条纠正。归类错位的实机症状链（用户报告）是：头部页为空、肩部里显示头的装备、胸甲页显示的是戒指类道具，即**每个分类整体后移一位**；反推唯一自洽解释是分类表按 0-based 的 `eArtifactSlots`（H3API/NH3API：HEAD=0、SHOULDERS=1、NECK=2、RIGHT_HAND=3、LEFT_HAND=4、TORSO=5、RING=6/7、FEET=8、MISC1..4=9..12、BALLISTA..CATAPULT=13..16、SPELLBOOK=17、MISC5=18）编写，而运行时读到的是同一批位置的 **+1 表示**（raw 1=头部、raw 6=胸甲、raw 7/8=双戒指、raw 19=杂物5、raw 0=未装备）。修法是分类前先归一化：`raw<=0 → 无位置`，否则 `raw-1`。**注意与仓库自有 `Heroes3Src` 复原（NECK=1、CLOAK=2、MISC1..5=9..13、SPELLBOOK=14、机器 15..18）不是同一编号体系，不要混用**；两者只在“0-based 分类 ↔ 1-based 表值”这一层换算。
  - 【第十轮更正】"raw 7/8=双戒指、raw 19=杂物5"是**当时未经验证的推断**，不是观察：均匀 `raw-1` 把 raw 8 起本就规范的高段也错位了一格。真实分段编码见 §17。
- **静态取表的尝试与其边界**：`Heroes3 HD.exe` 的 VA `0x660B68` 在文件里不是宝物表（读到的是资源/字符串垃圾，例如 `NewWeek3.def`），游戏目录内也没搜到该表的静态副本——该地址可能只在活进程里有效。本条结论是从**两次独立的实机观察**反推出的语义，不是静态取证；若要升级为机器码级证据，需要在活进程里 dump `0x660B68` 起 N×记录并与已知宝物对拍。
- **空槽按下就是“关窗”的触发点（round-8 定性）**：原生命中项 `1000..1063` 覆盖背包 8×8 全部格子，round-7 的中和策略只吞 `LBUTTON_CLICK(0xD)`，**`LBUTTON_DOWN(0xC)` 对 `1000..1063` 是刻意透传的**（当时理由是“保持原版按压/提示路径”）。空槽上的这次按下进入原版按下状态机后走到上层关闭分支，玩家看到的就是“点空格关掉整个界面”。修法：展开态下 `0x200/0xC` 与 `0x200/0xD` 两态一律中和且不再按 id 放行。
- **消息分类边界（H3API `NH3Messages` 逐条核对，纠正了一个想当然的写法）**：`ITEM_COMMAND == MOUSE_BUTTON == 0x200` 是 **command**；`LBUTTON_DOWN=0xC`、`LBUTTON_CLICK=0xD`、`RBUTTON_DOWN=0xE`、`END_DIALOG=0xA` 是它的 **subtype**；而 `MOUSE_WHEEL=0x20A`、`LBUTTON_UP/ITEM_REDRAW=0x10`、`LCLICK_OUTSIDE=0x8`、`RCLICK_OUTSIDE=0x20`、`WHEEL_BUTTON=0x309` 都是**独立 command**。因此“展开态吞掉所有 0x200 子类型”会把 `END_DIALOG(0xA)` 一起吞掉——这违反既有硬约束“绝不屏蔽 EndDialog”。正确形状是**只吞左键手势两态**（`0xC/0xD`）：既覆盖空槽按下与未知 ID 点击，又把滚轮（`0x20A` 独立 command）、右键、Esc、网络/超时、EndDialog 全部保留在原生路径上。
- **坐标兜底比 id 更可靠**：空槽未必有可用的 `itemId`，因此“点背包装备即入仓”的判定改为**先查 attach 时记录的原生命中项几何（`1000..1063` 的 `GetX/GetY/GetWidth/GetHeight`），再用算术兜底**（原点 = 背包原点 + `(18,50)`、步距 46、8×8，`slot = row*8+col`，越界返回 -1）。几何真源沿用 round-6/7 的结论：原生命中项是覆盖控件坐标的唯一真源。
- **`H3DlgItem::GetX()/GetY()` 返回 `INT`（非 `UINT`）**，`IsVisible()` 可用（`H3API.hpp` 10901/10257）；覆盖层控件的可见性判断用 `IsVisible()` 即可，不需要读 `+0x16` 状态位（读状态位仅在需要区分“隐藏但仍可命中”的 `Hide()` 语义时才必要）。

## 15. 待验证（第八轮补充）
- 1-based 归一化按“raw 1=头部、raw 6=胸甲、raw 8=右手戒指”归纳：戒指/杂物/机器等**其余位置只做了同构推导**，未经逐项实机对拍；若个别页签仍有一项错位，应按同一表逐值复核（而不是再改一处偏移）。
- “空槽按下走关闭分支”为**行为级定性**：未在活进程里断到是 `0x039987` 还是 END_DIALOG 路径。若实机仍出现“点某处关窗”，下一步应在 `0x0396AB` 处断下并记录 `command/subtype/itemId`（本模块已把消费前后都打了日志，可直接对读）。
- 第八轮未实机验证：四类页签归类结果、`BulkButtonDY`（及同节其余键）改 user.ini 后重开弹窗是否立即生效、单击背包装备是否即时入仓、点空格是否不再关窗、“整理”按钮显隐与存储层排序观感、整理后存档/读档是否保持新顺序。

## 16. 滚轮消息的增量载体（2026-10-14 第九轮接线时核对）
- `eMsgCommand::MOUSE_WHEEL (0x20A)` 到达 dialog callback 时，**增量数值在 `H3Msg::subtype`**：原生 `H3Dlg::Notify` 的分发是 `case MOUSE_WHEEL: if (OnMouseWheel(msg.subtype)) break;`（H3API 单头 29088-29091），基类 `H3Dlg::OnMouseWheel(INT direction)` 默认返回 TRUE。
- 符号约定与 H3Auto `PanelInput.inc.cpp` 的生产实证一致（同一条消息通道）：`subtype > 0` = 上滚（向更早项移动），`subtype < 0` = 下滚；量级（±120 等）与消费方步进无关，只取符号。
- H3RndNew 仓库页签行据此实现滚轮滚动：仅当光标在页签行内且窗口实际移动时消费该消息（中和为 MOUSE_OVER）；行外/未展开/已到边界透传。`H3DlgItem::TranslateUnprocessedMessage`（H3API 27853-27877）证明控件内滚轮会以 `NotifyParent` 回流 dialog 层，不消费即走原路径——这也解释了为什么“行内滚轮”必须在 dialog 回调层处理。

## 17. 第十轮（2026-10-14）：宝物表 position 的分段编码定案（推翻第八轮“均匀 1-based”）

**症状**（第十轮用户实测，在均匀 `raw-1` 归一化部署后）：戒指页 = 戒指+靴子；靴子页全是杂物；杂物页应为空。

**定案**：运行时 `H3ArtifactSetup::position` 是**分段**编码，不是均匀偏移——
- raw 0 = 无装备位；
- raw 1..6 = 头/肩/颈/右手/左手/胸甲（相对 0-based 规范 **+1**）；
- raw **7 = 戒指族单值**（规范中 6/7 双戒指位在表中只出现一个，戒指族归到 6）；
- raw **8 起与 0-based 规范完全一致**：8=靴子、9..12=杂物1..4、13..16=战争机器、17=魔法书、18=杂物5。

三轮症状链交叉验证：修前（无归一化）只有 raw 1..7 段错位（头部空/肩显头/胸甲进戒指页），靴子=8、杂物=9 落在规范槽位**本来就正确**——与用户第八轮只报“从胸甲往前到头部全错”完全吻合；均匀 `-1` 修好低段的同时把高段错了一格（靴→7 戒指页、杂物1→8 靴子页、杂物5 18→17 被魔法书拒绝→杂物页空）。修法：`raw<=6 → raw-1；raw==7 → 6；raw>=8 → 原值`。

**证据边界**：raw 8=靴子、raw 9=杂物族由本轮实机锁定；raw 10..18 按编号连续性推定（未逐值实机对拍）。静态取证依旧失败：exe 中包装 `0x660B68` 处的指针指向 `0x693A58`，落在 `.data` 的**零初始化区**（raw size 0x34000 只覆盖到 RVA 0x292000，0x693A58 的 RVA 0x293A58 在 BSS 段），文件里该偏移读到的实际是 `.rsrc` 内容（旧笔记里的 “NewWeek3.def 垃圾”即由此而来）——表是运行时构建的，静态文件里不存在。NH3API 佐证地址语义：`akArtifactTraits=0x693A58`（144 项 ×0x20，slot 在 +8）、组合表 `0x693938`、槽位特征表 `akArtifactSlotTraits=0x694C58`（19 项）；反编译初始化代码在 `blk_440000.c:28385` 附近逐项填充。要机器码级定案仍需活进程 dump。
