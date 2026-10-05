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

## 5. 结论：新插件的设置入口怎么做

1. **不碰 HD 的 F12 界面**：无公开接口；UI 可能在另一进程/壳内；改 HD 本体升级即丢。SOP（生态最大插件）也这么做——这是社区共识路径。
2. **推荐 SOP 范式**（全部积件我们已有）：
   - 配置：插件自有 `<名字>.ini`（`[General]` 开关；如需出厂默认+用户层，沿用 H3Auto 的 default/user 两层模式）；
   - UI：游戏内 H3 原生对话框（H3DlgItem/AddItem/CreateDialog 已验证）；选项多时做分类+描述栏（参考 chs.json 的 text/description 结构）；
   - 文案：中文直接内嵌即可（SOP 用 json 多语言是因为面向国际发布）；
   - 可借鉴 SOP 的「地图作者锁定」思路（若将来需要服务器/地图级强制）。
3. 对「全程真随机」项目：设置入口建议**扩展现有开局窗口勾选为三态**（关/仅开局/全程，见全程真随机笔记 §6），而不是新做设置页——与现有交互一致且零新增 UI 风险。

## 6. 待验证清单

1. F12 设置窗口所属进程与窗口类（Spy++ 实机枚举；判断是否 Launcher 进程）。
2. SoD_SP 设置对话框的打开入口（菜单按钮/热键）。
3. HD_SOD.dll 的 F12 热键键名（若在键值系统中，应能从运行时 Settings ini 或内存 dump 里找到 `HD.xxx` 键）。
4. HD+ 替换 RNG 的具体形态（替换函数体还是种子快照）——影响全程真随机 hook 的共存顺序，四种组合（HD±、OriginalRNG±）实机验证。
