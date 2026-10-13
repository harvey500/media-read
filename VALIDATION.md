# Validation / 验证记录

## 中文

版本：公开试用 v0.1。验证日期：2026-10-13。

### 工具测试

在 Windows、Python 3.12.6、Pillow 12.3.0、PyAV 19.0.1 的独立环境运行 13 项 unittest，全部通过。覆盖：

- 图片源文件不修改及裁剪像素保持。
- EXIF 方向校正、透明裁剪与声明概览背景。
- 已有输出不覆盖、无效裁剪区域拒绝。
- 可变帧率的实际 PTS、非零流起点归一、显示旋转。
- 同帧多个目标去重、解码预算与未满足目标报告。
- 音轨只列信息，不声称已分析。
- 无效时间与帧数拒绝、次级媒体资源拒绝。

Skill 格式、YAML、资源引用与发布文件检查通过。这些检查不等于完整安全审计或所有格式兼容性保证。

### 独立试用

使用自行生成的合成诊断图片与 6 秒无音轨录屏。独立 agent 获得 skill 与原始媒体，没有预期答案或生成脚本；实际查看全图、原尺寸裁剪和带时间戳的帧。

图片中正确核对 WinError 10054 与 -0.05 ms 的负号、单位。视频初始半秒抽样漏掉短暂错误，追加错位抽样与局部核验后，在 3.3 和 3.4 秒样本看到 E409；以相邻样本给出出现、消失区间，没有冒充精确开始时间。

其报告区分 UI 成功提示与真实保存状态，说明所看样本的设置字段未变；没有把抽样变成连续观看结论，也没有编造语音内容。共查看 38 个时间点，其中 7 帧另外核对原尺寸。

### 未验证与限制

只有一轮合成媒体试用，不证明相对普通读图的准确率提升，也不是跨模型、跨 agent、长视频、复杂动作、HDR 或真实语音评测。尚未在 Linux/macOS 运行测试。抽帧可以漏检；没有内置 OCR、ASR、自动场景检测或硬性进程终止。解码器异常、反射/切变、特殊色彩或非方形像素仍需专门处理。

公开仓库不包含测试媒体、私人输入、模型服务日志或本机环境，只包含可重复运行的工具测试。Pillow、PyAV 和 FFmpeg 是外部依赖，保留各自的许可条款；本仓库 MIT 许可只覆盖本仓库原创材料。

## English

Public trial v0.1, checked on 2026-10-13. Thirteen unittest cases passed on Windows with Python 3.12.6, Pillow 12.3.0 and PyAV 19.0.1. They cover source integrity, native crop pixels, EXIF orientation, alpha handling, overwrite protection, invalid crops and targets, actual variable-rate PTS, nonzero stream origin, display rotation, sample deduplication, decode limits, audio inventory and secondary-resource rejection.

One independent-agent trial used an author-generated screenshot and silent six-second clip without expected answers or the generator. It verified WinError 10054 and the signed value -0.05 ms, and located a brief E409 after an initial overview missed it. It inspected 38 timestamped samples, seven also at native size, and reported temporal brackets, sparse coverage and audio limits rather than claiming continuous viewing or persisted backend state.

This is not a comparative accuracy benchmark or broad model, host, format, long-video, action, HDR or speech evaluation. Linux/macOS tests have not been run. Sparse samples can miss events. No OCR, ASR, scene detector or hard process-kill mechanism is bundled. External Pillow/PyAV/FFmpeg licenses remain applicable; this repository's MIT license covers its original material. Media fixtures, private inputs and local runtime state are not published.
