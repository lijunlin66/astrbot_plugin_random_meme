# astrbot_plugin_random_meme · 随机表情包

<img src="logo.png" alt="随机表情包插件图标" width="160" height="160">

由 **lijunlin66** 创建并维护的 AstrBot 随机表情包插件，支持 Doro、柴郡、龙图，
以及奶龙 GIF 与静态图混合随机获取。每次命令发送一张图片。

**基于 [astrbot_plugin_doro](https://github.com/2356820887/astrbot_plugin_doro)
0.0.6 二次开发**，原作者为 Shingetsu（shingetsu）。上游归属及许可证保留，
详见 [来源与致谢](ATTRIBUTION.md)。

| 项目 | 内容 |
| --- | --- |
| 插件标识 | `astrbot_plugin_random_meme` |
| 展示名称 | 随机表情包 |
| 作者 / 维护者 | [lijunlin66](https://github.com/lijunlin66) |
| 创建日期 | 2026-10-26（Asia/Shanghai） |
| 当前版本 | `1.0.0` |
| 仓库 | [lijunlin66/astrbot_plugin_random_meme](https://github.com/lijunlin66/astrbot_plugin_random_meme) |
| AstrBot 版本 | `>=4.29.1,<5`，已在 4.29.1 验证 |
| 已验证平台 | OneBot v11 / `aiocqhttp`，支持群聊和私聊 |
| 许可证 | [AGPL-3.0](LICENSE) |

创建日期指本派生项目，不改变上游项目的原始作者和历史。

## 安装

### 从 GitHub 仓库安装

在 AstrBot WebUI 的插件管理中选择从 GitHub 仓库安装，粘贴：

```text
https://github.com/lijunlin66/astrbot_plugin_random_meme
```

安装后确认“随机表情包”已启用。依赖会根据 `requirements.txt` 安装。
后续可通过 AstrBot 的插件更新功能获取本仓库的更新。

### 从 ZIP 安装

可以在 GitHub 页面选择 **Code → Download ZIP**，然后通过 AstrBot 的本地插件
上传功能安装；也可上传随本次发布提供的 `astrbot_plugin_random_meme-1.0.0.zip`。

### 从旧插件迁移

如果已安装并启用 `astrbot_plugin_doro`，先停用旧插件，再启用本插件，
避免两个插件同时响应相同命令。本插件使用独立标识和配置，默认冷却为 5 秒。
若旧插件设置了其他冷却时间，可在本插件配置中重新填写。

## 命令

| 命令 | 功能 |
| --- | --- |
| `/doro` | 随机获取一张 Doro 表情包 |
| `/柴郡` | 随机获取一张柴郡表情包 |
| `/龙图` | 随机获取一张龙图表情包 |
| `/奶龙` | 从奶龙 GIF 和静态图的合并清单中随机获取一张 |

奶龙会同时读取仓库 `gif/`、`images/` 两个目录。目前清单为 83 张 GIF 与
62 张静态图，共 145 张；上游图库更新后数量会变化。每次对合并清单直接
等概率抽取，每张图片的抽中概率相同。它使用同一个命令、冷却和缓存。

本插件仅注册上述四条命令。

## 配置

| 配置项 | 类型 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `cooldown_period` | 整数 | `5` | 每个类别的冷却秒数；填 `0` 可关闭冷却 |

冷却按类别在整个插件内共享，不按用户或群单独计算。四类表情分别计时，
奶龙 GIF 和静态图共同计入奶龙类别；失败也会进入对应冷却，避免连续请求异常接口。

## 图片来源与请求方式

| 类别 | 来源 | 方式 |
| --- | --- | --- |
| Doro | [1143520/doro](https://github.com/1143520/doro/tree/main/loop) | 获取图库清单后随机选择 |
| 柴郡 | [HL 柴郡接口](https://api.hlz7.com/chajun) | 直接下载随机图片 |
| 龙图 | [OIAPI 随机表情包](https://oiapi.net/api/FunBoxEmoji?0=dragon) | 按龙图分类下载随机图片 |
| 奶龙 | [GeorgeNaNN/nailong-memes](https://github.com/GeorgeNaNN/nailong-memes) | 合并 `gif/`、`images/` 后随机选择 |

Doro 和奶龙的清单分别缓存在内存中，重载插件后重新获取。GitHub 图片通过
`cdn.jsdmirror.com` 下载；奶龙会检查目录树是否完整，避免使用被截断的清单。
网络与 HTTP 错误最多尝试 3 次，单次 API 请求超时为 15 秒，使用默认 TLS 验证。
接口不可用、清单为空或响应格式错误时，会给出对应提示。

## 开发与验证

目录结构：

```text
astrbot_plugin_random_meme/
├── main.py                # 插件入口与四条命令
├── metadata.yaml          # 插件名称、作者、版本与仓库
├── _conf_schema.json      # 冷却配置
├── logo.png               # 维护者指定的图标
├── requirements.txt       # 运行依赖
├── requirements-dev.txt   # 验证依赖
├── tests/test_plugin.py   # 隔离回归测试
├── README.md
├── CHANGELOG.md
├── ATTRIBUTION.md
└── LICENSE
```

在可导入 AstrBot 4.29.1 的 Python 环境中，从本插件根目录执行：

```sh
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
python -m ruff check main.py tests
python -m ruff format --check main.py tests
```

测试通过模拟 HTTP 响应检查命令、混合随机清单、过滤、缓存、冷却及错误处理，
不调用真实图片 API，不向 QQ 发送测试消息。版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## 来源与许可

本项目基于 `astrbot_plugin_doro` 0.0.6 开发，由 lijunlin66 维护。
保留上游 [AGPL-3.0 许可证](LICENSE)，新增代码同样采用该许可证。
插件图标由维护者指定，图标及表情素材的相关权利归其原作者或权利人所有；
代码许可证不改变这些素材的权利归属。

反馈问题请使用[本仓库 Issues](https://github.com/lijunlin66/astrbot_plugin_random_meme/issues)。
