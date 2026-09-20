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
6. **Dashboard**：`shedTotal`、`fruitingRoomCount`、`climateLast24h`、`harvestKgLast7d`
7. **Carton 拼箱**：把多笔 FlushHarvest 收进一只纸箱（不提供 CSV、不提供对账下载）
   - 字段：`cartonNo`、`shedId`、`sealedAt`（未封箱为 `null`）；`cartonNo` 仅在同一 `shedId` 下唯一，两棚撞号不串棚，归属只认 `shedId`
   - `POST /api/sheds/:shedId/cartons` 建未封箱；同棚撞号 **409**
   - `POST /api/cartons/:id/items`（正文 `{harvestId}`）：潮次所属出菇室必须属于本棚，跨棚 **409**；一笔潮次只能待在一只未封箱里，重复拼入 **409** 并在响应体带回 `cartonId`
   - `DELETE /api/cartons/:id/items/:harvestId` 移出潮次
   - `POST /api/cartons/:id/seal` 封箱：**箱内至少两笔潮次才可封**，且 `weightKg` 合计须大于 0，否则 **409** 且 `sealedAt` 仍为空；封箱后不得再加入或移出
   - `POST /api/cartons/:id/unseal` 拆封仅限 **admin**（**403** for 其他角色）；拆封不清空条目，但允许把其中一笔改挂到另一只未封箱（移出后加入另一只未封箱）
   - `GET /api/cartons/:id` 返回 `items` 与 `totalKg`
   - `GET /api/cartons/reconcile` 返回 `byShed`（每棚箱数、按箱合计 kg、明细直接求和 kg、差额）与总计；明细求和与箱合计之差不超过 **0.001**（`balanced` 标志）
   - 已拼入纸箱的潮次不能直接删除，须先移出，否则 **409**

各实体 API：`GET/POST` 列表与创建、`DELETE` 按 ID 删除。

## 前端页面

Login · Dashboard · Sheds · Rooms · ClimateLogs · FlushHarvests · **棚页「拼箱」入口 → Cartons 拼箱页**（建箱 / 加入 / 移出 / 改挂 / 封箱 / admin 拆封 / reconcile 汇总；接口失败时原文展示；至少两笔潮次才可封箱）

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
