# 拉格朗日考勤 · 开源版

《无尽的拉格朗日》联盟考勤的**开源免费工具**。纯本地识别，不碰游戏数据，零封号风险。

## 功能

- 纯本地 OCR 识别玩家名（RapidOCR，零密钥、离线运行）
- 单格式支持：纯名字考勤截图 → 输出「谁来了谁没来」
- 输出 CSV + 一张本地表（xlsx）
- 案例库自动累积（越用越准，可导出分享）

## 安装

需要 Python 3.9+。

```bash
cd lagrange-attendance-open
pip install -r requirements.txt
```

（RapidOCR 模型首次运行会自动下载一次，之后离线可用。）

## 用法

### 1. 识别一张考勤截图（谁来了谁没来）

准备一张「纯名字考勤截图」（纵向排列一堆玩家名、没有数字列的那类），运行：

```bash
python attendance.py recognize 你的截图.png
```

会生成：
- `attendance_YYYY-MM-DD.csv` —— 玩家名 / 小队 / 状态(到场·未到场·疑似) / OCR文本 / 相似度
- `attendance_YYYY-MM-DD.xlsx` —— 同一内容的本地表
- 自动往 `cases/` 累积一条案例（用于持续改进识别准确率）

用自己的名册替换 `roster.csv`（只留「玩家名,小队」两列，不要繁荣度列）。

### 2. 案例库（越肥越准）

```bash
python attendance.py cases --stats          # 查看本地累积样本数
python attendance.py cases --export case.zip # 导出匿名案例包
```

把 `case.zip` 分享给作者或社区（GitHub: sque-h），一起把共享案例库做得更准，识别也会随之提升。

## 许可证

**个人非商用免费**，商用/转售需作者书面授权。详见 [LICENSE](LICENSE)。

## 反馈与贡献

欢迎提 Issue / PR，或分享案例库一起改进识别。

作者：侯宇飞（GitHub: sque-h）
