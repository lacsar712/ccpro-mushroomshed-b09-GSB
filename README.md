# MushroomShed-01 · 菇房出菇台账

食用菌菇房「出菇室环境记录与采收台账」种子项目（非库存 / 电商 / 医院 / 考勤）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11 · Flask · SQLAlchemy 2 · Marshmallow · Flask-JWT-Extended · passlib(bcrypt) · gunicorn |
| 前端 | SolidJS · Vite · TypeScript · @solidjs/router |
| 数据库 | MySQL 8（协议兼容原 MariaDB 设计） |
| 部署 | docker-compose · 前端 Nginx 反代 `/api` |

## 端口与账号

| 服务 | 端口 |
| --- | --- |
| 前端 | **3800** |
| 后端 API | **8800** |
| MySQL | **3310** |

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | admin（场长） |
| `fruiter` | `123456` | fruiter（出菇员） |

数据库：`mushroomshed` / `mushroomshed`，库名 `mushroomshed`。JWT 密钥环境变量 **`JWT_SECRET`**。

## 一键启动

```bash
cd MushroomShed-01
docker compose up --build
```

启动后访问：

- 前端：http://localhost:3800
- 后端健康检查：http://localhost:8800/api/health

后端 entrypoint 流程：等待 MySQL 就绪 → `create_all` 建表 → seed 初始数据 → 启动 gunicorn。

## 功能模块

1. **Auth**：JWT 登录（OAuth2 表单或 JSON），`/api/auth/login`、`/api/auth/me`，`Authorization: Bearer`
2. **Shed 菇房**：`name`、`location`、`notes`
3. **Room 出菇室**：`shedId`、`roomCode`、`species`、`capacityBags`、`status(fruiting|idle|sanitize)`；同菇房 `roomCode` 唯一
4. **ClimateLog 环境记录**：`roomId`、`recordedAt`、`tempC`、`humidityPct`、`co2Ppm`、`notes`；`humidityPct ∈ [1,100]`，否则 **400**
5. **FlushHarvest 采收**：`roomId`、`harvestedAt`、`flushNo(≥1)`、`weightKg`、`grade(A|B|C)`、`operatorName`；`weightKg > 0`，否则 **400**
6. **Carton 拼箱**：把多笔 FlushHarvest 收进同一只纸箱
   - 字段：`cartonNo`、`shedId`、`sealedAt`（可空）；`cartonNo` 仅在**同一 `shedId` 下唯一**，两棚撞号不串棚，归属只认 `shedId`
   - `POST /api/cartons` 建箱（重复箱号 **409** 并带回 `cartonId`）；`GET /api/cartons?shedId=` 列表
   - `POST /api/cartons/:id/items`（正文 `harvestId`）：该潮次的室必须属于这只棚，否则 **409**；一笔潮次只能待在一只箱里，重复加入 **409** 并带回所在 `cartonId`
   - `DELETE /api/cartons/:id/items/:itemId` 移出条目
   - `POST /api/cartons/:id/seal` 封箱：**封箱时箱内至少两笔潮次、且 `weightKg` 合计大于 0，否则 409 且 `sealedAt` 仍为空**；封箱后不准再加入或移出
   - `POST /api/cartons/:id/unseal` 拆封：**仅 admin**（其他角色 403）；拆封不清空条目，但允许把其中一笔移出后改挂到另一只未封箱
   - `GET /api/cartons/:id` 给出 `items` 与 `totalKg`
   - `GET /api/cartons/reconcile` 给出 `byShed` 的箱数与公斤，箱侧汇总与明细求和双路核对，差不超过 **0.001**
   - 已拼入箱的潮次不能直接删除，需先移出（**409**，带回 `cartonId`）
7. **Dashboard**：`shedTotal`、`fruitingRoomCount`、`climateLast24h`、`harvestKgLast7d`

各实体 API：`GET/POST` 列表与创建、`DELETE` 按 ID 删除。拼箱另有封箱 / 拆封 / 条目加移 / reconcile 端点。

## 前端页面

Login · Dashboard · Sheds · Rooms · ClimateLogs · FlushHarvests（侧边栏布局）。在**菇房页**点「拼箱」进入该棚的拼箱页（`/sheds/:shedId/cartons`）：建箱、加入本棚潮次、移出、封箱（**至少两笔才可封**）、admin 拆封，并展示 byShed 对账汇总；接口失败时原文展示。

## 本地开发（可选）

```bash
# 数据库（或用 compose 只起 db）
docker compose up -d db

# 后端
cd backend
pip install -r requirements.txt
set DATABASE_URL=mysql+pymysql://mushroomshed:mushroomshed@localhost:3310/mushroomshed
set JWT_SECRET=local-dev-secret
python -c "from app.database import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
python -c "from app.seed import seed; seed()"
gunicorn wsgi:app --bind 0.0.0.0:8800 --reload

# 前端
cd frontend
npm install
npm run dev
```

## 目录结构

```
MushroomShed-01/
├── docker-compose.yml
├── README.md
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── requirements.txt
│   ├── wsgi.py
│   └── app/
│       ├── __init__.py
│       ├── config.py
│       ├── database.py
│       ├── auth.py
│       ├── seed.py
│       ├── utils.py
│       ├── models/
│       ├── schemas/
│       └── routes/
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── pages/
        ├── components/
        └── api/
```
