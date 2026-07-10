# H3Auto 战场自动化调查

> 调查时间：2026-07-10
> 目的：为 H3Auto 设计文档中的待确认项提供答案

---

## 1. "自动战斗"按钮

### 位置推测

在战斗画面底部面板（H3CombatBottomPanel）上。根据 H3BattleValueInfo 的经验，该面板的按钮通过 `_DlgStdButton_` 创建。

### 调查方向

```cpp
// 可能的 DEF 资源名
"AutoFight", "AUTOCBT", "auto", "auto_fight", "adventure"

    // 可能的控件 ID（通过右键拦截 Hook @ 0x41B120 获取）
    // 需要在游戏中实际触发右键后，从 H3API 日志中确认 ID
```

### 待做

- [ ] 在战斗画面右键点击，找到"自动战斗"按钮的实际控件 ID
- [ ] 用 IDA/radare2 搜索 `_DlgStdButton_` 创建语句，确认 DEF 资源名
- [ ] 或直接 Hook 0x41B120，在右键消息中打印控件 ID

---

## 2. 插件如何向战斗系统提交动作

### 战斗流程（推测）

```
1. 玩家选择目标（点击生物/空地）
2. 游戏将选中的 stack + 目标位置写入某个结构
3. 战斗循环检测到行动完成，执行移动/攻击动画
4. 进入下一轮
```

### 可能的提交路径

### 路径 A：修改 `active_stack` 状态字段（最可能）

`_BattleStack_` 结构中可能有以下字段：

```cpp
struct _BattleStack_ {
    // ... 已知的字段 ...
    DWORD action_type;    // 0=未设置, 1=攻击, 2=防御, 3=撤退, 4=投降
    DWORD target_x;       // 目标坐标 X
    DWORD target_y;       // 目标坐标 Y
    DWORD spell_id;       // 施法时存储法术 ID
    // ...
};
```

**调查方法**：
1. 在战斗中手动点击"防御"按钮
2. Hook `0x495C50`（战斗循环），在行动执行前 dump `active_stack` 结构
3. 对比行动前后的字段变化，找到动作类型和目标字段

### 路径 B：模拟用户输入（SendMessage/PostMessage）

```cpp
// 模拟点击目标位置的坐标
PostMessage(hwndBattle, WM_LBUTTONDOWN, 0, MAKELPARAM(x, y));
PostMessage(hwndBattle, WM_LBUTTONUP, 0, MAKELPARAM(x, y));
```

**缺点**：依赖窗口坐标，容易被干扰，不够可靠。

### 路径 C：Hook 战斗行动提交函数

找到"防御/撤退/投降"按钮点击后的处理函数，直接调用：

```cpp
// 推测的函数
void __thiscall BattleSubmitAction(_BattleMgr_* bm, int action, int target);
// Hook 地址待确认
```

**调查方法**：
1. IDA 搜索字符串 "defend"、"retreat"、"surrender"
2. 找到按钮点击处理函数
3. 分析函数签名和参数

### 待做

- [ ] 在战斗中 Hook `0x495C50`，dump `active_stack` 关键字段
- [ ] 手动执行防御/撤退/投降，对比 `active_stack` 变化
- [ ] IDA 搜索 "defend" 字符串，找提交动作的函数
- [ ] 确认行动类型的枚举值（防御=?, 撤退=?, 投降=?）

---

## 3. 下拉框控件

### 结论：不需要单独做插件

H3Auto 内部实现即可。用 `_DlgCustomButton_` + 弹出小列表框模拟：

```
点击按钮 → 创建临时子窗口（含4个选项按钮）→ 点选项 → 关闭子窗口 → 更新按钮文本
```

参考 MegaDesc 中的下拉框实现（如果有）。

### 控件结构

```cpp
// 下拉框状态
struct ComboBoxState {
    int selected_index;           // 当前选中项 0~3
    int x, y, w, h;               // 按钮位置和大小
    bool is_open;                 // 是否展开
    HWND popup_hwnd;              // 弹出窗口句柄
};

// 下拉框选项
static const char* STRATEGY_OPTIONS[] = {
    "手动",
    "防御",
    "随机射击",
    "智能射击",
    "平衡射击"
};
```

### 弹出列表窗口

- 窗口风格：`WS_POPUP | WS_BORDER`，无标题栏
- 5 个按钮垂直排列，每个 120×20px
- 点击选项 → 更新选中项 → 关闭弹出窗口 → 重绘主按钮
- 点击按钮外区域 → 关闭弹出窗口

### 待做

- [ ] 参考现有项目中类似弹出控件的实现
- [ ] 确认 H3API 中 `_DlgCustomButton_` 的用法
- [ ] 在 SettingsDlg.inc.cpp 中实现 ComboBoxState 结构

---

## 4. 行动策略选项

根据用户要求，更新为：

| 值 | 文本 | 说明 |
|---|---|---|
| 0 | 手动 | 默认，不干预，用户自行操作 |
| 1 | 防御 | DEFEND，不要主动攻击 |
| 2 | 随机射击 | 随机选择目标生物攻击 |
| 3 | 智能射击 | 优先敌方远程 > 速度快 > 生物等级高 |
| 4 | 平衡射击 | 打击使敌方剩余数量趋于平衡（打数量最多的那队） |

### 策略实现说明

- **手动**：不干预，正常游戏逻辑
- **防御**：`active_stack` 设置防御状态
- **随机射击**：从敌方存活部队中随机选一个
- **智能射击**：优先敌方远程 > 速度快 > 生物等级高
- **平衡射击**：打击使敌方剩余数量趋于平衡（打数量最多的那队）

---

## 5. 战区坐标（A01~H15）

### 坐标系统

- 横向：A, B, C, D, E, F, G, H（共8列）
- 纵向：01~15（共15行）
- 左下角为 A01，右上角为 H15（参考 HoMM3 战斗地图坐标系）

### 坐标转换

```cpp
// stack->position 存储为整数（如 0xXY），需要转换为 A01 格式
const char* PosToString(int pos) {
    static char buf[8];
    int col = (pos & 0xF0) >> 4;  // 高位 = 列 0~7 → A~H
    int row = pos & 0x0F;          // 低位 = 行 0~14 → 01~15
    sprintf(buf, "%c%02d", 'A' + col, row + 1);
    return buf;
}
```

> **注意**：需要确认 HoMM3 内部坐标存储方式（上式为假设）。实际可能横向是行号（A=1），纵向是列号（01=第1格），需要通过实测确认。

### 待做

- [ ] 在战斗中读取 `stack->position`，确认坐标编码方式
- [ ] 对比战区地图上的实际位置，验证转换公式

---

## 6. Hook 地址验证

| 地址 | 类型 | 用途 | 状态 |
|---|---|---|---|
| `0x495C50` | HiHook | 战斗动画循环 | 待实测 |
| `0x41B120` | LoHook | 对话框 DefProc | 待确认按钮 ID |
| `0x464F10` | HiHook | 施法后标记策略变更 | 待确认必要性 |
| `0x4781C0` | HiHook | 战斗开始清空策略 | 待验证 |

### 待做

- [ ] 用 H3API 模板项目测试 Hook `0x495C50` 是否能正常触发
- [ ] 确认战斗开始/结束的 Hook 地址是否正确
