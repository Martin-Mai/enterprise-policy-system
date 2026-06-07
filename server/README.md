# 企业知识库 - 用户认证与 RBAC 权限系统

基于 FastAPI 的后端服务，提供用户注册、登录、JWT 认证和基于角色的访问控制（RBAC）。

## 技术栈

- **FastAPI** - 高性能 Web 框架
- **SQLAlchemy** - ORM 框架（同步引擎）
- **PyMySQL** - MySQL 驱动
- **python-jose** - JWT 令牌处理
- **passlib + bcrypt** - 密码哈希
- **python-dotenv** - 环境变量管理

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`，并根据实际情况修改。

### 3. 确保 MySQL 数据库已创建

```sql
CREATE DATABASE IF NOT EXISTS enterprise_kb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload
```

服务启动后访问：
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/

## API 接口

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/auth/register | 用户注册 | 无 |
| POST | /api/auth/login | 用户登录 | 无 |
| GET | /api/auth/me | 获取当前用户信息 | Bearer Token |
| GET | /api/admin/users | 获取所有用户列表 | Bearer Token（admin） |

## 项目结构

```
server/
├── app/
│   ├── api/
│   │   ├── auth.py          认证路由
│   │   ├── admin.py         管理员路由
│   │   └── deps.py          依赖注入（权限校验）
│   ├── core/
│   │   ├── config.py        全局配置
│   │   ├── database.py      数据库连接
│   │   └── security.py      密码哈希与 JWT
│   ├── models/
│   │   └── user.py          用户 ORM 模型
│   ├── schemas/
│   │   └── user.py          Pydantic 模型
│   └── main.py              应用入口
├── requirements.txt
├── .env.example
└── README.md
```
