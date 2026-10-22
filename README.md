# Diablo II for RGDSplus

RGDSplus 双屏适配包 · RGDSplus dual-screen adapter  
适配维护 / Adapter maintainer: **Blood_roc (LPF970915)**

> **该项目仅为 RGDSplus 机型的双屏版本适配包，不包含任何正版游戏资源。严禁盗版，严禁将游戏本体或资源内置后进行二次分发。请自行合法购买并提供受支持的《Diablo II》及《Lord of Destruction》传统 PC 版资源。**
>
> **This project is only a dual-screen adaptation package for the RGDSplus handheld. It contains no retail game assets. Piracy and redistribution with bundled game files are strictly prohibited. You must legally obtain and supply the supported classic PC releases of Diablo II and Lord of Destruction yourself.**

本项目是面向 RGDSplus 双 1024×768 屏幕、Linux/Wayland 固件和 PortMaster 运行环境的非官方设备适配。它不是游戏本体、完整游戏移植源码、重制版，也不是 Blizzard、notaz、PortMaster 或设备厂商的官方发行版；不表示上述主体认可或授权本项目。

This is an unofficial device adaptation for the RGDSplus, its two 1024×768 displays, compatible Linux/Wayland firmware and PortMaster environment. It is not the game, a complete game-engine source release, Diablo II: Resurrected, or an official release endorsed by Blizzard, notaz, PortMaster or the device manufacturer.

## 下载与当前基线 / Download and baseline

从 [Releases](https://github.com/LPF970915/Diablo-II-for-RGDSplus/releases) 下载 **Diablo.II.for.RGDSplus.adapter.zip**、校验文件和双语安装说明。GitHub 自动生成的 Source code 压缩包仅是可公开源码快照，不能作为完整安装包使用。

Download **Diablo.II.for.RGDSplus.adapter.zip**, its checksum and the bilingual installation guide from [Releases](https://github.com/LPF970915/Diablo-II-for-RGDSplus/releases). GitHub's automatic source archives contain the published source snapshot, not the complete adapter runtime package.

| 项目 / Item | 值 / Value |
| --- | --- |
| 用户接受基线 / User-accepted baseline | `20261023-player-rc10` |
| 接受日期 / Acceptance date | 2026-10-23 |
| 适配 ZIP 大小 / Adapter ZIP size | 158,250,551 bytes |
| SHA256 | `c72543438ae4a89a2d836c604eb6f373f917aec7e4ce778fbe2a1a133dc18c83` |
| 核心组合 / Engine combination | Player-supplied pinned notaz 1.13d ARM core + local adaptation delta |
| 正版资源 / Retail assets | Exact supported classic enUS 1.14b profile; player supplied |

**公开下载的安装边界：RC10 导入器强制要求其匹配的独立中文分片。本仓库及 Releases 不提供该分片**：现有记录不能确认其中全部候选内容的原创性及再分发授权。拥有正版游戏并不自动取得该社区分片的再分发权。没有合法取得且哈希匹配的配套分片时，RC10 会停止导入；当前没有已验收的免中文分片/纯英文安装路径。请勿下载未知“整合包”补齐，也不要把普通中文补丁随意改名代替。

**Public installation limitation: RC10 requires its matching separate Chinese supplement. That supplement is NOT distributed in this repository or its Releases**, because the available provenance does not establish redistribution permission for all its candidate content. Owning the game does not automatically grant rights to redistribute that community supplement. Without a lawfully obtained, hash-matching supplement the importer stops. There is currently no accepted supplement-free/English-only installation path. Do not substitute an unknown prepacked game or rename an arbitrary translation patch.

## 适配范围 / What the adapter does

- 游戏世界采用连续双屏画布与索引色显示桥，配合设备显示输出；不是把同一画面简单复制两次。Continuous dual-screen world presentation through an indexed display bridge, rather than duplicating one image on both panels.
- 启动动画/加载画面使用上屏；标题、主菜单、选角和创建/命名页面按各自规则分配上下屏，燃烧 Logo 与副标题移至上屏。Startup movies/loading use the upper panel; title/menu/character pages have specific layouts, with the animated logo and subtitles on the upper display.
- 下屏触摸、点击/长按、光标跟随、手柄导航、战斗请求、背包/装备界面导航及角色命名键盘的设备适配。Device-specific lower-screen touch, tap/hold and cursor handling, controller navigation, combat requests, inventory/equipment navigation and a naming keyboard.
- 从玩家本地 MPQ 生成页面、Logo、字幕和缓存；保留原版 10×4 背包布局并在本地生成所需修正。Local extraction/generation of menu pixels, logo/subtitles and caches from player-owned MPQs, including the classic 10×4 inventory correction.
- 启动、离线依赖、声音预检、资源哈希校验、Windows x64 导入编排及独立玩家状态目录。Launch/runtime integration, audio preflight, resource checksums, Windows x64 import orchestration and separate player state.

这些功能依赖现有核心和正版数据，不提供新的游戏剧情、关卡、美术资源库、商业授权、联网服务或通用机型兼容承诺。

These functions depend on the external core and lawful game data. This project supplies no game campaign, levels, retail artwork library, commercial game license, online service or general device compatibility guarantee.

## 安装 / Installation

完整步骤、目录示例和故障边界见 **[中英双语安装说明 / Bilingual installation guide](docs/INSTALL.md)**。

1. 先确认拥有合法的受支持 PC 资源及合法取得的匹配中文分片。Confirm access to lawful supported PC files and the required lawfully obtained matching supplement.
2. 在 Windows x64 PC 的全新空目录解压适配 ZIP，再放入匹配分片。Extract into a new empty folder on Windows x64, then supply the matching supplement.
3. 自行从 [notaz 作者地址](https://notaz.gp2x.de/misc/starec/libd2game_sa_arm.exe.so.xz) 获取固定核心并放入 `engine-input/`；不使用当前 Pandora PND r4 或自编 1.14 核心。Obtain the pinned core separately and place it in `engine-input/`; the current Pandora PND r4 and custom 1.14 cores are incompatible with this adapter.
4. 双击 `Import Game Assets.cmd`，指定自己的正版目录，等待 `INSTALLATION READY`。Run the importer against your own lawful installation and wait for `INSTALLATION READY`.
5. 退出设备游戏，备份旧安装、`saves/` 与 `prefix.ext4`；把新生成的 `Ports` 放到卡二根目录，保持至少 4 GiB 可用空间，从固件 Ports 手动启动。Exit the device game, back up the old installation and player state, copy the locally prepared `Ports` to card two, keep at least 4 GiB free, then launch manually from the firmware's Ports menu.

**不得上传或分享导入后的目录、核心、MPQ、从游戏提取/生成的缓存、prefix、存档或原始诊断。Do not upload or share the imported installation, core, MPQs, game-derived caches, prefix, saves or raw diagnostics.**

## 仓库与产物边界 / Published contents

| 位置 / Location | 内容 / Contents |
| --- | --- |
| `adapter/Ports/` | RC10 的 Python/Bash、导入器、按键/显示配置及现存 C 源码快照 / RC10 scripts, import tools, configuration and available C sources |
| `packaging/` | 固定基线、229 项 ZIP 文件白名单与源码哈希 / Pinned baseline, 229-file ZIP allowlist and source hashes |
| `tools/audit_public.py` | 白名单、完整性和禁止内容审计工具 / Allowlist, integrity and prohibited-content audit |
| `docs/` | 双语安装、范围、权利与依赖说明 / Bilingual installation, scope and rights documentation |
| Releases | 原始 RC10 适配 ZIP、SHA256 与双语说明 / Unmodified RC10 adapter ZIP, checksum and bilingual guides |

适配 ZIP 包含离线 Wine/Weston 等运行组件、Windows Python/Pillow/StormLib、空的 ext4 文件系统模板、原生适配库、局部核心差分和新增上屏扩展图。上屏 PNG 为基于本地游戏画面参考生成的扩展素材，不是原版隐藏场景，也不代表获得游戏美术权利。原版场景、Logo、字幕及游戏缓存只在玩家本地生成。空 ext4 模板不是带注册表、玩家设置或存档的初始化 Wine prefix。

The adapter ZIP includes offline runtime components, Windows Python/Pillow/StormLib, an empty ext4 filesystem template, native adaptation libraries, a local core delta and generated upper-screen extensions. The extension PNGs were generated using local game scenes as references; they are not hidden original scenery or a grant of rights in game artwork. Original scenes, logos, subtitles and game caches are generated locally. The empty ext4 template is not an initialized Wine prefix containing registry/player data.

不发布完整核心、任何 MPQ/中文分片、正版游戏文件、私有缓存、实机完整备份、QA 测试脚本/证据、日志、凭据、玩家存档和历史实验。仓库是经过筛选的单次公开快照，没有导入私有开发历史。

No complete core, MPQ/Chinese supplement, retail game files, private caches, full device backups, QA scripts/evidence, logs, credentials, player saves or historical experiments are published. This is a curated public snapshot, without private development history.

## 验收与源码限制 / Validation and source limitations

RC10 于 2026-10-23 经用户从正式入口人工运行后被指定为最新基线。已有本地导入/回归和独立设备检查记录，但这不等于全部流程、长期稳定性、所有固件、所有真实手势/物品拖放或硬件延迟已经完整验证；充电相关触摸异常的根因没有独立证明，不承诺永不复发。请备份存档并按自己的实际环境验证。

RC10 was accepted by the user after manually running the normal launcher on 2026-10-23. Local import/regression and isolated device checks exist, but do not establish exhaustive gameplay, long-term stability, all firmware compatibility, every physical gesture/item drag, or measured end-to-end hardware latency. The cause of charging-related touch anomalies was not independently established; permanent elimination is not claimed.

**`world_probe.so` 与 `indexed_gpu.so` 的完整精确源码及原始工具链未恢复。** 本仓库不以历史实验源码冒充它们，不承诺从源码完整重建所有二进制。已有 `retail_mpq.c`、`retail_probe.c` 按实际恢复状态提供。可用 `python tools/audit_public.py --archive "path/to/Diablo.II.for.RGDSplus.adapter.zip"` 检查固定产物；后续修改需要新 build ID 与相应验证，不能覆盖 RC10 并沿用旧验收结论。

**The exact full sources/toolchain for `world_probe.so` and `indexed_gpu.so` were not recovered.** Historical prototypes are not passed off as those sources. Full binary reproducibility is not claimed. Available C files are supplied as recovered. Use the audit command above for the pinned artifact; future changes require a new build ID and appropriate validation.

## 权利与反馈 / Rights and feedback

详见 [权利声明 / Rights notice](docs/RIGHTS.md)、[原创贡献条款 / Original-contribution terms](LICENSE.md) 与 [第三方声明 / Third-party notices](THIRD_PARTY_NOTICES.md)。第三方组件各自的许可证继续有效；本项目不对游戏和第三方内容授予权利，不提供破解、序列号、授权绕过或盗版获取渠道。

See the linked notices. Third-party licenses remain applicable; this project grants no rights to the game or third-party content and provides no cracks, keys, license circumvention or piracy sources.

反馈请使用 [Issues](https://github.com/LPF970915/Diablo-II-for-RGDSplus/issues)，提供 build、固件、供电状态、操作来源及复现步骤。只在本地检查并脱敏后附最小必要错误片段，不上传游戏文件、完整日志、存档、账号资料或含游戏资源的安装目录。权利人也可通过 Issues 提出具体权属问题；维护者可在核实期间移除争议文件。

Use Issues for the build, firmware, power/input conditions and reproduction steps. Inspect/redact locally and share only the minimum relevant error excerpt; do not attach game files, full logs, saves, account data or prepared installations. Rights holders can identify specific concerns through Issues; disputed material may be removed pending review.
