# HD_SOD 完整背包弹窗模态与 LoHook 接入逆向笔记

记录日期：2026-10-13。任务范围：H3RndNew 随身空间 UI 阶段 B/C/D 生产接线所需的 HD_SOD 完整背包弹窗函数指令级事实与 patcher LoHook ABI 验证。不启动游戏，全部结论来自本机文件字节与受控离线回归。

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
| 状态条 | `(8, 433)` | 389×18 | H3DlgTextPcx，ID 777，HD_TStat.pcx，默认文案 RVA 0x13EA2D（**空串**），item 存 `dlg+0x74` |

### 状态条构造 ABI 与悬停文案（2026-10-14 第十四轮，H3RndNew 随身空间状态条按此同构）

- **构造（完整码 0x039DFF..0x039E63）**：`new(0x54)`（`0x617492`，cdecl size→ptr）→ **thiscall `0x5BCB70`**，ECX=新对象，栈参数正序 `(x+8, y+433, 389, 18, text, "smalfont.fnt", "HD_TStat.pcx", 1, 777, 5, 0)`；返回对象存入 `dlg+0x74`，并入 dialog owned-list（析构由 `dlg+0x34..0x38` 枚举 + vtable[0](1) 统一完成）。第 8/10/11 个参数（1/5/0）为 HD 内部样式位，**颜色随该构造走**——要“提示文字颜色与背包一致”就必须用同一构造，不要自建 H3DlgText 另配色。
- **默认文案 RVA 0x13EA2D = 空串**（`.rdata`，读到的第一个字节就是 `\0`）：背包状态条初始无字，悬停才填名字；**悬停离开不清空**（下一次悬停才覆盖）。
- **悬停分支（callback 0x010396BD..0x010397F9，command==4）逐条**：
  1. `0x5FF970(dlg, msg.x, msg.y)` 现算命中项 id（**不用 msg 里的 itemId**），要求 `0x7D0 ≤ id < 0x810`（即 2000..2063 的 DEF 覆盖图标）。
  2. `artifactId = *(hero + 0x1D4 + (id-2000)*8)`（`hero`=`dlg+0x78`；`0x1D4` 即背包记录数组起点，与构造码里的 `[eax+edx*8+0x1d4]` 同源）。
  3. 普通宝物：名字 = `*[0x660B68] + artifactId*0x20 + 0`（H3 宝物表首字段 name；H3API 对应 `H3Artifact(id,subtype).GetName()`）。
  4. **法术卷轴特例**（`artifactId == 1`）：`wsprintf(buf, "%s. {%s.}", 宝物名, 法术名)`，格式串 RVA `0x142658`；法术名 = `*[0x687FA8] + subtype*0x88 + 0x10`（H3Spell.name，0x88 与 `sizeof(H3Spell)` 一致；H3Auto `SpellRules.inc.cpp` 同写法 `H3Spell**`）。
  5. 更新序列：`状态条->vtable[13](text)`（SetText，槽 13×4=0x34）→ `状态条->vtable[4]()`（Draw）→ **`0x10FAA10(状态条)`**（只刷该 item 屏幕矩形，内部走 `00603190`）。空槽（id 落回 1000..1063）不触发任何更新。
- **H3RndNew 同构落地**（WarehouseUiStageB）：状态条创建在随身空间面板 `(面板原点+8, +505, 389, 18)`（ID 30500，仅日志用——H3DlgText 不参与 `0x5FF9A0` 命中）；悬停用 `GridSlotFromPoint` 定位随身空间槽（与原生“坐标现算”同策略），文案走 `FormatStatusHint`（普通=宝物名；卷轴=上款拼接），更新用同一 `SetText→Draw→刷屏` 序列。两条状态条各管各自面板：背包 2000..2063 仍由原生分支更新原生条。

#### ⚠ 地址空间归属（2026-10-14 实机崩溃复盘，写 H3RndNew/插件前必读）

本笔记正文里的绝对地址**分属两个模块**，混用必崩：

| 地址 | 归属 | 插件里怎么用 |
| --- | --- | --- |
| `0x5BCB70`（H3DlgTextPcx 构造）、`0x5BC6A0`（H3DlgText 构造）、`0x617492`（operator new）、`0x5FF970`（鼠标命中原生）、`0x5FF9A0`（原生命中测试）、`0x660B68`/`0x687FA8`（宝物/法术表）、`0x642DF8`（H3DlgTextPcx vtable） | **H3.exe 绝对 VA**（全部 `< 0x1000000`） | **直接用绝对地址，绝不加 HD_SOD 基址**。H3API 本身就 `THISCALL_12(H3DlgTextPcx*, 0x5BCB70, …)` 直接调 |
| `0x10FADB0`（整窗底图工厂）、`0x10FAA10`（悬停后刷屏助手）、`0x1006620`（外框阴影）、`0x113EA2D`（状态条空白默认文案）、`0x1157FB8`（卷轴判别全局）、`0x1039E66`/`0x1039E80`（attach/detach LoHook 点） | **HD_SOD 绝对 VA**（≥ 0x1000000） | 先 `GetModuleHandleW(L"HD_SOD.dll")` 取运行时基址，`RVA = VA - 0x1000000`，调用/取数用 `base + RVA` |

**判别法**：HD_SOD 反汇编地址 `≥ 0x1000000` → 属于 HD_SOD（`RVA = 地址 - 0x1000000`，H3.exe 基址是 0x400000 段、HD_SOD 偏好基址 0x1000000）；地址 `< 0x1000000`（如 `0x5BCB70`、`0x617492`）→ 属于 **H3.exe 本体**，H3API 常量就是这么写的。

**踩坑实例（round-14，随身空间界面整块打不开）**：把 `0x5BCB70`/`0x617492` 当 HD_SOD RVA 且加了基址 → 跳到 HD_SOD 别的代码，最终在 `.data` 段执行，`0xC0000005 写入 0xC76ABA00 addr=HD_SOD+0x10FB609`；attach 抛异常中断，`随身空间UI: attached` 日志从未出现，随身空间面板不创建。修法：**改用 H3API 官方路径**（不自己解析这三个指针）：`H3ObjectAllocator<H3DlgTextPcx>().allocate(1)`（H3API 已证 `sizeof(H3DlgTextPcx)==0x54`，与原生 `new(0x54)` 完全一致，析构归 dialog owned-list）+ `THISCALL_12(0x5BCB70, …)`；悬停更新也走 H3API：`SetText`→`vSetText`(=原生 `vtable[13]`，H3API 注记 `[v34]`)、`Draw`→`vDrawToWindow`(=原生 `vtable[4]`)、`Refresh` 经父对话框刷屏（对应原生 `0x10FAA10` 效果）。**附带的硬约束**：MSVC 不允许在“需要对象展开”（函数里有 std::vector 等局部对象）的函数里用 `__try`（C2712）——含 SEH 的创建逻辑必须拆成独立小函数，否则 `WarehouseUiAttach_` 直接编译不过。

- 字符串表位置：`"Backpack"` RVA 0x1426A4、`"BkPack.pcx"` 0x1426B0、`"def.SpScrArt"` 0x1426BC、`"artifact.def"` 0x1426CC（.rdata）；创建代码在构造函数 `0x039B72..0x39DB5` + 状态条 `0x039DD3`（`H3DlgPcx` 走 `0x01005E40`，文本走 `0x00617492`+thiscall `0x005BC6A0` 即 `H3DlgText`）。
- **`0x01006620` 不是画底图**：它读 `[0x6992D0]+0x40` 绘制对象，4 次 thiscall `0x0044E2C0`（暗化/阴影条）：右 `(x+w, y+9, 7, h-9)`、`(x+w, y+8, 8, h-8)`、底 `(x+9, y+h, w-2, 7)`、`(x+8, y+h, w, 8)`；stdcall ret 0x10，可被插件直接转发调用（H3RndNew 已在 attach 时同款调用画随身空间面板阴影）。
- 卷轴/普通宝物分支由全局 `0x01157FB8` 判别；宝物ID有符号比较 `<0`（`jl`）的槽不建 DEF；不是 ID=0。
- 未 dump 段：构造函数 `0x039E1B..0x039E66`（状态条后续/模态前收尾约 0x4B 字节）。

## 6. 生产消费方式（H3RndNew 阶段 B/C/D 及 2026-10-13 同构改版）

- `0x039E66` LoHook：attach（布局锚点取 `GetList()` 中 ID 1000 控件实际坐标）、保存并在 `dlg+0x70` 写入 `__stdcall(this,msg)` 包装。
- `0x039E80` LoHook：detach（恢复原 callback 指针、关闭 session）。
- 事务成功后置 `dlg+0x7C = -2` 并 `CloseDialog`，走原生"重建背包"重开路径，icon/hit/tooltip/状态栏由游戏自己重建。
- 验证入口：`tests/warehouse_ui_abi.inc.cpp`（离线 0x1A 复刻 + 真实 patcher）与 `tests/warehouse_ui_flow_test.cpp`（纯布局/事务模型），全量回归 PASS；游戏内行为留给用户实机验收。
- 2026-10-13 用户实机反馈"面板过宽、无背景"后改版：随身空间面板固定 405 宽与完整背包一致，`BkPack.pcx` 背景放网格原点，标题条 405×30 用 `bigfont.fnt`，64 槽（8×8，步距 46，DEF 44×44 偏 +2,+1）与原生网格同构；锚点 = `GetList()` 中 ID 1000 控件坐标 − (18,50)。布局最小屏宽 834，不足 fail closed。
- 2026-10-13 第二轮（用户裁定"抄整个扩展界面，比它高一点点"）：面板高 459→**523**（+顶部 Tab 行 32 预留 +底部 32 分页行）；网格原点下移 (18,82)；attach 时直接转发调用 `HD_SOD+0x6620` 画同款右/底阴影（Install 缓存函数指针，CrashGuard __try 内）；最小屏高门槛随之 459→523（800×600 仍可显示，宽 834 fail）。
- 2026-10-13 第三轮（用户反馈"格子外空白"）：完整背包非格子区显示的是原画面+阴影，而随身空间面板区底下是黑边；补 H3DlgPcx16 整块底板 405×523：`BackgroundRegion`(diboxback.pcx 256×256 平铺) + `FrameRegion`(dialogbox.def 玩家色边框，色=hero->owner)，原版对话框标准做法。（第三轮的通用 DIBOXBACK 手工拼板方案已在第 7 节被推翻，见下。）

## 7. 整窗背景生成器更正（2026-10-13，只读逆向已证实）

此前第三轮记录“完整背包非格子区显示原画面+阴影”以及用通用 DIBOXBACK/DLGBOX 拼随身空间整窗的描述均不正确，现以完整反汇编 `D:\\logs\\dsh\\scripts\\h3-warehouse-skin\\fadb0-complete.txt` 和资源解析报告 `skin-analysis.txt` 为准：

- 构造函数 RVA `0x039B25` 调 HD_SOD RVA `0x0FADB0`，完整范围 `[0x0FADB0,0x0FB175)`，长度 `0x3C5`。签名 `H3DlgPcx16* __fastcall(x,y,width,height,itemId,statusBar,colorIndex)`；ECX=x、EDX=y，五个栈参数，`ret 0x14`。原生完整背包参数 `(x,y,405,459,0,1,color)`。
- 返回控件 `H3DlgPcx16*` 的 `+0x30` 为 `H3LoadedPcx16*` 画布；画布自己的 `+0x30` 才是像素 buffer。背景由 `DiBoxBck.PCX` 256×256 裁剪平铺和 `dialgbox.def` 11 帧拼成，不是独立 `sb...` 文件。`sb%.4u%.4u%.1u%.1u` 只作为资源管理器运行时缓存 key，参数为宽、高、`!statusBar`、颜色。
- 背景先做底纹四块平铺，再绘制边缘及四角；statusBar 非零选帧 8/9/10（带底部状态槽），零选 2/3/7。资源位于 `Data\\H3bitmap.lod` 与 `Data\\H3sprite.lod`。离线重建 `405×459` 与扩高 `405×523` 对照图在 `D:\\logs\\dsh\\scripts\\h3-warehouse-skin\\background_comparison.png`；未运行游戏，不能据此宣称实机像素验收通过。
- 底部 `389×18` 状态文字另由 H3DlgTextPcx 构造，位置 `(x+8,y+433)`、ID 777，保存至 `dlg+0x74`；不是背景 item。

## 8. 双层交互与消息中和（2026-10-13 第四轮，静态逆向 + 离线回归）

用户裁定交互契约：背包扩展打开时只显示"随身空间"按钮；点击后才展开随身空间层（同一 dialog owned-items，游戏内顶层模态即"置顶"）；随身空间关闭按钮只收起随身空间层；**随身空间展开时 Esc 只收起随身空间层，随身空间关闭时 Esc 保持原生关闭背包**。

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
- 【round-6 修正】Tab改为12项而非14项。机械（slot 13..16）与魔法书（slot 17）不会进入背包，也就不会出现在随身空间列表里，因此不列页签；`SlotTab` 仍保留 `Machine/Spellbook` 语义但 `kTabOrder` 只含12项，`IsBackpackSlot(slot)` 拒绝 13..17 使 `TabMatches` 对这两类恒为 false。窗口显示4项，箭头只改变 `TabOffsetShift`，所有页签控件归 panel owned-items。常规定义为全部道具入口；scroll artifact id=1优先，id=0魔法书仍查询原生 `GetSlot`。
- 【round-6 废止】`一键取出` ID 30201、`一键放入` ID 30202，只使用活动Tab过滤；`RetrieveAll/DepositAll` 在私有候选完整准备后一次提交 epoch。第五轮曾在成功后按原生 `dlg+0x7C=-2` 重建重开来刷新图标/tooltip/hit；round-6 用户裁定“随身空间打开后移动道具不得关闭随身空间”，改为活窗口内 `WarehouseUiRefreshAfterMove_` 就地刷新（重算筛选/翻页/图标帧/计数 + 局部重绘），`-2` 与 `CloseDialog` 不再出现在成功路径。

## 10. 第五轮缺陷修复（2026-10-13，机器码证据确认；其中“关闭顺序”条 round-6 已废止）

- **成功事务的关闭顺序（第五轮曾采用，round-6 已废止）**：`H3Msg::CloseDialog()`（H3API 约 29358）实际跳到 `0x00491640`，写入 `command=0x200`、`subtype=0xA`、`itemId=0xA` 并返回 `2`（证据：`D:\logs\dsh\scripts\h3-warehouse-ui\modal-close-shade.txt`）。完整背包 modal loop 只有在 callback 返回 `2` 且消息仍为 `0x200/0xA` 时才退出并读取 `dlg+0x7C`（`modal-loop.txt` 114–124）。第五轮因此让成功事务在原生 callback 返回后写 `dlg+0x7C=-2`、调 `CloseDialog` 并返回 `2`。该机制本身仍然成立，但 round-6 用户要求随身空间打开期间移动道具不得关闭随身空间，故生产路径不再下发 END_DIALOG；`CloseDialog`/`dlg+0x7C` 只保留为逆向事实记录。
- **布局拒绝而不是假平移**：`MakeLayout` 在两侧空间不足时曾规划把背包放到左缘，但 StageB 没有移动原生背包背景、标题、状态条、命中项或 DEF。因此 Attach 现在要求 `layout.backpack.x/y` 与实际 ID 1000 锚定出的原点完全一致，否则 fail closed 保留原生背包，避免同一 dialog 两套命中项重叠。
- **Hook 安装原子性**：modal attach/end 两只 `WriteLoHook` 必须同时存在；任一失败时对已创建的另一只调用 `LoHook::Destroy()` 并清指针，`g_wh_ui_installed_` 保持 false；attach 入口也检查该标记，避免只安装半套 Hook 后产生永不 detach 的 vtable/PCX 裸指针残留。
- 修复后全量 BAT 回归（18:08 终版）：主 DLL 与测试工程 0 warning/0 error；warehouse UI flow 170（含回调关闭顺序与布局 fail-closed 用例，顺序由生产共用 `WarehouseUiCallback.hpp::CallNativeThenFinalize` 保证）、PCX 286、UI 状态机/11 指纹 77、LoHook ABI、真实 patcher callback/RNG 并发均 PASS；部署 Release 与 Packs SHA256 均为 `C8BFD5AF792DBB2735AAECA1570B816FC8D3561C0697491EF41EDAAD4B3F5DF9`。仍未启动游戏，`-2` 重建、实际重打与存读档循环由用户验收。

## 11. 第六轮：图标层、命中状态位与“移动不关闭”（2026-10-13，机器码 + 生产接线）

用户 round-6 裁定：按钮沿用 H3MegaDesc 原图质感但用文字；标题与原生背包标题同字号/同字体/同亮度；**随身空间打开后无论怎么移动道具都不关闭，只有 X 或 Esc 才收起**；关闭控件是极端右上角的小四态 X；页签去掉机械与魔法书（12项），两个一键按钮左右交换。

- **owned-items 命中测试（`0x5FF970` → `0x5FF9A0`，反编译 `blk_5f0000.c`）**：`0x5FF9A0(dlg, x, y)` 先把坐标减去 `dlg+0x18/0x1C`（dialog 客户区原点），再从 owned-list 尾部（`dlg+0x38`）向前逐项（`iVar3 -= 4`）扫描；命中条件是矩形包含 **且** `state(+0x16) & 2` 置位 **且** `(state & 8) == 0` **且** `(state & 0x1000) == 0`。`0x5FF970` 只是把命中项 `+0x10` 的 `INT16` ID 取出来，未命中返回 -1。
- 由此推论并已按此实现：`HideDeactivate()` 清 ACTIVE|VISIBLE，是“既不显示也不参与命中”的正确调用；`Hide()` 只清 VISIBLE，**隐藏但仍会被原生命中**。同一 ID 存在多个控件时（本轮的普通/卷轴双覆盖层），只要非选中的那些都 `HideDeactivate`，逆序扫描就只会命中唯一活动项，重复 ID 是安全的。
- **`H3DlgDef::SetFrame` 只写 `defFrame`，不加载/替换 `loadedDef`**（H3API `0x4EA800` 创建时确定 DEF 资源，`SetFrame` 见 `H3API.hpp` 27545）。因此“同一个背包格可能装普通宝物、也可能装卷轴（`def.SpScrArt` 帧=法术ID）”无法靠 SetFrame 完成资源切换：生产做法是每格创建两个同 ID 控件（`artifact.def` 与 `HDassets::SCROLL_SMALL`），按当前记录只激活其中一个；原生原件自接管起一直停用，否则收起后转移过的格子会显示构造时的旧帧。
- **HD 卷轴模式全局是 `0x01157FB8`（RVA `0x157FB8`）**，非零时卷轴走 `def.SpScrArt`、帧=subtype，否则走 `artifact.def`、帧=artifactId；运行时由 `MakeIconView` 纯函数选择资源族。
- **原生标题参数（反汇编确证）**：`H3DlgText(x, y+18, 405, 30, text, "bigfont.fnt", color = eTextColor::REGULAR (=1), id = 0, align = MIDDLE_CENTER, bkColor = 0)`。随身空间标题复用完全相同的尺寸/字体/颜色/对齐，才能保证与原生背包标题同字号、同亮度。
- **原生图标 DEF 几何**：44×44，网格原点相对扩展窗原点 `(+18,+50)`，格内 DEF 偏移 `(+2,+1)`，步距 46。
- **展开态必须自己处理图标 CLICK**：自建覆盖 DEF 与原生命中项共用 ID 区间（`1000..1063` 槽命中、`2000..2063` 宝物图标）。若不适配这些 ID 的 CLICK，原生 callback 会落到 `0x039987` 的未知回退关闭分支并写 `dlg+0x78=-1`，表现为“点一下背包就关窗”。
- **“移动不关闭”的生产语义**：成功转移只调 `WarehouseUiRefreshAfterMove_`（就地重算筛选/翻页/图标帧/计数 + 局部重绘），不再写 `dlg+0x7C=-2`，也不调 `CloseDialog`；收起随身空间层只有两条路径——关闭按钮 ID 30060 与展开态 Esc。背包 modal 本身仍由原生 Esc（随身空间已收起时）关闭，右键/网络/超时/未知路径继续透传。
- **点击边沿策略**：随身空间控件只中和 `LBUTTON_DOWN(0xC)`，动作只在 `LBUTTON_CLICK(0xD)` 执行一次；`IsWarehouseControlId` 覆盖 `30050/30051` 翻页箭头、`30060..30202`（关闭/打开/一键取出/一键放入/30100..30163 槽位）、`30300..30311` 页签，刻意不含背景 ID `30000..30004`。展开态下 `2000..2063` 的 DOWN 与 CLICK 都由本模块接管。

## 12. 待验证（不混入确认段）
- `Arg(1)/Arg(2)` 的参数语义（生产代码仅作锚点缺失时的回退，不依赖）。
- Esc/右键/联机关闭路径、HeldArtifact 与第一击拦截的实机交互。
- round-6 新增待验证：活窗口就地刷新（不重建）后，原生 tooltip/状态栏是否仍与新数据一致；覆盖层 DEF 与原生命中项同 ID 同时存在时，长时间悬停/拖拽是否出现旧帧残留；`0x157FB8` 卷轴开关在运行时是否确实按 HD 设置翻转。
- 必须由用户实机验收：四态按钮观感是否与 H3MegaDesc 一致、中文标题亮度、极端右上小 X 命中范围、12 页签左右滚动、两个一键按钮左右语义、以及“移动道具后随身空间保持打开”。
- 双层交互的实机效果：随身空间按钮位置/字体渲染（GBK 字节串 + bigfont）、save-under 回写是否残留、展开态外部左键中和后的实际行为、Esc 分流第一击是否真的不关背包——均需用户游戏内验收。
- 消息中和（改写 `H3Msg` 后再调原生 callback）对 command=4 分支的副作用：静态看只做 hit-test，但 `0x396C0` 起 `ItemCommand(dlg,itemId,...)` 仍会执行；若实机出现状态栏/悬停异常，需改为 return_address 重定向方案（`0x0396AB` LoHook + 跳 `0x0399F4` 出口，保留 `[ebp-0x28]` 返回值）。

## 13. 第七轮（2026-10-13）：命中项是覆盖控件的坐标真源

- **错位事故与教训**：第六轮把随身空间面板网格原点 `kGridOriginDY=82`（含 Tab 行 +32）误用于背包覆盖图标；原生背包图标实际在窗口 +50，导致物品比网格整体低 32px（用户观感“背包初始位置上移、物品没跟上”）。凡是往原生弹窗里加同位覆盖控件，坐标一律取自原生现存控件的实际 `GetX()/GetY()`，不要从常量推导；本例正确做法：覆盖 DEF = 原生命中项(1000+i) 坐标 + (2,1)（与原生 DEF 图标相对 hit 的格内偏移一致）。新增 `kBackpackGridOriginDY=50` 与随身空间原点 82 彻底分开。
- **分页控件 ID 扩展**：底部箭头复用 arrow 素材但为独立实例（ID 30050/30051，与页签行 30310/30311 同素材不同对象）；页码按钮 30400..30403 为 36x22 两态底图 + id=0 的 H3DlgText 数字（文本控件不参与 0x5FF9A0 命中测试，点击落在下层透明命中项——这与原生标题/状态条文本行为一致，round 4-6 从未出现“点标题关窗”即为旁证）。
- **布局配置**：`[WarehouseUI]` 节七键两层 ini（default/user），attach 时重读；超范围钳制回退。随身空间控件坐标从此不再写死在源码。
- **语义裁定（非逆向）**：一键=全量（常规页语义）；放入落点无关（面板内任意点击即追加提交）；未完成移动=取消（选择只存模块内存，不写原生数组/held，故天然回原位）。

## 14. 第八轮（2026-10-14）：宝物表 position 是 1-based、空槽按下的关窗路径与消息分类边界

**【第十轮更正，2026-10-14】**本节“1-based”结论只在 raw 1..7 段成立，高段被第十轮实机推翻（见 §17）。保留原文以记录推理链。

- **宝物表 `position` 运行期为 1-based（0 表示无装备位）**——本轮最关键的一条纠正。归类错位的实机症状链（用户报告）是：头部页为空、肩部里显示头的装备、胸甲页显示的是戒指类道具，即**每个分类整体后移一位**；反推唯一自洽解释是分类表按 0-based 的 `eArtifactSlots`（H3API/NH3API：HEAD=0、SHOULDERS=1、NECK=2、RIGHT_HAND=3、LEFT_HAND=4、TORSO=5、RING=6/7、FEET=8、MISC1..4=9..12、BALLISTA..CATAPULT=13..16、SPELLBOOK=17、MISC5=18）编写，而运行时读到的是同一批位置的 **+1 表示**（raw 1=头部、raw 6=胸甲、raw 7/8=双戒指、raw 19=杂物5、raw 0=未装备）。修法是分类前先归一化：`raw<=0 → 无位置`，否则 `raw-1`。**注意与随身空间自有 `Heroes3Src` 复原（NECK=1、CLOAK=2、MISC1..5=9..13、SPELLBOOK=14、机器 15..18）不是同一编号体系，不要混用**；两者只在“0-based 分类 ↔ 1-based 表值”这一层换算。
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
- H3RndNew 随身空间页签行据此实现滚轮滚动：仅当光标在页签行内且窗口实际移动时消费该消息（中和为 MOUSE_OVER）；行外/未展开/已到边界透传。`H3DlgItem::TranslateUnprocessedMessage`（H3API 27853-27877）证明控件内滚轮会以 `NotifyParent` 回流 dialog 层，不消费即走原路径——这也解释了为什么“行内滚轮”必须在 dialog 回调层处理。

## 17. 第十轮（2026-10-14）：宝物表 position 的分段编码定案（推翻第八轮“均匀 1-based”）

**症状**（第十轮用户实测，在均匀 `raw-1` 归一化部署后）：戒指页 = 戒指+靴子；靴子页全是杂物；杂物页应为空。

**定案**：运行时 `H3ArtifactSetup::position` 是**分段**编码，不是均匀偏移——
- raw 0 = 无装备位；
- raw 1..6 = 头/肩/颈/右手/左手/胸甲（相对 0-based 规范 **+1**）；
- raw **7 = 戒指族单值**（规范中 6/7 双戒指位在表中只出现一个，戒指族归到 6）；
- raw **8 起与 0-based 规范完全一致**：8=靴子、9..12=杂物1..4、13..16=战争机器、17=魔法书、18=杂物5。

三轮症状链交叉验证：修前（无归一化）只有 raw 1..7 段错位（头部空/肩显头/胸甲进戒指页），靴子=8、杂物=9 落在规范槽位**本来就正确**——与用户第八轮只报“从胸甲往前到头部全错”完全吻合；均匀 `-1` 修好低段的同时把高段错了一格（靴→7 戒指页、杂物1→8 靴子页、杂物5 18→17 被魔法书拒绝→杂物页空）。修法：`raw<=6 → raw-1；raw==7 → 6；raw>=8 → 原值`。

**证据边界**：raw 8=靴子、raw 9=杂物族由本轮实机锁定；raw 10..18 按编号连续性推定（未逐值实机对拍）。静态取证依旧失败：exe 中包装 `0x660B68` 处的指针指向 `0x693A58`，落在 `.data` 的**零初始化区**（raw size 0x34000 只覆盖到 RVA 0x292000，0x693A58 的 RVA 0x293A58 在 BSS 段），文件里该偏移读到的实际是 `.rsrc` 内容（旧笔记里的 “NewWeek3.def 垃圾”即由此而来）——表是运行时构建的，静态文件里不存在。NH3API 佐证地址语义：`akArtifactTraits=0x693A58`（144 项 ×0x20，slot 在 +8）、组合表 `0x693938`、槽位特征表 `akArtifactSlotTraits=0x694C58`（19 项）；反编译初始化代码在 `blk_440000.c:28385` 附近逐项填充。要机器码级定案仍需活进程 dump。

## 18. 第十一轮（2026-10-15）：随身空间面板可见文案的两处来源与素材重出流程

用户裁定把可见文案统一改成「随身空间」——背包上的打开按钮与面板标题两处**来源完全不同**，改法也不同：

| 可见文案 | 真正来源 | 改法 |
|---|---|---|
| 背包界面左上角打开按钮上的字 | **烘焙在素材里**：`pcx/btn_open0..3.pcx`（66×32 四态，24 位真彩 PCX = 3 plane，非 8bit 调色板） | 必须重出那 4 张图；只改 C++ 常量在正常路径**看不到任何变化** |
| 随身空间面板顶部标题（405×30，bigfont.fnt REGULAR 居中） | 代码里的 GBK 常量 `kWhUiGbkWarehouse_`（`WarehouseUiPanel.inc.cpp`），创建 `H3DlgText` | 改常量字节即可 |
| 打开按钮的**降级** caption（素材不可用时的兜底 `H3DlgCaptionButton`） | 同一个 `kWhUiGbkWarehouse_` | 同上 |

由此得到一条通用结论：本工程 UI 的中文文案一律用 **GBK 字节数组**常量（游戏字体不保证中文字形；按钮类若连字形都不参与，则直接烘焙进 PCX）。搜索“还有哪处硬编码了某个文案”时，要按 GBK 字节序搜（例如「随身空间」= `CB E6 C9 ED BF D5 BC E4`），不能按 UTF-8 搜。

### 18.1 按钮素材的出图方法（沿用原生成器，不重新设计）

生成器：`H3RndNew\scripts\make_whui_assets.py`（H3Space 的素材即其产物，整体搬迁而来；2026-10-15 起由平铺 `whui/` 改为仓库根 `pcx/`（贴图）与 `png/`（预览图），生成器输出目录需同步）。关键约束：

- **底图**：从 `H3BattleStore\img\HA_bg.pcx`（680×548）图形**正中直裁 66×32**（left=307 top=258），不平铺、不缩放。实测该 66×32 与 `H3RndNew\whui_src\HA_bg_crop.pcx` **逐像素相同**——即用户所说的“从 HA_bg.pcx 中间截取”就是既有做法本身。小尺寸控件（36×22/28×22/24×24/18×22）再从这 66×32 正中二次直裁。
- **四态** = 同一底图 × `STATE_TINT`（normal 1.0 / pressed 0.845 / highlight 1.35 / disabled 0.853）+ 墨色 `INK_*` + 按压态文字下移 1px（`dy=1`）。
- **金框**：`apply_reference_frame()` 从 `whui_src/bv_frmL.pcx`（50×42）取样绘制 1px 边框，不缩放窄化。
- **字号**：`make_button()` 里 `size = 16 if len(text) <= 2 else 15`，文字宽上限 `BTN_W - 12 = 54`，超宽用 LANCZOS 压到 54。所以改成 4 字「随身空间」后**自动与「一键取出/一键放入」同规格**，无需另调字号。

### 18.2 可复用的验证手法：全量重出 + 逐文件哈希比对

改素材最怕“只想改 A，结果 B 也被动了”。本轮做法：把生成器**原样复制**到临时目录（只改 open 按钮文案那一处字符串），`SRC` 指向临时素材源（其中 `HA_bg_crop.pcx` 按用户指定从 `HA_bg.pcx` 正中重切，并断言与原件逐像素相同），`OUT` 指向临时目录，跑完整流程（50 张 PCX + preview.png），再与现有素材目录**逐文件 sha256 比对**：

```
相同: 46  变化: 5  新出: 无  多余: 无
变化的文件: btn_open0..3.pcx, preview.png
```

46 个非目标文件逐字节相同，是“只改了文案、纹理/金框/其它控件零改动”的强证据，比肉眼比对可靠；同时也证明本次 Pillow 版本与原出图环境在像素级一致。这套手法适用于任何“文案/局部改动 + 大批量素材”的场景。

### 18.3 落地与副作用

- `kWhUiGbkWarehouse_` 改为 GBK「随身空间」（`CB E6 C9 ED BF D5 BC E4`），并补注释说明它与标题/降级 caption/烘焙素材三者的关系。
- `使用说明.txt`、`H3Space.default.ini` 里描述屏幕文案的措辞同步（这两个文件是 **UTF-8 无 BOM + CRLF**，与 `.cpp/.md` 同规，不是 GBK）。
- 回归：`build.bat` 0 警告 0 错误；四套单测全绿（`warehouse UI PCX: 50 assets` 直接解码新图，校验 66×32 尺寸与色彩分布）；部署后 DLL 与 5 个素材同哈希。
- 遗留：合并前插件 `H3RndNew` 的同款素材未随本轮改动（用户后续会删除合并前的项目；两个插件本就不同时加载）。

### 18.4 术语统一（2026-10-15，全库扫一遍）

用户裁定：合并后的本项目与笔记项目里，该功能的中文名一律写成「随身空间」，不留旧写法；合并前的源项目后续由用户删除。

- 范围：H3Space 24 个文件 246 行（代码注释、日志串、测试注释、README、使用说明、ini、docs、deploy.ps1/pack.ps1）、H3Note 6 个文件 64 行。
- **最大的坑是语义歧义**：汉语旧名同时可指 git 版本库。按语义保留（整行跳过或事后回改）的一共 5 处——本库合入的三个插件、本库是三个源插件合并成的单 TU、库根 `H3Env.ps1`、本库自研子项目约定、`H3Plugins` 库与其内部分析——这些是 repository 义，改了就读不通。所以批量替换前必须先按上下文分类（本次 304 处里 297 处是功能名、7 处需人工判），改完再逐条复核 diff；本次共抓回 6 处误伤。
- **自引用句必须手工改写**：记录“改名这件事”的句子、举例里的旧名、脚本输出块里的措辞，盲替后会变成「随身空间→随身空间」这类鬼话；本次手工改了 4 处（含本节 18.2 的举例）。
- 连写要先消解再泛替，避免双写：括注形式、`随身空间+旧名`、`随身+旧名`、`156 旧名` 各一条规则排在泛替之前。
- 验证四连：① 残留扫描（期望只剩 repository 义那几处）；② GBK 文件按字节查（`.bat`/`.rc` 是 GBK，只按 UTF-8 扫会漏）；③ 伪影扫描（连续重复、括号套括号）；④ 编码体检（`.ps1` 带 BOM、`.md/.cpp/.txt/.ini` 不带 BOM、无裸 LF）。
- 副作用：改到了代码注释与日志串 → 必须重编重部署（新 DLL 哈希 `9E21F056…`，四套单测全绿）；被笔记链接的文件名也要跟着改，否则链接断掉——本次把 `H3RndNew/docs` 两个被引用的文档同步改名并修好其内部链接与标题。

## 19. 第十二轮（2026-10-15）：随身空间"战斗后丢失"的根因——无附件档被显式清空

玩家反馈「随身空间内的东西，在战斗后会丢失」。**无日志，纯代码定案**（用户明确要求），结论：**确有此 BUG，已修复**。

### 19.1 为什么"战斗"能碰到随身空间的存储

随身空间插件**没有任何战斗钩子**（`CrashFix` 只补 0x466710/0x43E790/0x43E720 三个战斗崩溃点，`SaveLoadEnhance` 只挂 0x4BEB60）。物品丢失只能经由**内存态被清/被替换**，而 `g_warehouse_` 在整个插件里只有两条清空路径：

| 清空路径 | 触发条件 | 判定 |
|---|---|---|
| `OnWhStartGame_`（`WarehouseStore.inc.cpp`） | `g_scenario_context_ == kScenarioNewGame_` 时对 0x58BFB0 建档入口调 `ClearForNewGame` | **正确**：上下文由场景对话框（ctor + 每条消息前）观察、`ClassifyScenarioContext_(+0x64!=0, +0x65!=0)` 两者皆 0 才算新局；`OnStartGame_`（真随机段）每次建档都 `ConsumeScenarioContext_()`，上下文不会陈旧 |
| `WhAfterLoad_` 的 `NoAttachmentLegacyUnknown` 分支 | 读档时档里**没有**随身空间附件块 | **缺陷**：无条件 `ClearForNewGame`，清空全部 156 个随身空间 |

战斗本身不动存储；**战斗前后必然发生的存档/读档**才是触发器（战前存档、战败读档、重打读档、自动存档）。

### 19.2 根因：「档里没有随身空间块」是歧义，不是"确认旧档"

旧实现的注释自称"门禁全绿仍无自有块 = 确认从未有过随身空间块的原生档"，这个推理**不成立**——`ValidateObservation` 只证明"这次捕获是可信的"，完全不能证明"这个档从来没有过附件"。无附件至少有四类来源：

1. 真正从未有过随身空间的旧档；
2. **本次存档没能附加**——`WhAfterSave_` 有六条 fail-closed 早退（原生存档未成功 / 处于锁定态 / 未捕获到实际路径 / 读取已保存文件失败 / 原生 gzip 边界不可信 / `PlanSave` 策略拒绝或写失败），每条都让那一次存档**不带附件**；
3. **锁定态下所有存档一律不附加**（`g_wh_locked_` 在读到非法附件后置位，直到下次成功读档或新局才解除）→ 形成一个自锁环：一次坏档 → 后续每一档都无附件；
4. 附件被第三方工具裁掉，或原子替换（临时文件 + `MoveFileExA`）中断。

其中 2/3/4 之后再读档，旧实现就把玩家现有物品**全部清空**——不可恢复。真旧档下清空无害（内存本来就空），这正是它一直没被当成 bug 的原因。

**更关键的是它违反了自己纯层的契约**：`WarehouseStore.hpp` 对 `NoAttachment` 写得很清楚——"A missing attachment has two possible meanings (legacy save or lost/cut attachment). This policy never clears/replaces State for that ambiguous case. The adapter/application must make an explicit, user-visible legacy decision." 适配层却静默清空，等于把歧义一律判成旧档。

### 19.3 修复（round-23）

`WhAfterLoad_` 的该分支改为**保留内存内容**：不再调 `ClearForNewGame`，仍解除锁定（让下一次存档把保留下来的内容重新写回，数据在磁盘上续存），日志改为「该档无随身空间块（歧义：旧档或本次未附加），保留当前随身空间内容不清空（保留 N 件，已解除锁定）」。

- 真旧档：内存本空，效果与清空**完全等价**（不会凭空长出物品）；
- 无附件但内存有物品：不再丢，且下一次存档即把它写回。

### 19.4 验证（离线，无需游戏）

`tests\hook_abi_test.cpp` 的随身空间段用 mock 钩子 + 真实临时文件驱动生产 `OnSaveGame_`/`OnLoadGame_`/`OnStreamOpen_`/`OnStreamClose_`，新增第 4 段：

- 先制造"已锁定 + 状态非空"，把文件重写成**只有原生 gzip、无附件**的夹具，再走一次读档；
- 断言：仍保留 2 件记录、锁定被解除、紧接着的一次存档把 `H3WHBGN1` 重新附加。

**证伪实验**（确认测试抓的是真根因，不是假测试）：把该分支临时改回 `ClearForNewGame` 后重编重跑 → `FAIL hook ABI: no-attachment save never clears the live warehouse (round-23 data-loss fix)`；还原修复后全绿。

**坑**：存档前必须把 mock 流模式设回 `"wb"`（`g_wh_test_mode_`）。读档用例留下的 `"rb"` 会让捕获窗口匹配不到写模式 → `WhAfterSave_` 走"未捕获实际路径"fail-closed → 不附加，测试会误报在"重新附加"那条断言上。

回归：`build_and_deploy.bat` 0 警告 0 错误；16 套单测全绿（含 `PASS warehouse hooks: …`）；部署 DLL 与 `Release\H3Space.dll` 同哈希 `93892863…C6F9865`。游戏内验证由玩家执行。文档同步：`README.md`、`docs\骨架模块说明.md`。

## 20. 第十三轮（2026-10-15）：§19 结论修正——清空的正确时点是"游戏结束"，并查清 N/L 离开战局的链路

### 20.1 用户裁定（推翻 §19 的语义）

§19 把"读档发现档里没有随身空间块 → 清空内存"整体判为 bug 并改为"绝不清空"。玩家原话（2026-10-15）：

> 游戏结束时（回到新游戏或读档或其它系统界面，特征是**除非读档，否则不可能再回到当前游戏**），是应该清空所有英雄的随身空间的内存的。

即：**清空这件事本身是对的**，错的是时点与判据——不该用"档里没有附件"这个歧义条件去清，而应该用"这一局结束了"这个事件去清。随身空间内存的存活期 = **一局游戏**。

### 20.2 冒险界面按 N/L 离开战局的链路（反编译证据）

三个"命令分派"入口都会汇到同一个"建并运行选图/读档对话框"的函数 `FUN_004180c0 @ 0x4180C0`（624 字节，`src/h3/uncategorized/blk_410000.c:25443`）：

| 分派点 | 位置 | 分支 |
|---|---|---|
| `FUN_00408ba0 @ 0x408BA0` | `blk_400000.c:17354` | `case 0x1f:` → `FUN_004180c0(); return 1;` |
| `FUN_0041ab60 @ 0x41AB60` | `audio_video/blk_410000.c:700` | `case 0x6a:` → `FUN_004180c0(); break;` |
| `FUN_004eea70 @ 0x4EEA70` | `network/blk_4e0000.c:4114` | 同一函数内另有三处分派到 `FUN_004f0b20 @ 0x4F0B20`（新游戏界面，`FUN_00579ce0(0)`）与 `FUN_004f0ca0 @ 0x4F0CA0`（读档界面，`FUN_00579ce0(1)`），见 `blk_4f0000.c:726 / 988`，case 0x64 / 0x65 / 0x67 |

`FUN_004180c0` 体内序列（行号为 `blk_410000.c`，该导出每两行夹一个空行）：

```
25616: FUN_00618060();
25624: if (extraout_CL == '\0') { FUN_0041a240(); for (i=0..7) if (!DAT_00699538[0x1f636+i]) FUN_004ce600(i) 计数 }
25700: FUN_0050cea0();
25704: if (DAT_0069779c == '\0') 用 &DAT_006603f0 否则用 &DAT_006603f8 → FUN_006179de(...)  // 组标题串
25756: local_1c = 2;
25764: FUN_00579ce0();     // 选图/读档对话框 ctor（已挂钩 0x579CE0）
25780: FUN_00584ec0();     // 模态运行
25792: FUN_00583e10();
25812: if ((char)unaff_EDI == '\0') FUN_00417380();
```

**关键结论一：打开界面这一步不卸载当前游戏。** 三处分派器所在的 `blk_400000.c` / `blk_410000.c` / `network/blk_4e0000.c` 里**没有任何**会话丢弃调用（`FUN_004bee60` 的全部调用点见下），只有屏幕状态位（`DAT_00699538+0x1f69d`）、`DAT_006992d0+0x38` 判定与 `FUN_004c5ac0(会话+0x1f7d4, 会话+0x1f6d9, 0)`。玩家"回不到当前局"是因为该界面没有回到战局的通路，不是内存已被释放。

### 20.3 引擎自己"丢弃当前会话"的那一步：`FUN_004bee60 @ 0x4BEE60`

`FUN_004bee60`（387 字节，`src/h3/uncategorized/blk_4b0000.c:44585`）= 会话重置：清 `DAT_0069956c / DAT_0069955c=-1 / DAT_00698884 / DAT_00697798 / DAT_006977a0 / DAT_0069844c`；把 `DAT_006a5dc4[0x20]+0x30` 的场景路径 `_strncpy` 进 `会话+0x1f4d5`（0x15f 字节）；清 `&DAT_0069fb80` 8 项；复位 `会话+0x7d91`(8) / `+0x137c6`(0x27) / `+0x137ed`(0x9c)；再逐玩家 0..7 调 `FUN_004b8150(i)`、`FUN_004d8990(i)`（二者均为**纯字段复位**，无 free）。

它的执行时点正是"确认新局/读档"：

| 路径 | 证据 |
|---|---|
| 读档 | `FUN_004beff0 @ 0x4BEFF0`（LoadGame，565B，`src/h3/system/blk_4b0000.c:1378`）的**第一条实质语句**就是 `1475: FUN_004bee60();`，之后 `1483: if (param_3 == 0) { DAT_00697308 = 0; ... FUN_004d6eb0(...,&DAT_00677d6c) 读档 ... }` |
| 新局 | `FUN_0058c840 @ 0x58C840`（999B）的 `blk_580000.c:34963: FUN_004bee60();`，随后 `35123: FUN_004c01e0(会话+0x1f7d4, &DAT_00699430, &DAT_0069fb80, mode)` 初始化地图 |

而读档路径本身是在建档入口内部触发的：`FUN_0058bfb0 @ 0x58BFB0` 判 `+0x64 != 0` → `33821: FUN_0058c560 @ 0x58C560` → `blk_580000.c:34308: FUN_004beff0(会话+0x1f6d9, 0, 0)`（LoadGame）。

**关键结论二：当前游戏是在"确认新局/读档"（建档入口 `0x58BFB0` 内部）被引擎重置/替换的，不是在按 N/L 打开界面时。** `FUN_004bee60` 的其它调用点（退出/回主菜单类路径）：`blk_580000.c:761 / 2976 / 7845 / 23491`、`menu/blk_570000.c:7547`（属 `FUN_0057f600 @ 0x57F600`）、`system/blk_4b0000.c:1475`、`ui_assets/blk_450000.c:7639`、`uncategorized/blk_4c0000.c:38255`、`uncategorized/blk_570000.c:29482`；主菜单初始化见 `FUN_004edce0 @ 0x4EDCE0`（`system/blk_4e0000.c:594: DAT_00698450 = 0;`，含 `LoadMenuA`）。

### 20.4 修正后的实现（round-24）

`OnWhStartGame_`（钩 `0x58BFB0`）：**把清空搬到原函数调用之前**，条件从"仅新局"扩为"新局 **或** 读档"，存档上下文不清：

```cpp
static int __stdcall OnWhStartGame_(HiHook* hook, int self)
{
    const LONG context = g_scenario_context_;
    __try {
        if (context == kScenarioNewGame_ || context == kScenarioLoad_) {
            const warehouse::Result cleared = warehouse::ClearForNewGame(g_warehouse_);
            InterlockedExchange(&g_wh_locked_, 0);
            LogInfo("随身空间: 游戏结束（%s），156 个随身空间已清空 result=%d",
                context == kScenarioLoad_ ? "读档确认" : "新局确认", static_cast<int>(cleared));
        }
    } __except (GuardCrashFilter_(GUARD_WH_START, GetExceptionInformation())) {}
    const int result = OnStartGame_(hook, self);   // CrashGuard L2：原函数在 __try 外恰好一次
    return result;
}
```

- **为什么必须前置**：读档发生在 `0x58BFB0` 内部（见 20.3 的表），清空若放在原函数之后，会把刚读回来的附件内容一起抹掉。前置后清空与引擎自己的会话重置（`FUN_004bee60`）同处一次建档调用内，且早于"内容替换"。
- **`WhAfterLoad_` 的 `NoAttachmentLegacyUnknown` 分支降级为兜底**：仍不清空、只解锁并记日志，用于"某次读档绕过建档入口"的异常情形（正常路径下内存已被游戏结束清空，保留与清空等价）；避免异常路径下销毁玩家唯一副本。
- **语义结果**：读一个无附件的档 → 随身空间为空（符合"旧档/new game 从空开始"）；新局 → 空；普通存档 → 完全不动。

### 20.5 验证（离线，无需游戏）

`tests\hook_abi_test.cpp`：

1. 第 1 段断言改为"读档入口清空上一局的随身空间"，并新增"存档入口绝不清空"（`save entry never clears the live warehouse`）；
2. 新增 2b **时序回归**：让 mock 的原函数在内部真走一次读档（`g_wh_start_drives_load_` 开关 + `MockWhStart_` 内调 `MockWhLoad_`，模拟 20.3 证明的"读档在建档函数内部"结构）。上一局残留 `{4,2}`、档里是 `{21,5}`，正确结果必须是 `{21,5}`——若清空发生在原函数之后，结果会是空，断言 `game-end clear runs before the native entry, so the load inside it survives` 即失败。
3. 第 4 段（无附件档兜底不清空 + 下次存档重新附加）保留；证伪实验记录见 §19.4。

回归：`build_and_deploy.bat` 0 警告 0 错误；17 套单测全绿；部署 DLL 与 `Release\H3Space.dll` 同哈希 `AA79187F…`。游戏内验证由玩家执行。

---

## 21. 素材目录调整：`whui\` 平铺 → 仓库根 `pcx\` / `png\`（2026-10-15）

**用户裁定（原话）**：「这个目录里面我看全是资源啊，应该按文件后缀名建立文件夹（同级）pcx png」→ 澄清「不是在 img 下分目录，是仓库根 pcx\ / png」。

即：素材不再放单一平铺目录，而是**与仓库同级、按后缀建目录**——`pcx\`（50 个界面贴图）+ `png\`（预览图），对齐 `H3Auto功能合并进H3BattleStore笔记.md` §7 的同一约定；空掉的 `whui\` 目录删除。用户随后删掉 `img\`（保留占位的目录也不需要），仓库里与 deploy/pack/README/docs 的 `img` 引用一并清掉。

### 21.1 运行期路径（这是改结构的真正代价）

`WarehouseUiButtons.inc.cpp` 的 `WarehouseUiLoadOne_` 用 `GetModuleFileNameW` 取 DLL 目录后拼素材名，原为 `whui\<文件名>`：

```cpp
// 素材在仓库根按后缀分目录（pcx\btn_open0.pcx），部署时同结构复制到插件目录下。
if (swprintf_s(path + used, cap - used, L"pcx\\%hs", filename) <= 0) { ... }
HANDLE file = CreateFileW(path, ...);
if (file == INVALID_HANDLE_VALUE) {
    // 兼容旧版布局（whui\btn_open0.pcx）：老安装目录没跟着改组时不至于整屏无图。
    if (swprintf_s(path + used, cap - used, L"whui\\%hs", filename) > 0) { ... 命中时记一条 LogInfo ... }
}
```

要点：素材是**按文件名运行时加载**（不是编译期资源），所以目录结构一变，代码、部署脚本、打包脚本、测试数据路径必须同步改，否则界面整屏无图（只留 `LogError("随身空间UI: PCX加载失败 %s")`）。加了旧布局兜底，玩家目录未改组时不至于瞎眼。

### 21.2 同步清单（同类改动照抄）

| 位置 | 改动 |
|---|---|
| `modules\WarehouseUiButtons.inc.cpp` | 主路径 `pcx\`，旧 `whui\` 兜底 |
| `tests\warehouse_ui_pcx_test.cpp` | 读 `pcx/<名>`（测试在仓库根运行，`Push-Location $root`，相对路径即仓库根） |
| `deploy.ps1` | 由整树复制 `whui\` 改为遍历 `pcx`、`png` 两目录整树复制（产物落到 `Packs\随身空间\pcx|png\`） |
| `pack.ps1` | 包内路径 `随身空间/pcx/…`、`随身空间/png/…` |
| `README.md` / `使用说明.txt` / `docs\骨架模块说明.md` | 目录树与素材位置描述 |
| `WarehouseUiPanel.inc.cpp` 注释 | "烘焙进 whui/btn_open0..3.pcx" → `pcx/` |

`git mv` 保证 51 个文件都识别为 **rename（100% 相似）**，历史不丢。顺带修掉一处**先行提交的意外删除**：上一轮 `git add -A` 把 `img\.gitkeep` 的磁盘缺失一起提交了；该占位随后按用户要求（`img\` 目录不需要延续）连同 `deploy.ps1`/`pack.ps1` 的整块素材处理、README 目录树、`docs\骨架模块说明.md` 的"`img\` 为空占位"描述一并移除。

验收：`build_and_deploy.bat` 0 警告 0 错误；17 套单测全绿（`PASS warehouse UI PCX: 50 assets …` 即从新目录读到全部 50 个）；部署目录出现 `pcx\`（50）与 `png\`（1），部署 DLL 与 `Release\H3Space.dll` 同哈希 `773755AE…`。游戏目录里上次部署留下的旧 `whui\`（51 个）未删——加载器优先取 `pcx\`，旧目录已失效但无害。

**踩坑**：目录归属要先问清"同级"是相对谁——第一版做成了 `whui\pcx\`、`whui\png\`（理解成"在 whui 里面按后缀分目录"），被用户纠正为"仓库根"。这类结构改动的第一次尝试前，先用一句话把目标结构复述确认，比事后返工便宜。

---

## 22. 随身空间分页行右端「打包日志」按钮（2026-10-15 round-25）

> **round-26 更正（见 §23）**：本节的两处结论已作废——①按钮落点从背包分页行右端**移到 F11 设置窗**（用户裁定）；②`"smallfont.fnt"` 是**游戏里不存在的字体名**（正确名 `smalfont.fnt`），它正是本次 `0xC0000005` 的根因（§23.1）。本节保留作为缺陷引入点的原始记录。

**用户裁定（原话）**：「在背包界面 的右侧,添加一个打包日志的按钮,功能参考"D:\GitHub\H3\H3BattleStore"项目中的打包日志按钮」。

### 22.1 参考件（H3BattleStore）拆到什么程度

`H3BattleStore\modules\BattleUi.inc.cpp:1372 UiPackLogs_()` 是**功能**参考的全部：
①`static DWORD lastPack` + `static bool packing` 双闸（1 秒去抖 + 重入闸，MessageBox 泵消息期间的重入不会重复打包）；②`GuardFlushFaults_("log-feedback", true)` + `LogRecentContext_("log-feedback")` 前置（把崩溃取证上下文也冲进包里）；③`PackRecentLogs_(nullptr, 0, reason, sizeof(reason))`（`nullptr` 合法——H3Space 的 LogPack 同款，内部落 internal_path）；④成功 `MessageBoxW(kLogPackSuccess_)`、失败 `MessageBoxW(reason)`。
它的**绘制**（font->TextDraw + DrawFrame，自绘悬浮条 x=392/宽84）**不照搬**——H3Space 是对话框件体系，两类 UI 不可互换。

### 22.2 H3Space 落点与几何（右侧 = 分页行右端）

- 落位：分页行（整理按钮所在行）右端、贴右 18px（`kPagerRightInset`），与「整理」左右对称——这正是 H3BattleStore「按钮贴条右缘」约定的同构位置。
- 常量（`WarehouseUiFlow.hpp`）：`kPackLogButtonWidth=72`（四个中文字，同整理按钮 18px/字）；`PackLogButtonX(panelWidth)=panelWidth-18-72` → 405 面板上 **x=315**；`kPagerNumbersRightLimit(panelWidth)=panelWidth-18-72-4`。
- **代价**：页码区从 [58,387) 329px 缩到 [58,311) 253px，`kPagerMaxButtons` **10→8**（8*28+7*4=252，起点贴 58）。全部数组/循环（`g_wh_ui_pagers_`、`pagerText`、创建与刷新循环）都以常量为界自动跟随。
- 按钮：**无 PCX 素材**，直接 `H3DlgCaptionButton::Create(..., 30053, "", GBK"打包日志", "smallfont.fnt", ...)`——同一键取出/放入的降级路径；中文小字体在本作中文版可用（原生状态条同源）。
- ID：面板局部 `kWhUiPackLogId_=30053` + 头文件 `warehouseui::kWhUiPackLogButtonId=30053`（**static_assert 互锁**防走偏）；进 `IsWarehouseControlId` 白名单（DOWN 被吞、`UsesGeometryFallback` 让位），但**不进** `ButtonIndexFromId` 五按钮数组（无 PCX 视觉对，不吃 round-19/20 的自维护按压管线）。
- 消息流：caption 按钮原生状态机在抬起时合成 0xD(CLICK)+itemId → `WarehouseUiHandle_` 的 CLICK 段新增 `id == kWhUiPackLogId_` 分支 → `WarehouseUiPackLogs_()`（与 §22.1 同构 + `outPath` 落日志）。收起层无此命中项（`AddPanelItem` 默认 HideDeactivate，展开统一 ShowActivate），故无需 expanded 判定。

### 22.3 坐标系与铠甲边界（没动的部分）

- 未改任何钩子入口：`WarehouseUiPackLogs_` 运行在既有 `Callback` 的 `__try(GUARD_WH_UI_POST_COMMON)` 内，原版 callback 仍在铠甲外恰好一次；函数体只放 POD 局部。
- `MessageBoxW` 从对话框回调里弹（H3BattleStore 生产同款模式）：泵消息期间对话框可能再收消息——`packing` 重入闸兜住；`WarehouseUiNeutralizeMessage_` 语义未动。
- GBK「打包日志」= `B4 F2 B0 FC C8 D5 D6 BE`（打=B4F2 包=B0FC 日=C8D5 志=D6BE，PowerShell 936 编码实测）。

### 22.4 验证

- `build_and_deploy.bat` 0 警告 0 错误；18 套单测全绿（`warehouse UI flow` 227→**230 checks**：新增 round-25 三断言——贴右几何、页码/按钮永重叠（`numbersEnd ≤ PackLogButtonX-4`）、30053 进白名单且 30054 不进）；round-12 断言同步 10→8（`CenteredPagerNumbersX(405,8,28,4)==58`）。
- **证伪**：临时把白名单条目改成 `id == kWhUiPackLogButtonId && id != kWhUiPackLogButtonId` → 恰好红 `round-25 pack-log button id joins the warehouse control whitelist`（1/230 failed）→ 还原 → 全绿。部署 DLL 与 `Release\H3Space.dll` 同哈希 `C76B31F8…`。
- 实机（用户执行）：展开随身空间层，点右下角「打包日志」→ 应弹「日志已打包」窗，且 `.7z` 路径已在剪贴板（可直接粘贴到聊天框）；连点不重复打包；分页行右侧 8 个页码仍可点。

## 23. 「打包日志」按钮迁到 F11 设置窗，并纠正 round-25 的不存在字体名（2026-10-15 round-26）

**用户裁定（原话）**：「这样:打包日志按钮别放到背包界面,放到F11界面里去(界面不够高就加高)」。
起因：用户报「随身空间 报错了,你看下日志」，日志里出现
`[Guard] WarehouseUiModal 异常 0xC0000005(访问冲突: 读取 0x00000006) addr=0x0324B063 HD_TC2.dll+0xB063`。

### 23.1 HD 字体模块（HD_TC2.dll）取证与崩溃机理

| 事实 | 证据 |
|------|------|
| `HD_TC2.dll` 是 HD 的**字体/文本**模块 | 144896 B、ImageBase 0x02000000、仅导出 `Start`/`_Start@0`(RVA 0x1000)；可打印串只有字体标签比较：`=SMAL`(字节 `3D 53 4D 41 4C` 即 `cmp eax,'SMAL'`)、`=TINY`、`=S_TI`、`=MEDF`、`=BIGF`、`=VERD`、`=CHAM`——即按**4 字符前缀**认字体 |
| 运行期基址 0x03240000（`HD_TC2.dll+0xB063` ⇒ VA 0x0324B063） | 崩溃行 + 模块基址反推 |
| 故障例程 RVA 0xB050：arg1=对象、arg2=文本/字体 id；`mov ecx,[eax]`→`call [ecx+2Ch]`(getter)→`call eax`(ecx=arg2) 取字体指针→`mov edx,eax` | dumpbin 反汇编切片（HD_TC2 标签 = ImageBase+RVA，如 `0200B063`） |
| `0200B063: movsx eax,byte ptr [edx+6]`：**edx==NULL 时读 0x6** ⇒ 正是 `读取 0x00000006` | 与异常操作数逐字吻合 |
| 取到 NULL 的原因：**字体名不存在** | 全盘取证：`H3bitmap.lod` 内只有 `smalfont.fnt`×1、`bigfont.fnt`×1；`_HD3_Data` 下只有 `smalfont.fnt`/`SMALFONT.FNT`/`bigfont.fnt`/`MedFont.fnt`/`tiny.fnt`/`verd10b.fnt`/`cham.fnt`；**全游戏目录无 `smallfont.fnt`** |

结论：round-25 的「打包日志」按钮写 `H3DlgCaptionButton::Create(..., "", GBK"打包日志", "smallfont.fnt", ...)`，字体名是**不存在的** `smallfont.fnt`（正确名 `smalfont.fnt`，H3API 常量 `NH3Dlg::Text::SMALL = 0x65F2F8`）→ 字体查表返回 NULL → HD 字体例程按空指针取 `[+6]` → `0xC0000005`。日志顺序吻合：崩溃点在「素材 ready」之后、「打包日志按钮 create=」（round-25 新增日志）与「状态条 create=」之前——即**第一条真正被执行的 caption 按钮**（前面几个 caption 按钮只在 PCX 素材缺失的降级路径才走）。

> 判定口径（可复用）：`GuardCrashFilter_` 日志里的钩子名 ⇔ 捕获异常的铠甲点，本例 `WarehouseUiModal` = attach 钩子（`WarehouseUiStageB.inc.cpp:77`）包住 `Attach(...)`，故异常发生在**面板创建过程中**；「素材 ready」是创建块最后一条成功日志，其后两条 create 日志缺失即圈定崩溃区间（创建块本身耗时 3.6s 的原因=64 槽 PCX/DEF + 12 页签 + 50 张贴图逐个从 LOD 取出）。round-25 的 21:17:44 构建（提交前工作区已含该改动）与 21:51 构建的两次日志同源同点，属**同一缺陷复现**，不是用户其他改动所致。

### 23.2 round-26 落点（F11 设置窗）

- 按钮移出背包分页行：删面板局部 `kWhUiPackLogId_` 与 `warehouseui::kWhUiPackLogButtonId`（30053 与 `static_assert` 互锁一并删）、`WarehouseUiPackLogs_`、CLICK 分支、创建块与 GBK 文案常量；`IsWarehouseControlId` 不再吞 30053。
- 页码几何回到 round-24 状态：`kPagerNumbersRightLimit(panelWidth)=panelWidth-18`（405→387），`kPagerMaxButtons` **8→10**（[58,387) 329px 放 10 个占 316px，`CenteredPagerNumbersX(405,10,28,4)==64`）；`kPackLogButtonWidth`/`PackLogButtonX` 删除。
- 设置窗（`HdSettingsUi.inc.cpp`）新增：`PackLogsFromSettings_()`（功能体与 round-25 同源，日志前缀改「设置窗触发」）+ `RunPackLogsFromSettings_()`（SEH 外壳，异常只等于“这次没打包”，日志 `真随机: 打包日志异常`）；控件 = `CreateLogSurface_` 画的深棕底 + 金边 PCX16（id `0x7E17`）+ 可点 GBK 文字（id `0x7E1E`，`smalfont.fnt`、色 5 / 中中对齐），两者都进 `OnLeftClick` 分派；下拉展开时被 `kSdLogShieldId_` 整窗接管层挡住。
- 几何进 `TextLayout.hpp` 纯常量 + 静态断言（`kSdWidth_=340`、`kSdPackLogX_=250`、`kSdPackLogW_=72`、`kSdPackLogH_=22`；右缘 18px、不压下拉框），对话框与单测共用；窗口高度**不需要加高**（原 340x190 足够，按钮与日志等级下拉框同行）。
- 同类缺陷一并纠正：`WarehouseUiPanel.inc.cpp` 三按钮降级路径的 `"smallfont.fnt"` → `"smalfont.fnt"`（该路径仅 PCX 素材缺失时执行，属潜在同源崩溃）。

### 23.3 验证

- `build.bat` 0 警告 0 错误；`run-unit-tests.bat` 18 套全绿（`warehouse UI flow` **231 checks**：round-25 三断言换成 round-26 四断言——30053 已出白名单且 30054 仍不进、30400 仍吞、页码区右界 387 与 10 个按钮、F11 按钮 18px 边距；round-12 断言同步 8→10、起点 58→64；页码槽位上限注释改 30400..30409）。
- `deploy.bat` 部署成功，部署 DLL 与 `Release\H3Space.dll` 同哈希 `C0557A260C77A7321EE0AD953DA55770BB86CF41582E1B3B90384D8DA877719C`（233472 B）。
- 产物字节取证（UTF-8 口径）：`smallfont.fnt` **0 次**、`smalfont.fnt` 1 次、`打包日志` 2 次、`设置窗触发` 2 次、`界面触发` 0 次、`打包日志按钮 create=` 0 次（面板创建块已删）、`状态条 create=` 1 次（保留）。
- 实机（用户执行）：①背包界面正常展开、日志不再出现 `WarehouseUiModal` 异常行，且应看到 `状态条 create=1`；②分页行右侧页码增至 10 个；③F11 设置窗「日志等级」行右端点「打包日志」→ 弹「日志已打包」且 `.7z` 已在剪贴板。

## 24. 打包日志改为「不限份数，只按文件名前缀」（2026-10-15 round-27）

**用户裁定（原话）**：「打包日志功能还要再调一下,当前是只取了最后5个日志文件,改成不限数量,只限文件名前缀」。

- `LogPackCollectRecent_(out, max_count)` → `LogPackCollectLogs_(LogPackEntry** out)`：收集**全部** `<基名>_*.log`
  （基名仍来自 `g_log_base` = DLL 名去扩展名，与日志器同源、与同目录其它插件前缀互斥；基名缺失才退回写死 `H3Space_`），
  按写入时间降序；内部数组按需 2 倍扩容（起始 16），**不设份数上限**，成功时把堆数组交给调用方 `delete[]`；
  无匹配 / 分配失败返回 0 且 `*out = nullptr`。
- 打包侧缓冲从固定 `BYTE* datas[6]` 改为按 `nItems = nLogs + 1`（多一份 `00_说明.txt`）堆分配：五个数组
  `datas/packs/pack_lens/unpack_sizes/crcs`，元素初始化为 null，`bail` 与成功路径统一 `delete[]`（元素数按 `nItems` 走）。
- `00_说明.txt` 文案改为「包含全部 %d 份日志（不限份数，按文件名前缀收集）」，份数取实际收集数。
- 实际份数仍由日志器自己的保留策略兜底（`ConfigLog.inc.cpp`：`MAX_LOG_FILES_TO_KEEP = 30`、扫描上限
  `MAX_LOG_FILES_TO_SCAN = 1024`），打包侧不再截断——所以"不限数量"不会无限膨胀。
- 单测：`LogPackTests` 53 → **60 断言**：`LogPackCollectLogs_: 只收自家、按时间降序`（改新 API + 断言返回指针非空）；
  新增 `LogPackCollectLogs_: 不限份数（12 份全收，旧的也在内）`（旧实现必然红：上限 5 时 `n == 5 ≠ 12`）；
  `PackRecentLogs_: 超过 5 份也全进包（不限份数）`（8 份逐个查 7z 明文头 UTF-16LE 名字流，旧实现只有 5 个名能命中）。
- 文档同步：`docs\骨架模块说明.md` §4（符号表 + 新增"份数策略"段）、`README.md` 日志与反馈、`使用说明.txt` 日志打包条目。
- 验收：`build.bat` 0 警告 0 错误；18 套单测全绿；`deploy.bat` 部署 DLL 与 `Release\H3Space.dll` 同哈希 `8B0AC8F4A7836FB029EA77C29075555F7170ED03D08F9CACCFE7938723F8370F`（233984 B）；
  产物字节取证（UTF-8 口径）：`最近五份完整日志` **0 次**、`包含全部 %d 份日志` 1 次、`不限份数` 1 次。


