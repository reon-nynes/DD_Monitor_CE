# 验证指南

所有命令均从仓库根目录执行。默认入口只运行仓库检查，不遍历所有专项脚本。

日常功能和人工验收统一使用根目录 `run.cmd`。特殊项目可隔离测试，完成后必须集成回根目录并在该入口复测；自动回归仍使用合成数据、临时配置和离屏窗口。开发入口与冻结包统一使用 PySide6 6.11.2。

## 执行分类

| 套件 | 依赖与行为 | 命令 |
| --- | --- | --- |
| `repository` | Python 标准库和 Git；不导入 Qt，不读取账号，不联网 | `python dev/run_checks.py` |
| `smoke` | 开发依赖和 libmpv；离屏核心功能检查，使用合成数据与本机服务 | `python dev/run_checks.py --suite smoke --timeout 120` |
| `offline` | 开发依赖；离屏 Qt、替身接口或本机 HTTP/WebSocket 服务，不访问真实直播 | `python dev/run_checks.py --suite offline` |
| `native` | Windows、开发依赖、libmpv；部分项目需 FFmpeg，会创建原生窗口 | `python dev/run_checks.py --suite native` |
| `live` | Windows、运行库和网络；显式指定公开开播房间，只读接收 | 使用下方单项命令 |

`offline` 是已核对隔离条件的回归子集，`native` 也是明确列出的原生检查子集；均不表示仓库全部相关测试。其余历史脚本按功能列入[完整索引](../../dev/checks/README.md)，需要先检查脚本依赖、测试数据和隔离条件，再单独运行或加入套件。不能根据文件名中的 `live` 判断它是否使用真实网络。

离屏进程会阻止 Python 层的外部 DNS 查询和 socket 连接，只允许回环地址；即使脚本捕获该异常，最终结果仍失败。Qt WebEngine、原生库和子进程仍需逐项审查。套件脚本不能使用 `os._exit` 绕过清理；具体纳入标准与本机归档见[工作区维护](workspace-maintenance.md)。

## 单项与真实直播

```powershell
python dev/run_checks.py --list
python dev/run_checks.py --script selfcheck_preview_scroll
python dev/run_checks.py --script selfcheck_plugin_controls
python dev/run_checks.py --script check_live_restore -- 6
python dev/run_checks.py --script check_live_danmaku_motion -- --room 6 --backend animator
```

房间 `6` 仅为命令示例，执行前确认目标正在开播。真实直播检查必须显式选择单项并传入参数，不能隐式批量执行；以上两项不加载个人登录配置、不发送真实弹幕。

Windows 也可将 `python dev/run_checks.py` 换为 `dev\run-checks.cmd`。入口使用当前 Python 的解释器执行子进程，设置 `DDM_NO_SAVE=1`；离屏与原生图形后端按分类选择。每个脚本的退出码和异常保留在日志中；Windows 引导保持 MTA 资源至 Qt 清理结束。

## 结果与新增检查

原生视频浮层的内存回归：

```powershell
python dev/run_checks.py --script selfcheck_badge_memory
```

使用真实 Windows 原生徽标和左右圆角窗口，在深浅主题下完成 2,400 次 alpha 上传，
确认上传成功且 GC 后保留的 Python 内存低于 512 KiB。窗口在屏幕外创建，
不打开媒体、不加载插件或账号配置；此检查用于捕获反复重绘时创建 ctypes 类型导致的持续积累。

- 日志与 `summary.json` 写入忽略目录 `work/checks/<时间>/`。
- 所有选中项目完成后，任一失败或超时均返回退出码 `1`；参数错误返回 `2`，全部通过返回 `0`。
- 单项默认超时 300 秒，可用 `--timeout` 调整。遇到失败先查看对应日志，不以“执行结束”判断通过。
- 新增脚本先更新完整索引；核对真实配置、网络、窗口和依赖后，才将其加入 `dev/checks/suites.json`。
- 涉及发弹幕的自动回归使用替身或本机服务。真实账号、跨屏操作、声音听感等需要独立人工验收。
- CI 分别运行 `repository` 和 `smoke`，并编译应用源码。smoke 覆盖设置、通知、布局、关注排序、弹幕发送和插件接口；它不代表原生播放、视觉帧率和真实直播验收全部通过。
- smoke 与 offline 可共享脚本，但必须保持相同隔离模式；同一套件不允许重复脚本。新增 smoke 项目应先核对隔离条件、耗时和依赖，不把所有历史脚本直接纳入 CI。

## 工具与历史记录

性能测量见[性能工具](../../dev/benchmarks/README.md)，资源生成见[辅助工具](../../dev/tools/README.md)。发布构建入口继续使用 `dev/build_release.ps1`。

PR 测试和整理过程的历史记录位于 [archive/](../archive/README.md)，版本说明位于 [releases/](../releases/RELEASE-v0.4.md)。

## 账号菜单再次登录

```powershell
python dev/run_checks.py --script selfcheck_account_login_reopen --timeout 45
```

此原生检查使用真实 `QMenu.exec`、鼠标点击和平台登录窗口，在展开与收起侧栏各重复打开、取消两次；断言登录入口在菜单和鼠标回调返回后才执行。只使用合成账号与 `about:blank` 页面，禁用宿主轮询、启动更新和插件检查，不读取真实账号。外部进程超时也覆盖原生事件循环卡死。

## B 站自动追帧

```powershell
python dev/run_checks.py --script selfcheck_bili_catchup
python dev/run_checks.py --script selfcheck_bili_catchup_native --timeout 60
python dev/run_checks.py --script check_bili_catchup_live -- 1900545280
```

第一项使用播放器属性替身及真实 Qt 定时器，覆盖缓冲阶梯、异常读数、暂停/恢复、
缓冲/跳转/结束状态、跨通道换流、预览和释放后的回调；不打开媒体、不读取账号。
第二项需要 FFmpeg 与 libmpv，通过本机 HTTP 服务先返回仅音频 FLV，再提供备用的合成视频流，
验证取流拒绝纯音频响应；使用真实 D3D11 窗口、视频解码参数和截图检查实际画面，
再验证约 4 秒积压被消化至目标后恢复 1 倍速。
使用非零起始时间戳，且测试结束前持续供流，无真实直播请求，播放保持静音。
第三项仅在显式指定公开开播房间时运行，验证真实解码帧前进及窗口截图；
不读取真实账号或发送弹幕，截图与读数保存在忽略目录 `work/bili-catchup-live-<房间号>.*`。

追帧仅对 B 站 `app`/`web` 及其 HLS 编码通道的 HTTP(S) 主播放器自动启用，
每 300 毫秒检查一次 `demuxer-cache-state.cache-end - time-pos`。
缓冲超过 1.5、2.5、3.5 秒时分别使用 1.1、1.2、1.3 倍速；
回到 1.5 秒及以下时恢复正常速度。暂停、缓冲、跳转、结束、读数缺失和换流也恢复正常速度。
低缓冲时使用正常速度，由 libmpv 的缓冲机制处理；不采用原脚本最低 0.1 倍的自动减速。
预览、其他平台和本地文件不启用；这版没有新增设置项或强制跳帧。
本功能位于核心播放器，既有插件控件、账号与弹幕交互接口保持原有职责。
FLV 探测会读取完整文件头并拒绝不含视频的响应；App/Web FLV 均不可用时尝试同编码的
原生 HLS 通道，保留接口返回的画质与请求头。有声音、黑色占位窗口已创建但没有
`video-params` 时，不上报视频播放成功或启用追帧，超时沿用现有错误重连流程。

这些读数是本机已接收的前向缓冲估计，属性语义见 [mpv 手册](https://mpv.io/manual/stable/)；
1.5 秒是目标缓冲长度，不代表主播到观众的端到端延迟。
主播推流、转码、CDN 和 HLS 分片产生的上游延迟无法由本机倍速追帧消除。
真实 B 站 FLV/HLS 的延迟改善、弱网稳定性、多窗负载和加速期间的音频听感仍需人工实播验收。
