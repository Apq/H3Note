# HD 设置界面（F12）与插件选项接入调研笔记

- 调研日期：2026-10-06
- 动机：为「全程真随机」等新插件选定设置入口——调研 HD Mod 的 F12 设置界面从哪里打开、第三方插件能否往它里面加选项。
- 方法：静态分析（HD_SODSrc 反编译 + ghidra_strings/imports + PE 立即数扫描）+ SoD_SP 插件（19 版）实物剖析。未开游戏（用户约定）。
- 结论速览：**F12 设置界面没有公开的第三方扩展接口，不建议也不需要碰它**；HD 生态的标准做法是 **SoD_SP 范式——插件自有 ini + 游戏内 H3 原生风格设置对话框**（SoD_SP、打铁助手等全部如此）。

## 1. F12 设置界面的打开点（静态排查，未定位到立即数）

排查手段与结果（均为负结果，本身即结论）：

| 排查项 | 结果 |
|---|---|
| HD_SOD.dll 搜 VK 0x7B（F12）键码比较 | 0 处（命中皆为控件 ID / scanf 格式符 / JSON 括号） |
| HD_SOD.dll 搜 H3 键码 88(0x58)（F12，H3API.hpp:4920）比较 | 0 处（唯一命中是 CRT `scanf` 的 'X'） |
| GetAsyncKeyState / GetKeyState 引用 | 仅滚动锁定(CapsLock 0x14)检测与键注入，无菜单触发 |
| CreateWindowEx / RegisterClass / DialogBox 静态导入 | HD_SOD.dll 无——不创建 Win32 窗口 |
| ShellExecuteA（9 处） | 无启动 exe 的迹象（HD_SOD.dll 内无任何 `.exe` 字符串） |

**推断（待验证）**：F12 热键是 ini 键驱动的运行时比较（比较变量而非立即数），或窗口由 HD_Launcher 常驻进程创建——`HD_Launcher.exe`（302KB，与「游戏设置器.exe」同尺寸）**导入表只有 KERNEL32.dll**（壳/桩特征，标准 GUI 导入被藏），且 `_HD3_Data\HD_Launcher.ini` 有 `<CloseAfterLaunch> = 0`（启动游戏后常驻）。若设置窗口在 Launcher 进程内，游戏进程里的 HD 插件（我们的 dll）**跨进程根本无权改它的 UI**——这本身就是「别往 F12 界面加选项」的硬理由。

运行时定位法（留待需要时用）：用户实机按 F12 前后用 Spy++/进程窗口枚举对比，确认窗口所属进程与类名。

## 2. HD 设置体系（已确认事实）

- **三层 ini**（`_HD3_Data\Settings\`）：`#common.ini`（公共）→ `#default#sod.ini`（各版本出厂默认，另有 #sw/#wog/#hota/#era）→ `sod.ini`（用户层）。当前启用的插件包列表就写在用户层 `sod.ini` 的 `<Packs> = "打铁助手", "SoD_SP插件19版", ...`。
- **读取函数** `FUN_010051a0("HD.xxx.yyy")`：HD_SOD.dll 内 1063 处调用，返回键值指针（`int*`）——HD 键值系统的统一入口。设置组用 `FUN_01008180("HD+.Settings")` 系列访问（14+ 处）。
- **插件包机制**：`_HD3_Data\Packs\<目录名>\` + 用户层 ini 的 `<Packs>` 列表启用。无导出表也能加载（SoD_SP.dll 导出表 RVA=0，DllMain/Patcher 自注册模式，与 H3RndNew 同机制）。
- HD 键值系统**没有**「第三方注册设置项到 HD 界面」的接口；`SoD_SP.Version` 这类键是 HD 侧合成的（用于检测 SOP 安装状态），不是 SOP 写入的。

## 3. SoD_SP 插件（19 版）实物剖析——HD 生态加选项的标准范式

目录：`_HD3_Data\Packs\SoD_SP插件19版\`

| 文件 | 作用 |
|---|---|
| `SoD_SP.dll`（425KB，无导出表） | 插件本体，Ghidra 工程已建（`SoD_SP.dll_ghidra\`，db 已有 12.8MB×2 内容） |
| `SoD_SP.ini`（47KB） | 43 个选项键（`[options]` 节），每个键配英/俄/德/希腊/波兰/法六语注释 |
| `SoD_SP.lod`（169KB） | 资源包（界面图形等） |
| `Lang\chs.json` 等 6 语言 | 界面文案：选项 text/description、对话框标题与按钮提示 |
| `H3.CombatAnimation/TextColor/LodTable.dll` | 附带的 H3Plugins 官方示例插件（对应 D:\GitHub\H3\H3Plugins 仓库） |

**SOP 的设置 UI 是完全自建的**（chs.json `sod_sp.dialog` 节）：
- 标题「SoD_SP选项」、描述栏、确认/保存按钮文案、`保存到 SoD_SP.ini` 确认弹窗、保存失败警告——游戏内 H3 原生风格对话框（标题栏装饰文案直接用 H3 颜色标记语法 `{~Gold}`）。
- 支持**地图作者锁定选项**（`disabled_option_text = "This option has been locked by the mapmaker"`）——选项可被地图设置强制，思路可借鉴。
- 对话框打开入口未定位（dll 内 0x7B×3 / 88×22 处比较无法区分键码与普通数值，列为待验证）。

**生态级证据**：SOP 是体量最大的第三方 HD 插件（425KB、43 选项），它都没有往 HD 的 F12 界面里塞选项，而是自建对话框+自有 ini——第三方在 HD 生态里加设置的正确路径就是这条路。我们 H3RndNew 的「开局真随机」选图框勾选（H3DlgItem + AddItem + 逐消息补画）已是同范式的最小实现。

## 4. 重大副产物：HD+ 会替换 RNG，SoD_SP 有「真随机数」选项（已同步进全程真随机笔记）

- chs.json 选项 `restore_original_random_number_generator`，中文名**「真随机数」**：「当启用此选项时，游戏将采用真随机数，即使使用 HD+ 模式。当禁用此选项时，游戏为伪随机数」↔ ini 键 **`OriginalRNG = 1`（用户当前已启用）**。
- 语义：**HD+ 模式会把 `0x61842C`/`0x50C7C0` 替换为自己的 RNG（社区视角的「伪随机」），SOP 的该选项恢复原版 LCG（社区称「真随机」）**。注意与我们的 CSPRNG「真随机」是两码事——**新插件命名必须避开「真随机数」字样冲突**（例如叫「CSPRNG 全程随机」或「系统级随机」），否则玩家会把两者混为一谈。
- SoD_SP.dll 二进制含 `push 0x61842c`×3（文件偏移 0x99EB/0xC8E9/0xF850）、`push 0x50c7c0`×4（0x95FB/0xC8FE/0x389BD/0x38A2B）——对两个 RNG 入口的补丁注册代码，实物坐实。
- **HD↔SoD_SP 运行时补丁协调协议**（HD_SODSrc 行 15512-15561）：HD 用模块管理器单例 `DAT_0114f964`（`+4` 虚方法按名查模块 "SoD_SP"）拿插件对象；读键 `SoD_SP.Version`；旧版 SOP（<0x122a00）时对 `0x4ac2d6/0x4abba9/0x4ad160/0x61842c/0x50c7c0` 逐一调插件对象 `+0x5c`(addr) 查补丁条目，`+0xc` 返回 1 时调 `+0x1c` 禁用之——**HD 与插件对同一地址的多重 hook 有运行时仲裁机制**。全程真随机插件的 hook 共存问题（与 HD+、与 SOP OriginalRNG）见《全程真随机调研笔记.md》第 4 节。

## 5. 结论：新插件的设置入口怎么做（2026-10-06 用户实锤后改写）

**用户实锤：游戏内按 F12 弹出的窗口标题就是「SoD_SP选项」——这台机器上的「F12 设置界面」根本不是 HD 官方设置窗口，而是 SoD_SP 插件自建的对话框**（chs.json `sod_sp.dialog.dialog_title`）。谜团随之解开：
- HD_SOD.dll 里搜不到 F12 处理 ✓（不是它处理的）
- HD_Launcher.exe 常驻、导入折叠 ✓（它是释放/注入器，不画设置窗口）
- F12 热键由 **SoD_SP.dll** 响应（二进制内 3 处 VK 0x7B 比较命中），弹出自己的 H3 原生风格对话框

### 5.1 「挤进 SoD_SP 的 F12 对话框」——不可行/不值得
- SoD_SP 是**闭源第三方 dll**（425KB），无插件间接口、无选项注册协议；它的选项表（43 项 ini+json 文案）是编译期固定结构。
- 硬要做只能 hook SoD_SP.dll 内部的对话框构建函数再 AddItem——跨插件 hook 闭源代码，SOP 每升一版（现已 19 版）地址全变、即刻返工；且与它的 ini/lang 体系冲突。放弃。

### 5.2 正确路线：抄 SoD_SP 的模式，自己做一个「随时可开」的设置窗（完全满足需求）
SOP 能用 F12 随时弹自己的设置窗，**我们的插件同样可以**——这就是该生态的标准玩法：
1. **全局热键**：hook 键盘消息链检测热键（避开已被 SOP 占用的 F12；可选 F11/F10/自定义键，ini 可配）。落点参考：H3Msg 键处理（`H3Manager::ProcessMessage`，H3API.hpp:30647；`H3Msg::GetKey/eVKey`）或 H3Auto 已验证的键盘钩子先例。战斗中/对话框中/冒险地图均可触发（SOP 的 F12 就是证明，全程可用）。
2. **自建设置对话框**：H3 原生风格（H3BaseDlg/H3DlgItem/AddItem 全套经验已在开局真随机验证；多选项时加分类+描述栏，参考 chs.json 的 text/description 结构）。
3. **持久化**：插件自有 ini（`[General]` 开关），改完即存，下次启动生效。
4. 对「全程真随机」项目：三态（关/仅开局/全程）就放进这个随时可开的设置窗；开局窗口勾选可保留（或统一收进设置窗，二选一）。

### 5.3 为什么这条路成立（三层证据）
- SOP 本体即先例：第三方插件、全局热键、自有对话框、自有 ini——全链路无 HD 官方接口参与；
- H3Auto 先例：热键面板（打铁助手 J 键/面板）在同一台机器上长期运行验证；
- 开局真随机先例：H3DlgItem/AddItem/绘制链在同环境验证通过。

## 6. 实施记录：H3RndNew 0.2.2026.1006 设置窗落地（2026-10-06）

§5.2 路线已在 H3RndNew 实现并通过编译（0 警告 0 错误），热键 F11 + 设置窗（全局真随机/热键修改）。实施中把热键落点从「候选」变成确认事实，全部静态反编译证据：

### 6.1 键盘消息链（全局热键的正确落点）

- **窗口过程 `0x4F8290`**（`FUN_004f8290`，869 字节）：`RegisterClassA` 的 `lpfnWndProc`（Heroes3Src `blk_4f0000.c` 行 2184）。消息分派：`<0x13` 窗口管理；`0x100<=msg<0x102` → **键盘入口 `0x4EC1C0`**；`0x200..0x206` → 鼠标入口 `0x4EC370`；`0x111` → 菜单 `0x4F86F0`；其余 DefWindowProc。
- **键盘入口 `0x4EC1C0`**（`FUN_004ec1c0`，427 字节，`bool __fastcall(hwnd@ECX, msg@EDX, wparam@栈, lparam@栈)`）：
  - 入口守卫：`DAT_00699530`（输入管理器）非空且 `+0x34 == 1`，否则原样返回 true（放行）。
  - 把按键写进输入管理器环形槽（`DAT_00699530 + 0x83c` 为写指针，每槽 0x20 字节）：`[0]=1/2`（WM_KEYDOWN/UP）、`[1] = lparam>>16 & 0xFF`（**扫描码 set 1**）、`[3] = GetKeyState(Ctrl/Alt/Shift)` 组合位。
  - **扫描码 set 1 = H3 内部键码**（`eVKey` 全表吻合：F1=0x3B=59、Enter=28、A=30、F11=0x57=87、F12=0x58=88）——`H3Msg::KeyPressed()`（读 `subtype` 字段）返回的就是它。插件配热键时直接存扫描码即可，无需 VK 转换。
  - **原版先例**：该函数内 `piVar1[1]==0x3B`（F1）→ `FUN_004f86f0(0x9c74,...)`、`==0x3E`（F4）→ `FUN_004f86f0(0x9c49,...)`——**在键盘入口直接打开界面**是原版自己的模式，hook 此处弹 H3 模态对话框与原生行为同源。
  - 返回值：生成了消息返回 false(0)=已处理（WndProc 即返 0），否则 true 继续走 DefWindowProc。吞键 = 返回 0。
  - 自动重复过滤：`lparam & 0x40000000`（bit 30）为 1 表示按住重复。
- **SOP 的 F12**：`SoD_SP.dll` 二进制 3 处 0x7B 比较中 `0x10002B42` 一处是真响应逻辑（`cmp eax,0x7B; jne` 后调原版 `0x4317D0`），另两处（`0x100148D2`/`0x10014AE9`）是 VK 0x7B 与 H3 码 88 并存的转换/热键表处理——它 hook 的具体原版函数未再深挖（§6 待验证 2 保留），我们已用 0x4EC1C0 独立达标。

### 6.2 自建 H3 原生对话框（H3API 官方支持的继承路线）

- `struct X : h3::H3Dlg` 直接继承，override `OnCreate()`（建控件）/`OnLeftClick(itemId, msg)`（点击分发）；`dlg.Start()` 模态运行（内部 `OnCreate` → `vShowAndRun(FALSE)`，退出自动恢复鼠标光标）；`Stop()` 请求关闭。栈对象即可（析构销毁 items+背景+vDestroy）。
- 构造 `H3Dlg(w,h)`（x/y=-1 自动居中，makeBackground=TRUE 自动木纹底+边框）。
- 控件：`H3DlgDef::Create(x,y,w,h,id,def,frame,...)`（勾选框 ChkBlue.def 帧 0/1）、`H3DlgText::Create(x,y,w,h,text,font,color,id,align,bk)`（SetText 改文字）、`H3DlgTransparentItem::Create(x,y,w,h,id)`（透明点击区）、`H3DlgDefButton::Create(x,y,id,def,frame,clickFrame,closeDialog,hotkey)`（官方用法见 H3API.hpp:28527：`("iokay.def",0,1,TRUE,NH3VKey::H3VK_ENTER)`，closeDialog=TRUE 点击自动关窗）。
- 热键侦听放键盘 hook 层（不是窗的 OnKeyPress）：hook 里侦听态吞掉一切 WM_KEYDOWN（ESC 取消/修饰键跳过/其余即新键），从同线程直接调窗对象的刷新方法更新键名文字——避开「OnKeyPress 依赖消息到达而消息已被吞」的循环依赖。
- 防重入：`InterlockedCompareExchange` 弹窗闸 + 窗开着时热键本身吞掉；SEH 兜底与 C++ 对象展开分函数（同函数会 C2712）。

### 6.3 中文文案

源码 UTF-8 + 运行时 `MultiByteToWideChar(CP_UTF8)` → `WideCharToMultiByte(936)` 转 GBK 再交给游戏（开局模块手写 GBK 字节表的自动化替代，smalfont.fnt 渲染 GBK 中文已验证）。

## 7. 待验证清单（更新）

1. ~~F12 设置窗口归属~~ ✅ 已实锤：SoD_SP 插件的对话框（标题「SoD_SP选项」）。
2. SoD_SP 的 F12 hook 具体挂点（0x10002B42 所在函数的 hook 目标）——已被 0x4EC1C0 路线替代，仅在研究 SOP 共存时再看。
3. HD 官方设置窗口（HD.exe 启动器里的那个）与本机 F12 行为无关，不再追。
4. HD+ 替换 RNG 的具体形态——影响全程真随机 hook 的共存顺序，四种组合（HD±、OriginalRNG±）实机验证。
5. ~~新插件热键选型~~ → 已定 F11（eVKey 87），设置窗内可改；F11 是否与本机其它整合插件冲突待用户实机反馈（SOP 占 F12 已确认）。
6. 设置窗在选图界面等 H3 自带模态对话框上的嵌套表现——第一版未放宽守卫，待实测。
7. 弹窗守卫用的 `DAT_00699530+0x34==1` 在启动早期/切图过场的值——若实测有场景弹不出，再研究该标志的全 0/1 生命周期。

### 6.4 动态 H3DlgText 的绘制坑（2026-10-06 用户实测后确认）

- `H3DlgText::SetText()` 只更新文字对象；`Draw()` 调 vtable 的 `vDrawToWindow()` 写绘制缓冲；`Refresh()` 只是调用父窗 `Redraw(x,y,w,h)` 将区域刷新。对同一动态文字控件连续 `SetText→Draw→Refresh`，不会自动擦掉旧字符串像素，所以「F11」切换为「请按新键…」会重叠。
- 设置窗标题、说明文字由 `H3Dlg` 框架正常绘制，关闭时不残留；动态键名是运行期间手工 `Draw+Refresh`，绕过了这条静态 item 重绘路径，关闭后可能留下残影。
- 修复模式：动态文字更新前先 `Hide()` 旧文字；使用同一位置的 `Box66x32.pcx` 框控件重新 `Draw+Refresh` 恢复底色；再 `SetText→ShowActivate→Draw→Refresh` 绘制新文字。窗口的 `OnOK/OnCancel/OnClose` 关闭路径先执行同样的清理。这个顺序是用户实测反馈驱动的确认机制，不是推测。
