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

- `H3DlgText::SetText()` 只更新文字对象；`Draw()` 调 vtable 的 `vDrawToWindow()` 写绘制缓冲；`Refresh()` 只是把矩形从缓冲 blit 上屏。对动态文字控件连续 `SetText→Draw→Refresh`，不会自动擦掉旧字符串像素——旧「F11」与新「请按新键…」像素叠加，且这些直写像素在对话框关闭后留在屏幕上（残留的是开窗时画的那一版，改键后也不更新）。
- **根因（关键时序）：`H3Dlg::Start()` 先执行 `OnCreate()`，之后才 `vShowAndRun` → `vShow` 保存底层画面。** 在 `OnCreate()` 里对动态控件调 `Draw()/Refresh()`，等于把动态文字画进“关闭时要恢复的背景快照”里——关闭时这层含 F11 的旧画面被整块贴回屏幕，这就是“关窗后残留、且残留的永远是 F11 而不是新键”的直接原因。
- 关窗后手工调 `H3WindowManager::H3Redraw(dlg 矩形)` **不能修这个问题**：`vShow`（0x5FF0A0）里保存的旧画面在窗口生命周期内一直是恢复源，运行期把新像素刷上去也会被后续背景恢复路径盖掉；必须从源头禁止动态控件绕过框架绘制。
- 正确模式（实测修正后的方案）：
  1. 动态文字用**原生自绘控件**（如 `H3DlgTextPcx`，文字+背景框一体），文字作为控件状态交给框架；
  2. `OnCreate()` 里只 `SetText`（或构造参数）设置初始文字，**绝不调用 `Draw/Refresh`**；
  3. 运行期更新只做 `SetText` + `H3Dlg::Redraw()`（`vRedraw(TRUE,-65535,65535)` 按 AddItem 顺序整窗重画并刷新），不做控件级直写；
  4. 关窗后**不要**再手工 `H3Redraw` 对话框矩形，恢复背景交给 `vShow/vHide` 的保存-恢复链。
- 参考时序：`H3Dlg::Start()`（H3API.hpp 内联）：`OnCreate()` → `vShowAndRun(FALSE)`（0x5FFA20 模态循环）；`vShow`（0x5FF0A0）在显示前保存底层画面。

### 6.5 下拉浮层底板、资源归属与点击命中（2026-10-06 静态确认）

目标为工作区 Heroes3Src 对应的 SoD `Heroes3.exe`，镜像基址 `0x400000`；参考构建使用 `H3API/single_header/H3API.hpp`。以下为静态结论，不表示游戏内外观已验证。

- `H3DlgText` 的 `+0x48` 是 `bkColor`。构造 `0x5BC6A0` 写入最后的背景色参数；绘制 `0x5BCA10` 在该字段非零时，以全局调色板索引取得 16 位颜色并填矩形，随后画文字。因此 `bkColor=0` 的选项文字本身是透明的。原生界面存在 `0x20` 用例，但本次未验证该调色板索引的实际颜色，不应称其为黑色或深棕色。依据：`Heroes3Src/src/decompiled/all_functions.c` 的上述地址函数；H3API `H3DlgText::Create`。
- 可使用独立 `H3LoadedPcx16::Create` 缓冲明确指定 RGB，`FillRectangle`、`DrawFrame` 填充底板，再以 `H3DlgPcx16::Create(..., nullptr)` + `SetPcx` + `AddItem` 纳入原生绘制链。框架 `H3Dlg::AddBackground` 也采用该组合。不要把短暂展开列表画进整窗持久背景，否则收起时重画仍会留下列表像素。
- `H3DlgPcx16` 在 `+0x30` 保存缓冲指针。构造 `0x450340` 在资源名为空时置零；析构 `0x450400` 对非空 `+0x30` 调资源虚表 `+4`。因此成功交给 PCX 控件后，不再自行释放缓冲；控件分配失败则由调用者 `Destroy()` 回收。依据：`all_functions.c` 的 `0x450340/0x450400`。
- 命中函数 `0x5FF9A0` 先从鼠标屏幕坐标减去对话框 `+0x18/+0x1C`，然后从控件数组末尾向前搜索（后加入者优先），检查 ACTIVE 与隐藏/禁用标志。因此浮层要后加入；坐标选择行时使用 `msg.GetX()-GetX()` 和 `msg.GetY()-GetY()`。
- H3RndNew 此版使用独立 PCX 底板和 H3Auto 帮助界面的棕底/金框 RGB 数值，箭头为 7×4 像素三角，列表当前项有不同底色与边界。展开时隐藏停用第二行与确定按钮，透明文字控件接管空白点击，收起后整窗 `Redraw`。布局为日志等级 y=44，复选框与热键并排 y=84，保持 340×190。
- 待实机验证：箭头展开/收起切换、底板不透字、五项点击映射、点外部只收起而不误触、收起恢复第二行、热键改绑和关窗无残留。构建与部署成功不等于这些运行时行为已验证。

### 6.6 下沉边缘残留与列表边缘对齐（2026-10-06 用户反馈 + 静态核对）

- 用户实机反馈：展开列表比收起框左右各宽出边框，第二行文字隐藏后仍能看到热键框下沉边缘。源码核对：前者由底板 x−2 / width+4 引起，改为与收起框同 x/width，行边界绘制在底板内部；后者来自对整窗 `GetBackgroundPcx()->SinkArea(...)` 的持久修改，控件隐藏并不清除背景内容。
- H3API `H3LoadedPcx16::SinkArea` 在指定矩形的上/左边暗化、下/右边亮化，直接修改调用对象像素，不是独立控件（见 `H3API/single_header/H3API.hpp:21701`）。因此下沉边缘若需要动态隐藏，必须随独立图层一起管理。
- 修正方案：热键框的 70×30 木纹区域复制到单独 PCX，仅对副本 `SinkArea(0,0,70,30)`，以 `H3DlgPcx16` 加在键名文字之前；隐藏第二行时也隐藏底板。整窗背景保持未刻凹槽的木纹，整窗重绘后恢复平面。
- `CopyRegion(source,x,y)` 中 x/y 是源图起点，复制大小受目标 PCX 宽高限制；目标起点为 (0,0)，源/目标各按自己的 scanline 步进。静态依据：SoD `0x44E0C0`（`Heroes3Src/src/decompiled/all_functions.c:59093`），以及 H3API `CopyRegion` 包装。此处源 (238,80)、目标 70×30 均在 340×190 背景范围内。
- 这次修正后的展开/收起外观待用户实机验证，保留热键输入框原坐标与尺寸。
