# 安装说明 / Installation guide — RC10

正式包名 / Official package name: **Diablo II for RGDSplus.zip**。GitHub 自动规范的下载名 / GitHub-normalized download filename: `Diablo.II.for.RGDSplus.zip`。包内名称保持空格 / Internal names retain spaces.

## 前提 / Prerequisites

本项目仅为 RGDSplus 双屏适配包，不含任何正版游戏资源。严禁盗版和内置游戏二次分发。需要兼容的 RGDSplus Linux/Wayland/PortMaster 固件和 Windows x64 PC；PC 导入器已附 Python/Pillow，不要求系统另装 Python。离线运行组件不替换固件或显示驱动。

This is an RGDSplus dual-screen adapter only, with no retail game assets. Piracy and redistribution with bundled games are prohibited. You need compatible RGDSplus Linux/Wayland/PortMaster firmware and a Windows x64 PC. Embedded Python/Pillow are supplied for import; system Python is unnecessary. Offline runtimes do not replace firmware or GPU drivers.

**先检查资源前提再下载：** 需要自己的正版传统 PC 版 Diablo II + Lord of Destruction、导入器支持的精确英文 enUS 1.14b 资源，以及合法取得且匹配 RC10 的独立中文分片。核心版本仍是 1.13d，1.14b 指资源版本；不是重制版、安装器目录或任意其他语言/补丁版本。

**Check dependencies first:** your lawful classic Diablo II + Lord of Destruction installation, the exact supported enUS 1.14b data profile, and the lawfully obtained matching RC10 Chinese supplement are required. The engine remains 1.13d; 1.14b describes the imported data. Resurrected, installer folders and arbitrary locales/patch versions are unsupported.

中文分片未公开发布，因现有来源记录不足以证明全部内容的再分发授权。RC10 对该分片有硬性校验；缺少时会停止，当前没有已验收的英文替代路径。普通中文补丁或自己拥有正版不等于满足其固定内容要求，不能通过关闭校验解决。

The supplement is withheld because complete redistribution permission has not been established. RC10 checks it strictly and stops if missing. No accepted English-only alternative exists. An arbitrary translation patch or game ownership alone does not satisfy the fixed-content dependency; do not disable validation.

## 1. 解压 / Extract

从 Releases 获取适配 ZIP、`SHA256SUMS.txt`，在 PC 全新空目录（例如 `D:\D2-Fresh-Install`）解压。PowerShell 可校验：

Download the adapter ZIP and checksum from Releases, verify it, then extract into a new empty PC folder:

```powershell
Get-FileHash -Algorithm SHA256 '.\Diablo.II.for.RGDSplus.zip'
```

应为 / Expected: `c72543438ae4a89a2d836c604eb6f373f917aec7e4ce778fbe2a1a133dc18c83`。

将自己合法取得的匹配中文分片放在同一个新目录的 `Ports\Diablo II for RGDSplus\game-import\chinese-patch\`。不要直接将分片改名为 `Patch_D2.mpq`，也不要放入 `gamedata`。公开 Releases 不提供中文包；ZIP 内提及“两个 ZIP”的旧说明是私有验收流程背景，以本说明的公开依赖限制为准。

Place your lawfully obtained matching supplement under `Ports\Diablo II for RGDSplus\game-import\chinese-patch\`. Do not rename fragments to `Patch_D2.mpq` or put them in `gamedata`. Public Releases do not supply the supplement. References to “two ZIPs” inside the unchanged baseline describe its original private acceptance workflow; this guide explains the public distribution limitation.

## 2. 自备核心 / Supply the core

自行访问 [作者项目页](https://repo.openpandora.org/?app=package.diablo2&page=detail)，固定适用文件为 [notaz standalone ARM core](https://notaz.gp2x.de/misc/starec/libd2game_sa_arm.exe.so.xz)。作者背景见 [upstream notes](https://notaz.gp2x.de/misc/starec/libd2game.txt)。下载链接不表示本项目取得或转授其再分发许可。

Obtain the pinned standalone file separately from the upstream author. Linking upstream does not grant or transfer redistribution rights.

放入 / Place in:

```text
Ports/Diablo II for RGDSplus/engine-input/libd2game_sa_arm.exe.so.xz
```

保持 `.so.xz` 文件名，不需要解压；也可仅放其解压后的 `.so`，两者只能选一个。当前 Pandora PND r4 的地址布局不匹配，不可替代。压缩文件 SHA256：

Keep the full `.so.xz` filename. Alternatively supply only its decompressed `.so`; never both. The current Pandora PND r4 has an incompatible layout. Compressed file SHA256:

```text
b9a9b880f674571a8d9ca09d8604b173126e2651778eb23714064ba71332f103
```

## 3. 本地导入 / Import locally

双击 `Ports\Diablo II for RGDSplus\Import Game Assets.cmd`，输入自己的正版安装目录。不要单独复制 CMD，必须保持全部配套文件。导入器验证适配文件、分片及核心，在独立暂存目录复制/重组资源、修正背包并生成前端缓存；源正版安装保持只读。成功提示为 `INSTALLATION READY`。失败时不要忽略错误或复制半成品到设备；本地日志可供自己排查，不公开上传。

Run `Import Game Assets.cmd` and enter your lawful PC installation directory. Keep the CMD with all companion files. Import checks the adapter, supplement and core, prepares data in an isolated staging folder, applies the inventory correction and generates frontend caches. The source game installation is read-only. Wait for `INSTALLATION READY`. Do not deploy a failed/partial import or publicly upload its logs.

已有非空 `gamedata`、`private-assets`、存档、初始化 prefix 或已生成核心的目录会被拒绝；不要把此全新安装工具用于现有玩家目录。

Nonempty game/cache/save directories, an initialized prefix or a prepared core cause rejection. This fresh-install tool is not an in-place updater for an existing player installation.

## 4. 卡二与启动 / Card two and launch

退出设备上的游戏，备份旧 `.sh` 入口、完整同名目录、`saves/` 和 `prefix.ext4` 至 PC 并核对。安全移走旧同名安装，再把 PC 本地准备好的 `Ports` 合并到卡二根目录，避免 `Ports/Ports/`；至少保留 4 GiB 可用空间。安全弹出、插回设备，从固件 Ports 人工启动 **Diablo II for RGDSplus**。首次启动会生成 prefix。不要同时运行多个本项目实例。

Exit the game; back up the old launcher, whole installation, saves and prefix to PC and verify the backup. Move the old same-name installation aside, copy the locally prepared `Ports` into card two's root without nesting `Ports/Ports/`, and keep at least 4 GiB free. Eject safely, reinsert and manually launch **Diablo II for RGDSplus** from firmware Ports. First launch initializes the prefix. Do not run concurrent instances.

```text
Ports/
  Diablo II for RGDSplus.sh
  Diablo II for RGDSplus/
    launch.bash
    game-import/                  # import tools / 导入工具
    engine-input/                 # supplied locally / 玩家自备
    gamedata/                     # generated locally; never redistribute
    private-assets/               # game-derived cache; never redistribute
    libd2game_sa_arm.exe.so        # prepared locally; never redistribute
    saves/                        # personal; back up / 玩家数据
    prefix.ext4                   # created on first launch / 首次启动生成
```

## 使用与排查 / Use and troubleshooting

下屏触摸及手柄输入由本适配处理，R3 提供光标/直接移动切换，具体面板语义见 `controller-layout.json`、`ui_navigation.py`。请先体验菜单、创建/命名、进世界、背包、保存退出和重载。优先使用游戏内保存退出；紧急退出不能替代保存。

The adapter handles lower-screen touch and controller input. R3 toggles cursor/direct movement; panel semantics are defined in the published configuration/code. Check menus, naming, entering the world, inventory, saving/exiting and reloading. Prefer in-game save and exit; emergency termination is not a substitute for saving.

触控异常时可断开充电/USB 后对照复测，但不能据此断言所有故障已解决。若卡只读或出现 FAT 错误，先停止游戏、保护最新存档并离线检查文件系统；不要强行继续写入。反馈版本、固件、供电/触摸条件与最小复现步骤，不上传资源或完整诊断。

If touch behaves unexpectedly, compare with charging/USB disconnected; that does not establish a universal fix. On read-only/FAT errors, stop, protect the latest saves and check the filesystem offline. Report version, firmware, power/touch conditions and minimal reproduction steps without game data or full diagnostics.

**安装完成的目录只供个人合法使用，禁止作为“免导入版”“内置游戏版”再次分发。The prepared installation is for lawful personal use; do not redistribute it as a ready-to-play or game-bundled package.**
