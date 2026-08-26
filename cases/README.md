# 案例库（cases/）

本目录是开源版的「截图格式库」——你每次运行 `recognize`，
会自动在这里累积一条识别样本（OCR 文本布局 + 解析出的名字，**不存原图**，保护隐私）。

**案例库越肥 → 识别越准**（尤其形近字、新名字、新截图布局）。

## 怎么让作者的中心案例库也更新（喂护城河）
运行：
```
python attendance.py cases --export cases_YYYYMMDD.zip
```
把生成的 zip 发给作者（GitHub: sque-h），作者会合并进全联盟共享案例库，
并在完整版 / 管家中为你提供更准的识别。

## 查看统计
```
python attendance.py cases --stats
```
