# TXT Nova Toolkit

`TXT Nova Toolkit` 是一个 Calibre GUI 插件，用于按固定文件名规则导入、更新和导出 TXT 小说。

## 功能

- 导入标准命名的 `.txt` 小说文件。
- 自动从文件名解析书名、作者、状态和标签。
- 连载书同名同作者再次导入时，更新已有记录。
- 更新连载时覆盖旧 TXT，并删除旧的非 TXT 派生格式。
- 完结、完本、全本、断更同名书不覆盖已有记录，而是新增记录并标记为 `重复`。
- 更新简介历史：最新文件名在第一行，最多保留 5 行。
- 所有通过插件处理的记录，出版日期固定为 `2000-12-31`。
- 出版方为空时补为 `中国成人文学精选`。
- 导出选中书籍的 TXT，导出文件名取简介第一行。
- 导出完成后自动打开目标文件夹。

## 安装

可安装插件包位于：

```text
dist/TXTNovaToolkit.zip
```

安装步骤：

1. 打开 Calibre。
2. 进入 `首选项` -> `高级` -> `插件`。
3. 点击 `从文件加载插件`。
4. 选择 `dist/TXTNovaToolkit.zip`。
5. 重启 Calibre。

如果之前安装过旧版 `TXT Novel Importer`，建议先在 Calibre 插件列表中卸载旧插件，再安装 `TXT Nova Toolkit`。

## 使用

安装后，Calibre 工具栏会出现 `TXT Nova Toolkit` 按钮。

按钮下拉菜单包含：

- `导入/更新 TXT 小说`
- `导出选中 TXT 小说`

## 文件名格式

插件要求导入文件名符合以下格式：

```text
《书名》 起始-结束章 状态 作者：作者.txt
```

示例：

```text
《测试书》 1-100章 连载 作者：测试作者.txt
《测试书》 1-200章 L连载 作者：测试作者.txt
《测试书》 1-300章 完结 作者：测试作者.txt
```

## 导入规则

连载书：

- 如果找到同书名、同作者的已有记录，则更新该记录。
- 更新时覆盖 TXT 格式。
- 更新时删除 EPUB、AZW3、MOBI 等所有非 TXT 格式。
- 更新时保留封面、评分、自定义列和已有标签。
- 如果原记录没有标签，则按新文件名生成标签。

完结、完本、全本、断更书：

- 如果找到同书名、同作者的已有记录，不覆盖旧记录。
- 新增一条记录。
- 新记录标签设置为 `重复`。

小文件：

- 如果导入 TXT 小于 `500 KB`，丛书设置为 `太短了，先养一养`。

## 标签规则

插件按文件名中的状态和标志生成组合标签。

常见映射：

```text
NTR连载 -> NTR、连载
NTR完结 -> NTR、完结
NTR断更 -> NTR、断更
L连载 -> 刘备、连载、加料
L完结 -> 刘备、完结、加料
L断更 -> 刘备、断更、加料
连载 -> 刘备、连载
完结 / 完本 / 全本 -> 刘备、完结
断更 -> 刘备、断更
```

## 简介规则

新增书籍时：

- 简介写入文件名主体，不包含 `.txt`。

更新已有连载书时：

- 本次导入文件名主体写入第一行。
- 原简介内容下移。
- 最多保留 5 行。
- 超过 5 行时删除最下面的旧行。

## 导出规则

导出选中书籍时：

- 读取书籍的 TXT 格式。
- 导出文件名取简介第一行。
- 如果简介为空，回退为 `书名 - 作者.txt`。
- 如果目标目录已有同名文件，自动追加序号，例如 `书名 (2).txt`。
- 导出完成后自动打开目标目录。

## 项目结构

```text
.
├── README.md
├── dist/
│   └── TXTNovaToolkit.zip
├── docs/
│   └── TXT Nova Toolkit 开发计划.md
└── src/
    └── txt_nova_toolkit/
        ├── __init__.py
        ├── ui.py
        ├── plugin-import-name-txt_nova_toolkit.txt
        └── images/
            ├── icon.png
            └── icon.svg
```

## 打包

在 `src/txt_nova_toolkit/` 目录内，将插件文件打包到 zip 根目录：

```powershell
Compress-Archive -Path "__init__.py", "ui.py", "plugin-import-name-txt_nova_toolkit.txt", "images" -DestinationPath "..\..\dist\TXTNovaToolkit.zip" -Force
```

## 注意事项

- 插件不会修改 Calibre 的全局 Auto Merge 设置。
- 推荐关闭 Calibre 自带 Auto Merge，由插件按钮接管导入和更新。
- 插件不会删除磁盘上的原始 TXT 文件。
- 更新连载时会删除 Calibre 记录内的非 TXT 格式文件。
