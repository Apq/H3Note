# SaveLoadEnhance 逆向笔记（Heroes3_2026.05.01 / HD Mod）

> 用 radare2 静态反汇编 `D:\Heroes3\Heroes3_2026.05.01\Heroes3.exe`（baddr=0x400000）确认。
> radare2 路径：`D:\Programs\radare2-6.1.6-w64\bin\radare2.exe`；全分析 `aaa` 约耗时 25 秒。
> 本文只记录**已反汇编+实测验证**的事实。

## 一、界面区分

游戏用同一个对话框类构造存档/读档/新游戏三种界面，由构造参数 `arg_8h` 决定模式：

| arg_8h | [+0x64] | [+0x65] | 界面 |
|--------|---------|---------|------|
| 1 | 1 | 0 | 读档 |
| 2 | 0 | 1 | 存档 |
| 0 | 0 | 0 | 新游戏选图 |

运行时判据（`self` = 对话框对象）：
- `[self+0x64] == 1` → 读档
- `[self+0x65] == 1` → 存档
- 两者都为 0 → 新游戏

模式设置在构造函数 `0x579CE0` 内（0x579F84–0x579F96）。

## 二、关键函数

| 地址 | 函数 | 说明 | Hook |
|------|------|------|------|
| 0x4BEB60 | H3Main::SaveGame | `__thiscall(this, name, 1,1,1,0)`；存档总入口，**6 个参数** | HiHook SPLICE_ THISCALL_ |
| 0x579CE0 | 构造函数 | 对话框构造/初始化（size 11619）；仅在窗口**创建**时调用 | — |
| 0x584EC0 | 显示/消息循环入口 | `fcn.00584EC0`：对话框显示+消息循环；**每次显示**都调用（新建或复用） | — |
| 0x584EF4 | 消息循环前点 | `fcn.00584EC0` 内部，`call 0x602D60` 之前 | **LoHook**（函数内部） |
| 0x583E10 | 析构函数 | `fcn.00583E10`（size 893）；所有关闭路径汇聚于此 | HiHook SPLICE_ THISCALL_ |
| 0x5857D0 | UpdateForSelectedScenario | `__thiscall(this, index, redraw)`；应用选中项+刷新滚动/预览 | — |
| 0x584820 | Redraw | `__thiscall(this)`；整窗重绘 | — |
| 0x602D60 | 消息循环 | DoDialog；被 0x584EC0 调用，阻塞到用户确认/取消 | — |

## 三、对话框显示函数 fcn.00584EC0

这是最核心的发现。此函数在每次对话框显示时调用，无论窗口是新建还是复用（连续存档场景）。

```asm
0x584ec0  push esi
0x584ec1  mov esi, ecx            ; esi = this（对话框对象）
0x584ec3  mov al, [esi+0x64]      ; 读档模式？
0x584ec6  test al, al
0x584ec8  jne 0x584ed5
0x584eca  mov cl, [esi+0x65]      ; 存档模式？
0x584ecd  test cl, cl
0x584ecf  je 0x584ee7             ; 新游戏
...
0x584ef4  mov ecx, [0x6992d0]    ; 游戏状态对象
0x584efa  push 0
0x584efc  push 0x58e5a0           ; 对话框回调
0x584f01  push 0x5ffac0           ; 帧缓冲
0x584f06  push esi                ; this
0x584f07  call fcn.00602d60       ; 消息循环（阻塞）
0x584f0c  pop esi
0x584f0d  ret 4
```

**Hook 点 0x584EF4**（消息循环前）：ESI = 对话框对象，用于自动选中。

**0x584EF4 保持 LoHook**：此地址在函数 0x584EC0 内部（非函数边界），HiHook 无法替代。但该地址是干净指令边界（`mov ecx, [0x6992D0]`，绝对寻址），LoHook 在此稳定可靠。

**0x584F0C 不可 hook**：仅 4 字节（5e c2 04 00），LoHook 会覆写下一个函数入口，导致崩溃。

6 个调用者（与构造函数 0x579CE0 一一对应）：
`0x41817b`（存档）、`0x4ef05b`（读档）、`0x4ef0be`（新游戏）、`0x4ef183`（第三模式）、`0x4f0b6a`、`0x4f0cde`

## 四、对话框生命周期

```
0x4ef04c  call fcn.00579ce0     ; 构造对话框
0x4ef05b  call fcn.00584ec0     ; 显示+消息循环（阻塞）
          ↳ 0x584EF4: 消息循环开始前（ESI=对话框对象）
          ↳ 0x584F07: call fcn.00602d60（消息循环阻塞）
0x4ef060  ...                   ; fcn.00584EC0 已返回
0x4ef0xx  call fcn.00583e10     ; 析构（释放显示数组等内部资源）
```

关键时序：
- **0x584EF4**：消息循环前，原生初始化已完成，可安全修改选中项
- **0x583E10**（析构入口）：ECX = 对话框对象，显示数组**仍然有效**，可安全读取选中文件名
- **0x4EF5C4**（EnterGame66）：析构已完成，对话框数据**已不可用**

## 五、对话框对象字段

| 偏移 | H3API 名 | 说明 |
|------|----------|------|
| +0x64 | — | 读档模式标志（1=读档） |
| +0x65 | — | 存档模式标志（1=存档） |
| +0x370 | mapListNumberTop | 列表顶部索引 |
| +0x374 | selectedMapIndex | 当前选中索引（索引 +0x1054 显示数组，非 +0x1034） |
| +0x1054 | — | 显示数组起始指针（begin） |
| +0x1058 | — | 显示数组结束指针（end） |
| +0x183C | — | 滚动条对象指针 |

显示数组单项步长 `0xCA4`，文件名偏移 `0x33D`。
可见行数：读档 18 行，存档 16 行。

滚动条对象字段：+0x3C = tick 值，+0x48 = tick 总数。vtable +0x38 = SetTick 函数。

## 六、手动/自动存档区分

当前稳定方案：**只在 `SaveGame` 真正发生时记录手动存档**。

游戏保存顺序可能是「先关闭存档对话框（析构）→ 再调用 `SaveGame`」，因此 `g_save_dialog_visible` 在 `SaveGame` 到达时可能已经被清掉。解决方式是：

- `HH_DialogDestructor` 对 `DK_SAVE` 不记录文件名，只设置 `g_save_dialog_recently_closed` 和短有效期。
- `HH_SaveGame` 在“存档界面仍可见”或“存档窗口刚关闭后的短窗口期”内收到调用，才记录 `save_path` 文件名。
- `DK_LOAD` 不在析构时记录；取消/关闭读档窗口不能污染最后记录。

这样能避免旧方案“打开存档窗口后取消/关闭也会更新记录”的误判。

**已废弃方案**（不要再用）：
- ~~按返回地址 `[esp]` 区分手动/自动~~：不稳定，HD Mod 包装层导致返回地址变化。
- ~~`IsLikelyAutoSaveName()` 文件名启发式~~：无法可靠区分。
- ~~`MANUAL_SAVE_RETURN_ADDRS` 白名单~~：析构先于 SaveGame 的时序使其无效。
- ~~析构时直接记录 `DK_SAVE` / `DK_LOAD` 当前选中项~~：取消/关闭窗口也会污染记录。

## 七、全局变量

| 地址 | 含义 |
|------|------|
| 0x6992D0 | 游戏状态对象；+0x38 = 当前菜单命令（0x65=NEW_GAME、0x66=LOAD_GAME） |
| 0x699538 | 全局对象；+0x1f843 = 回合时长 |
| 0x69FC88 | 存档名输入缓冲（构造存档界面时清空） |

**注意**：`0x699430` 在读档成功时被写入，但实测存放的是**场景地图名**（如 `Chaos.mp2`），不是存档文件名（如 `314_992.GM1`）。不可作为读档记录来源。

## 八、Hook 类型选择与 HiHook 改造

### 改造背景

初始版本 3 个 Hook 全部使用 LoHook。后按「函数边界用 HiHook、函数内部用 LoHook」原则进行改造。

### 改造结果

| Hook | 地址 | 原类型 | 现类型 | 改造理由 |
|------|------|--------|--------|----------|
| HH_SaveGame | 0x4BEB60 | LoHook | HiHook SPLICE_ THISCALL_ | 函数边界，thiscall，安全可行 |
| HH_DialogDestructor | 0x583E10 | LoHook | HiHook SPLICE_ THISCALL_ | 函数边界，thiscall，安全可行 |
| Hook_DialogShow | 0x584EF4 | LoHook | LoHook（不变） | 函数内部点，HiHook 无法替代 |

### SaveGame HiHook 细节

原 LoHook 通过 `c->esp` 读取返回地址和 save_path 参数。改 HiHook 后：

- 签名：`__stdcall HH_SaveGame(HiHook* h, DWORD thisPtr, const char* save_path, DWORD a3, DWORD a4, DWORD a5, DWORD a6)`
- **必须传递全部 6 个参数**（this + save_path + 4 个固定值），否则栈错位导致崩溃
- 调用原函数：`CALL_6(void, __thiscall, h->GetDefaultFunc(), thisPtr, save_path, a3, a4, a5, a6)`
- 手动/自动存档区分：通过 `g_save_dialog_visible` 标志（DialogShow 时设置，析构时清除）
- 来源：H3API 确认 `THISCALL_6(VOID, 0x4BEB60, this, save_name, 1, 1, 1, 0)`

### DialogDestructor HiHook 细节

原 LoHook 通过 `c->ecx` 读取 this 指针。改 HiHook 后：

- 签名：`__stdcall HH_DialogDestructor(HiHook* h, char* self, int delete_flag)`
- **必须传递隐藏的 `delete_flag` 参数**（MSVC C++ 析构函数的隐藏参数：0=仅析构，1=析构+delete），否则栈清理量不匹配导致崩溃
- this 指针直接作为参数传入
- 先读取数据（析构会释放内部资源），再 `CALL_2(void, __thiscall, h->GetDefaultFunc(), self, delete_flag)` 调用原函数

### DialogShow 不能改 HiHook 的原因

0x584EF4 在函数 0x584EC0 内部（偏移 +0x34）。HiHook 只能包裹函数入口，而我们需要在「默认选中设置之后、消息循环之前」插入逻辑：

- 在 CALL 原函数**之前**执行 → 太早（默认选中还没设置）
- 在 CALL 原函数**之后**执行 → 太晚（消息循环已结束，对话框已关闭）

函数 0x584EC0 非常短（~0x4E 字节），核心就是「设置滚动条 + 调用消息循环」，没有合适的子函数可以单独 hook。

### LoHook 在函数内部使用的安全性条件

1. **指令边界干净**：patch 区域必须是完整指令的起点（0x584EF4 = `mov ecx, [0x6992D0]` 的完整起点）
2. **不使用相对寻址**：指令不能含短跳转、相对 call 等相对地址（0x584EF4 使用绝对地址 `[0x6992D0]`）
3. **无外部跳入**：其他线程/代码不会跳进 patch 区域中间（对话框函数，单线程 UI 路径）

### hook 地址与游戏版本的关系

三个 hook 地址来自游戏 EXE（`Heroes3.exe`），与 HD Mod 版本无关。只要游戏 EXE 不变地址就有效；更换游戏 EXE（不同汉化版、ERA 平台等）需重新核对地址。HD Mod Patcher API（`WriteLoHook`/`WriteHiHook`）向后兼容。

### hook 地址（原版）与运行环境（HD Mod）的关系

两者是不同层面：

- **Hook 目标地址**：来自原版 `Heroes3.exe` 的函数，不是 HD Mod 注入的代码
- **DLL 加载与 hook 安装机制**：依赖 HD Mod 框架（`GetPatcher()`、`CreateInstance()`、`WriteHiHook()`、`WriteLoHook()` 都是 HD Mod 提供的 API）

没有 HD Mod，DLL 不会被加载，也没有 Patcher 框架安装 hook。所以插件运行需要 HD Mod 环境，但 hook 的地址本身与 HD Mod 版本无关。

## 九、存档界面输入框注意事项

存档界面有文本输入框控件。在消息循环开始前（0x584EF4）调用以下函数会破坏输入框初始化：

- `UpdateForSelectedScenario`（0x5857D0）：会把文件名写入输入框缓冲，控件未就绪时导致乱码/叠加
- `Redraw`（0x584820）：会干扰输入框控件的创建流程

解决：存档界面只设置 `selected`（+0x374）和 `topIndex`（+0x370）到内存字段，跳过上述两个函数调用。原生消息循环启动后会根据 selected 索引自行处理。

## 十、radare2 常用命令

```
r2 -q -e scr.color=0 "D:\Heroes3\Heroes3_2026.05.01\Heroes3.exe"
aaa                  # 全分析（~25s）
afi @ <addr>         # 函数信息
axt @ <func>         # 谁调用了这个函数
pdf @ <addr>         # 反汇编整个函数
pd N @ <addr>        # 从 addr 反汇编 N 条
```
