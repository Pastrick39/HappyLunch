# HappyLunch

HappyLunch 是一个基于 FastAPI 和 Vue 3 的订餐管理小工具，提供订餐、查询、取消、修改订单以及飞书登录能力。后端通过 SQL Server 保存和读取订餐数据，前端页面由 `index.html` 与 `static/` 目录下的静态资源提供。

## 功能

- 提交订餐信息
- 查询订餐记录
- 取消订餐
- 修改订餐信息
- 飞书 OAuth 登录并识别当前操作人
- 按订餐、取消、修改截止时间限制当天操作
- 支持代订/代取消/代修改时发送邮件通知

## 项目结构

```text
.
|-- main.py              # FastAPI 应用入口与接口路由
|-- functions.py         # 订餐业务逻辑、飞书登录、通知逻辑
|-- DBtools.py           # 数据库与通用工具函数
|-- index.html           # 前端入口页面
|-- static/
|   |-- css/app.css      # 前端样式
|   |-- js/app.js        # Vue 前端逻辑
|   `-- hamburger.png    # 静态图片
`-- requirements.txt     # Python 依赖
```

## 环境要求

- Python 3.13 或兼容版本
- 可访问项目配置的 SQL Server 数据库
- 如需使用浏览器自动化相关工具函数，需要本机安装 Chrome

## 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 配置

项目支持通过环境变量覆盖飞书配置：

```powershell
$env:FEISHU_APP_ID="你的飞书 App ID"
$env:FEISHU_APP_SECRET="你的飞书 App Secret"
$env:FEISHU_REDIRECT_URI="http://你的域名或IP:8000/feishu/callback"
```

注意：数据库连接信息当前写在 `DBtools.py` 中，部署到生产环境前建议改为从环境变量或配置文件读取，避免账号密码直接出现在代码里。

## 启动服务

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000
```

也可以直接运行：

```powershell
python main.py
```

启动后访问：

```text
http://127.0.0.1:8000/
```

## 主要接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/` | 返回前端页面 |
| `GET` | `/feishu/login` | 发起飞书登录 |
| `GET` | `/feishu/callback` | 飞书登录回调 |
| `POST` | `/submit_order` | 提交订餐 |
| `GET` | `/check_order` | 查询订餐 |
| `POST` | `/delete_order` | 取消订餐 |
| `POST` | `/update_order` | 修改订餐 |

## 运行提示

- 前端默认请求当前站点地址；如果直接用本地文件方式打开页面，会默认请求 `http://127.0.0.1:8000`。
- 订餐人姓名字段最长 5 个字符，操作人字段最长 43 个字符。
- 代码中的部分业务文案和枚举值依赖现有数据库内容，修改餐别、形式等字段时需要同步检查前后端与数据库。
