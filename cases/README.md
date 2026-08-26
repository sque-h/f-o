# 案例库（cases/）

本目录是开源版的「截图格式库」——你每次运行 `recognize`，
会自动在这里累积一条识别样本（OCR 文本布局 + 解析出的名字，**不存原图**，保护隐私）。

**案例库越肥 → 识别越准**（尤其形近字、新名字、新截图布局）。

## 怎么共享你的案例库（一起把识别做得更准）
运行：
```
python attendance.py cases --export cases_YYYYMMDD.zip
```
把生成的 zip 分享给作者或社区（GitHub: sque-h），一起把共享案例库做得更准，
识别也会随之提升。

## 查看统计
```
python attendance.py cases --stats
```
