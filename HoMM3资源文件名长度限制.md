# 英雄无敌3 资源文件名长度限制

## 结论

**资源文件名最大 11 字符 + 1 字节 null 终止 = 固定 12 字节缓冲区。**

即文件名（含扩展名）不超过 **11 个字符**。

## 依据

### LOD 归档条目结构 `H3LodItem`（0x20 字节）
```c
struct H3LodItem {
    CHAR    name[12];      // [00] 资源名，固定 12 字节
    UINT32  nameEnd;       // [0C] always 0, 标记名字结束
    PUINT8  buffer;        // [10]
    UINT32  size;          // [14]
    INT32   type;          // [18]
    UINT32  sizeCompressed;// [1C]
};
```
来源：`H3API/H3Assets/H3Lod.hpp` 第 82-96 行

### 资源管理器条目 `H3ResourceItemData`（0x14 字节）
```c
struct H3ResourceItemData {
    CHAR            m_name[12];    // 固定 12 字节
    UINT            m_nameEnd;     // always 0
    H3ResourceItem* m_item;
};
```
来源：`H3API/H3Assets/H3ResourceManager.hpp` 第 25-33 行

### 分析

1. 游戏用红黑树（`H3ResourceManager : H3Set<H3ResourceItemData>`）管理已加载资源
2. 查找时按名字比较，名字存储在固定 12 字节字段里
3. 11 字符 + null = 刚好填满 12 字节
4. 超过 11 字符的名字会被截断或导致缓冲区溢出

### 实际文件名示例

| 文件名 | 字符数 | 合法 |
|--------|-------|------|
| `CrStkP1.pcx` | 11 | ✅ |
| `CrStkP2.pcx` | 11 | ✅ |
| `bgA.pcx` | 7 | ✅ |
| `icon01.pcx` | 9 | ✅ |

**结论：资源文件名（含扩展名）控制在 11 字符以内。**
