# 第三方与来源 / Third-party components and provenance

本项目为非官方 RGDSplus 适配，第三方组件仍适用原许可证。下列链接为来源说明，不代表对游戏或组件转授权。ZIP 内原有声明与许可证保持原字节；新增说明以本文件为准，不改写历史来源。

This is an unofficial adaptation. Third-party licenses remain applicable. Source links do not transfer game/component rights. Existing notices/licenses remain unchanged in the baseline ZIP; this file supplies additional distribution context.

| Component / 组件 | Upstream / 来源与许可说明 |
| --- | --- |
| notaz ARM core | [Project page](https://repo.openpandora.org/?app=package.diablo2&page=detail), [author notes](https://notaz.gp2x.de/misc/starec/libd2game.txt). Player-supplied; no complete core published / 核心自备，不镜像完整文件 |
| Wine 4.0 | [Wine](https://www.winehq.org/), LGPL and component-specific terms; existing image notices retained / 保留镜像内声明 |
| Weston runtime | [Westonpack](https://github.com/binarycounter/Westonpack), [PortMaster runtimes](https://github.com/PortsMaster/PortMaster-New/tree/main/runtimes); licenses depend on bundled components / 按内含组件许可证 |
| gptokeyb | [PortsMaster/gptokeyb](https://github.com/PortsMaster/gptokeyb), GPL; bundled GPL notice retained / 包内保留 GPL 文本 |
| StormLib | [ladislav-zezula/StormLib](https://github.com/ladislav-zezula/StormLib), MIT; bundled notice retained / 保留 MIT 文本 |
| Python 3.12.10 embedded x64 | [Python](https://www.python.org/), licensing in `game-import/python/LICENSE.txt` |
| Pillow 12.1.1 | [Pillow](https://python-pillow.org/), wheel metadata/licenses and dependency notices retained under `pillow-12.1.1.dist-info` / 保留 wheel 原有许可 |
| zlib | [zlib](https://zlib.net/), runtime component notice retained / 运行镜像内保留声明 |
| supplementary Linux libraries | Package URLs/hashes in `adapter/Ports/Diablo II for RGDSplus/licenses/*-source.json`; archive package copyright files retained / 归档保留包版权文件 |
| BSDIFF40 | [Format description](https://www.daemonology.net/bsdiff/); local Python reader uses standard library / 本地读取器使用 Python 标准库 |

原生 `world_probe.so`、`indexed_gpu.so` 来自恢复的既有适配二进制，精确源码和原始构建工具链缺失；不以其他历史源码替代，不将整个二进制包宣称为作者独立原创或完全开源可重建。可用的解压/探测 C 源文件按实际状态公开。第三方源码链接及许可证不能替代特定许可证所要求的对应源码履约；本文不宣称已完成所有第三方许可义务的独立法律审计。

The recovered native adaptation binaries have missing exact sources/toolchains. They are not represented as entirely original or fully source-rebuildable. Available C files are published as recovered. Upstream source links and license texts do not replace corresponding-source obligations where required; this notice does not claim an independent legal audit of all license obligations.

上屏扩展图通过图像生成工具、以玩家本地解码画面作参考生成，不包含作为参考的下屏截图；原版背景、Logo、字幕从本地 MPQ 生成。生成扩展图并不赋予游戏知识产权。原始字体位图与其他继承组件仅按既有适配载荷保留，不作独占原创性保证。

Upper extensions were generated with local decoded scenes as references; reference lower-screen screenshots are excluded. Retail backgrounds/logo/subtitles are generated locally from MPQs. Generated extensions confer no rights in the game. Inherited font bitmaps/components are retained as part of the existing adapter payload without a claim of exclusive original authorship.

RC41 主包按项目要求包含中文社区补丁数据。其完整权属/来源未独立确认；包含不等于认证或权利背书。旧 ZIP 中的“separate Chinese supplement”是历史依赖说明，RC41 已改为内置。核心差分继承四处历史社区字节修改及适配 hook，历史目的未完全确定；它不是游戏本体，不能将“差分”认定为自动免责。
The RC41 main package includes Chinese community patch data at project direction. Complete rights/provenance were not independently established; inclusion is not a certification or endorsement. The older “separate Chinese supplement” wording describes a historical dependency; RC41 embeds it. The core delta inherits four community byte changes and an adaptation hook; their historical purpose is not fully established. Delta distribution is not automatic legal clearance.
