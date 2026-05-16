# StatTools 工作记忆

## 项目概述
- StatTools: 田间试验数据分析工具（Streamlit应用）
- 位置: d:\stat-tools
- 包含: 试验设计、方差分析、描述统计、回归分析等模块

## 2026-04-08 更新
### 新增四种试验设计类型

| 设计类型 | 函数名 | 说明 |
|---------|--------|------|
| Alpha设计 | alpha_lattice_design() | 不完全区组设计，v=s×k，适合品种区试 |
| Lattice设计 | lattice_design() | 格子设计，处理数为完全平方数 |
| 增广设计 | augmented_design() | 对照有重复，测试无重复，适合新品种筛选 |
| 对角线设计 | diagonal_design() | 对角线排列，控制土壤梯度 |

### Alpha设计关键参数
- v = 处理数
- s = 每个完整区组中的不完全区组数
- k = 每个不完全区组的大小
- 条件：s × k = v

### 对角线设计
- 也称diagonal design，用于控制田间单向/双向土壤梯度
- 之前被误称为"对接线设计"，已更正

## 技术要点
- Alpha设计和Lattice设计使用类似的不完全区组原理
- 增广设计结合RCBD框架，对照用于估计区组效应
- 对角线设计使处理沿对角线分布，穿越不同肥力水平

### 间比法/对比法（新增）
**间比法**：
- 排列：CK - 处理1 - ... - 处理N - CK
- 理论对照 = (左CK + 右CK) / 2
- 相对产量(%) = 处理产量 / 理论对照 × 100%
- 判断：>110% 可能显著优于对照

**对比法**：
- 排列：CK - 处理 - CK - 处理...
- 相对产量(%) = 处理产量 / 相邻CK × 100%

### 对应的方差分析方法
- Alpha/不完全区组：混合模型，区组为随机效应
- 增广设计：使用对照估计区组效应，校正测试处理产量
- 间比法/对比法：百分比法（非方差分析）

### 文件位置
- 试验设计：d:\stat-tools\pages\07_试验设计.py
- 方差分析：d:\stat-tools\pages\03_方差分析.py

## 2026-05-07 代码质量优化

### 统一延迟导入模块
- 新建 `utils/imports.py`，用 `st.cache_resource` 统一管理重量级库懒加载
- 消除 5 处重复的 `_get_statsmodels()` 定义（03/04/combining/ssr/trial_report）
- 修复 10_区试报告.py 中 5 处函数内直接导入（改用缓存版本）

### 修复 bare except
- 13 处 `except:` 全部改为 `except Exception:`
- 涉及 trial_report_analysis（8处）、01_描述统计、05_多变量分析、06_数据可视化、launch、stattools_launcher

### 合并 render_data_manager
- `render_data_manager()` 新增 `expanded` 参数统一控制展开/折叠
- `render_data_manager_expanded()` 改为委托调用，消除 ~250 行重复代码

## 2026-05-17 腾讯云服务器部署

### 服务器信息
- **IP**：43.156.131.60（腾讯云香港轻量，Ubuntu 22.04，2核2G）
- **SSH 私钥**：`C:\Users\phili\Downloads\autologonpass.pem`
- **用户名**：ubuntu（sudo 权限）
- **部署方式**：Docker + Nginx 反向代理

### 部署架构
```
用户 → Nginx(80) → Docker(127.0.0.1:8501) → Streamlit
```
- 代码路径：`/opt/stattools/`（git clone from GitHub）
- 数据持久化：`/opt/stattools-data/`（挂载到容器 `/app/data/`）
- 数据库：`/opt/stattools-data/billing.db`（SQLite，持久化）
- 日志：`/opt/stattools-logs/`（挂载到容器 `/app/logs/`）

### 关键配置
- Docker 镜像：`stattools:latest`，基于 `python:3.11-slim`
- `docker-entrypoint.sh`：启动前自动创建 billing.db 软链接 + 权限初始化
- billing.db 软链接：`/app/billing.db` → `/app/data/billing.db`（构建时创建）
- 管理员：13800138000 / admin123
- 域名：申请中，就位后用 certbot 加 HTTPS

### 已解决的关键问题
- **SQLite WAL 权限**：`/app/` 目录需可写（chmod 777），否则 `PRAGMA journal_mode=WAL` 失败
- **billing.db 持久化**：存入 `/app/data/`（挂载卷），通过软链接访问
- **容器重启稳定性**：symlink 在 Docker 构建时创建，配合 entrypoint 脚本兜底

### 更新命令备忘
```bash
# 服务器上更新代码 + 重建
cd /opt/stattools && git pull origin main && sudo docker build -t stattools:latest . && sudo docker rm -f stattools && sudo docker run -d --name stattools --restart=always -p 127.0.0.1:8501:8501 -v /opt/stattools-data:/app/data -v /opt/stattools-logs:/app/logs -u $(id -u ubuntu):$(id -g ubuntu) stattools:latest
```

### 域名字段就位后
```bash
sudo certbot --nginx -d your-domain.com
# 自动获取 SSL 证书，Nginx 配置自动更新
```

## 2026-05-09/10 启动脚本 & UI 修复

### 桌面临一键启动脚本
- `gen_launcher.py` 生成 `C:\Users\phili\Desktop\StatTools启动.bat`
- 流程：清理残留 → 新窗口启动 Streamlit(8501) → netstat 检测端口 → ngrok http 8501
- **编码坑**：.bat 文件必须用系统默认编码（GBK）写入，UTF-8 BOM 会导致 cmd 解析首行失败
- 标签必须用单冒号 `:`（双冒号 `::` 是注释，goto 跳不过去）

### 侧边栏导航分隔线
- 恢复扁平 `pages` 列表 + 重写 `inject_nav_separator()`（MutationObserver 版）
- 移除 `utils/visitor_logger.py` 中访问统计上方的 `---` 分割线
