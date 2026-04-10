# YU-RIS Script Editor

YU-RIS 引擎脚本编辑器GUI。支持 YBN 解析、文本编辑/回写，以及部分 YPF 封包读写操作。

- 自检测密钥、编码和引擎信息
- 支持拖选 `.ybn` 脚本、`.ypf` 资源包、`ysbin` 文件夹
- 支持纯脚本文本或翻译三行格式导出
- 支持 YPF 预览导出（不支持包含非脚本文件的 YPF 回封）

- 可视化编辑，支持搜索编辑，实时保存

## 预览

![](https://p.sda1.dev/31/6b38b4da12753b1b087b1f7b2c43cd12/preview1.png)

![](https://p.sda1.dev/31/4a2425ba7ebd02b89d5f04b5c6c5130f/preview2.png)

## 开始

Python 3.10+

```bash
git clone https://github.com/Aionfatedio/YU-RIS-Script-Editor.git

cd YU-RIS-Script-Editor

pip install PyQt5 PyQt-Fluent-Widgets

python start.py
```

## 用法

1. 启动程序后，拖选游戏文件到拖放区
3. 工具分析后，双击文件跳转至编辑器预览
4. 根据需要使用编辑器修改或导出文本

### YBN 脚本文件

- 点击「在编辑器中查看」在编辑器预览修改文本
- 点击「导出脚本文本」导出为纯文本，或「导出翻译三行」导出为翻译用的三行对照格式
- 若文件加密，可点击「解密为 YBN」导出解密后的文件

### YSBIN 脚本文件夹

- 自扫描所有 YBN 文件，文件列表支持排序或筛选
- 双击列表中剧情脚本可在编辑器中打开
- 支持批量导出

### YPF 封包

- 自解析封包索引，列出 ysbin 目录下的所有脚本
- 点击「导出资源文件」可导出封包内的全部文件（若文件中包含CG、音频等资源，将一并导出）
- 双击脚本文件在编辑器中打开
- 仅含 YBN 文件的**纯脚本封包**编辑保存时自动封回源文件

### 游戏程序

- 自检测同目录下的 `.ypf` 文件 或 `ysbin/` 文件夹
- 可处理多脚本文件共存场景

### 编辑器

| 操作     | 说明                                                         |
| -------- | ------------------------------------------------------------ |
| 文本编辑 | 在编辑器中预览修改，保存生效。`[OPT]` 前缀表示选项文本，请保留 |
| 搜索替换 | `Ctrl+F` 打开搜索替换栏，支持上下导航和批量替换              |
| 编码切换 | 适用于需要更换编码查看的场景                                 |
| 保存     | 点击「保存」写回原文件（纯脚本 YPF 自动封包）                |
| 另存为   | 点击「另存为」导出为独立 YBN 文件                            |

## 项目结构

```
YU-RIS-Script-Editor/
  start.py              # 入口
  config.json           # 用户配置
  core/
    ystb.py             # YSTB 脚本解析算法 (V2/V5)
    ypf.py              # YPF 封包解析算法
    yscm.py             
    ystl.py             
    encoding.py         
  gui/
    main_window.py      # 主窗口 (基于PyQt-Fluent-Widgets)
    workspace_page.py   
    editor_page.py      # 编辑器
    settings_page.py    
    workers.py          
  text/
    exporter.py         # 文本导出
    importer.py         # 文本导入
```

## 已测试的游戏

- Whirlpool 社系列游戏
- [人生通行止め] コトネイロ
- [Lusterise] 光翼戦姫エクスティアMarina Bright Feather


## 鸣谢

- **[YURIS_TOOLS](https://github.com/jyxjyx1234/YURIS_TOOLS)** by [jyxjyx1234](https://github.com/jyxjyx1234). 提供了新版 YU-RIS 引擎的解密算法
- **[RxYuris](https://github.com/ZQF-ReVN/RxYuris)** by [ZQF-ReVN](https://github.com/ZQF-ReVN). 提供了旧版 YU-RIS 引擎的解密算法
- [**GARbro**](https://github.com/morkt/GARbro) by [morkt](https://github.com/morkt). 提供了 YPF 封包的解密算法
