# 安装说明 / Installation guide — RC49

## 前提 / Prerequisites

本项目仅为 RGDSplus 双屏适配包，不包含任何正版游戏资源。严禁盗版，严禁把游戏本体或资源内置后二次分发。需要兼容的 RGDSplus Linux/Wayland/PortMaster 固件和 Windows x64 PC；导入器已带 Python/Pillow，不要求系统另装 Python。

This is an RGDSplus dual-screen adapter only, with no retail game assets. Piracy and redistribution with bundled games are prohibited. You need compatible RGDSplus Linux/Wayland/PortMaster firmware and a Windows x64 PC. Embedded Python/Pillow are supplied for import; system Python is unnecessary.

需要自己合法拥有的传统 PC 版《Diablo II》+《Lord of Destruction》资源，精确受支持的 enUS 1.14b 数据配置。核心仍是 1.13d；1.14b 指资源版本。重制版、安装器目录或任意其他语言/补丁版本不受支持。

You need your own lawful classic PC Diablo II + Lord of Destruction installation with the exact supported enUS 1.14b data profile. The engine remains 1.13d; 1.14b describes the imported data. Resurrected, installer folders and arbitrary locales/patch versions are unsupported.

**主包自 RC41 起已包含中文补丁**，位于 `game-import/chinese-patch/`；不需要再单独下载或放置中文分片。主包仍不包含完整核心、正版游戏 MPQ、prefix、存档或游戏派生缓存。

**The Chinese patch has been integrated since RC41** under `game-import/chinese-patch/`; no separate supplement download or placement is required. The package still contains no complete core, retail game MPQs, prefix, saves or game-derived caches.

## 1. 解压 / Extract

从 Releases 获取 `Diablo II for RGDSplus adapter.zip` 和 `SHA256SUMS.txt`，在 PC 全新空目录（例如 `D:\D2-Fresh-Install`）解压。PowerShell 可校验：

Download the adapter ZIP and checksum from Releases, verify it, then extract into a new empty PC folder:

```powershell
Get-FileHash -Algorithm SHA256 '.\Diablo II for RGDSplus adapter.zip'
```

应为 / Expected:

```text
00c87b3fac6a2a541fa7c2d8937e0905494d81d8c602ed075f65490acf8a35c9
```

大小 / Size: `211,744,390 bytes`（RC49）。

## 2. 自备核心 / Supply the core

自行访问 [notaz 作者页面](https://repo.openpandora.org/?app=package.diablo2&page=detail)，获取固定的 [notaz standalone ARM core](https://notaz.gp2x.de/misc/starec/libd2game_sa_arm.exe.so.xz)。链接不表示本项目取得或转授其再分发许可。

Obtain the pinned standalone file separately from the upstream author. Linking upstream does not grant or transfer redistribution rights.

放入 / Place in:

```text
Ports/Diablo II for RGDSplus/engine-input/libd2game_sa_arm.exe.so.xz
```

保持 `.so.xz` 文件名，不需要解压；也可只放解压后的 `.so`，二者只能选一个。当前 Pandora PND r4 的地址布局不匹配，不可替代。压缩文件 SHA256：

Keep the full `.so.xz` filename. Alternatively supply only its decompressed `.so`; never both. The current Pandora PND r4 has an incompatible layout. Compressed file SHA256:

```text
b9a9b880f674571a8d9ca09d8604b173126e2651778eb23714064ba71332f103
```

## 3. 本地导入 / Import locally

双击 `Ports\Diablo II for RGDSplus\Import Game Assets.cmd`，输入自己的正版安装目录。不要单独复制 CMD；必须保留全部配套文件。导入器验证适配文件、内置中文补丁和核心，在独立暂存目录复制/重组资源、修正背包并生成前端缓存；源正版安装保持只读。成功提示为 `INSTALLATION READY`。失败时不要忽略错误或复制半成品到设备；本地日志仅供自己排查，不公开上传。

Run `Import Game Assets.cmd` and enter your lawful PC installation directory. Keep the CMD with all companion files. Import checks the adapter, the embedded Chinese patch and the core, prepares data in an isolated staging folder, applies the inventory correction and generates frontend caches. The source game installation is read-only. Wait for `INSTALLATION READY`. Do not deploy a failed/partial import or publicly upload its logs.

已有非空 `gamedata`、`private-assets`、存档、初始化 prefix 或已生成核心的目录会被拒绝；不要把此全新安装工具用于现有玩家目录。

Nonempty game/cache/save directories, an initialized prefix or a prepared core cause rejection. This fresh-install tool is not an in-place updater for an existing player installation.

## 4. 卡二与启动 / Card two and launch

退出设备游戏，备份旧 `.sh` 入口、完整同名目录、`saves/` 和 `prefix.ext4` 到 PC 并核对。安全移走旧同名安装，再把 PC 本地准备好的 `Ports` 合并到卡二根目录，避免 `Ports/Ports/`；保持至少 4 GiB 可用空间。安全弹出、插回设备，从固件 Ports 手动启动 **Diablo II for RGDSplus**。首次启动会生成 prefix。不要同时运行多个本项目实例。

Exit the game; back up the old launcher, whole installation, saves and prefix to PC and verify the backup. Move the old same-name installation aside, copy the locally prepared `Ports` into card two's root without nesting `Ports/Ports/`, and keep at least 4 GiB free. Eject safely, reinsert and manually launch **Diablo II for RGDSplus** from firmware Ports. First launch initializes the prefix. Do not run concurrent instances.

```text
Ports/
  Diablo II for RGDSplus.sh
  Diablo II for RGDSplus/
    launch.bash
    game-import/                  # import tools + embedded Chinese patch
    engine-input/                 # supplied locally / 玩家自备
    gamedata/                     # generated locally; never redistribute
    private-assets/               # game-derived cache; never redistribute
    libd2game_sa_arm.exe.so        # prepared locally; never redistribute
    saves/                        # personal; back up / 玩家数据
    prefix.ext4                   # created on first launch / 首次启动生成
```

## 使用与排查 / Use and troubleshooting

世界页面按 **X** 与附近 NPC、物品、交互物或副本入口进行原生交互，不依赖鼠标指针位置。**L3（左摇杆下压）切换走路/跑步**，耐力耗尽时按原生规则走路，动画继续正常循环。A/B 使用战斗技能，Y 打开地图。窗口面板保留原有操作。

In the world, **X** uses native interaction with nearby NPCs, items, objects and dungeon entrances, independently of the mouse pointer. **L3 toggles walk/run**; exhausted stamina falls back to native walking while animation keeps cycling. A/B use combat skills and Y opens the map. Window panels retain their existing controls.

触控异常时可断开充电/USB 后对照复测，但不能据此断言所有故障已解决。若卡只读或出现 FAT 错误，先停止游戏、保护最新存档并离线检查文件系统；不要强行继续写入。反馈版本、固件、供电/触摸条件与最小复现步骤，不上传资源或完整诊断。

If touch behaves unexpectedly, compare with charging/USB disconnected; that does not establish a universal fix. On read-only/FAT errors, stop, protect the latest saves and check the filesystem offline. Report version, firmware, power/touch conditions and minimal reproduction steps without game data or full diagnostics.

## 验收与源码限制 / Validation and source limitations

RC49 于 2026-10-26 经用户肉眼确认并授权发布；74 项本地测试和全新玩家导入通过：239 个包文件、12 个零售资源、12 张前端位图、固定核心及中文补丁哈希均通过。NPC 对话、L3、邪恶洞窟入口及耐力耗尽动画经独立实机测试。详见 [RC49 验证记录与原生补丁边界](RC49.md)。

RC49 was visually accepted and authorized for publication on 2026-10-26. All 74 local tests and fresh-player import checks passed: 239 package files, 12 retail resources, 12 frontend bitmaps and pinned core/Chinese-patch hashes. NPC dialogue, L3, the Den of Evil entrance and stamina-exhaustion animation were tested on an independent device copy. See the [RC49 validation and native patch boundaries](RC49.md). These checks do not exhaust all gameplay or firmware conditions.

`world_probe.so` 与 `indexed_gpu.so` 的完整精确源码及原始工具链未恢复；历史实验源码不代表它们。可用 `python tools/audit_public.py --archive "path/to/Diablo II for RGDSplus adapter.zip"` 检查固定产物。后续修改需要新 build ID 与相应验证，不能覆盖 RC41 并沿用旧验收结论。

The exact full sources/toolchain for `world_probe.so` and `indexed_gpu.so` were not recovered. Historical prototypes are not passed off as those sources. Use the audit command above for the pinned artifact; future changes require a new build ID and appropriate validation.

**导入后的目录仅限个人合法使用，禁止作为“免导入版”“内置游戏版”再次分发。The prepared installation is for lawful personal use; do not redistribute it as a ready-to-play or game-bundled package.**
