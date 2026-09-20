from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.carton import Carton, CartonItem
from app.models.flush_harvest import FlushHarvest
from app.models.room import Room
from app.models.shed import Shed
from app.models.user import User
from app.schemas.carton import CartonCreateSchema, CartonItemAddSchema, CartonOutSchema
from app.utils import validation_error_response

bp = Blueprint("cartons", __name__, url_prefix="/api/cartons")

create_schema = CartonCreateSchema()
item_add_schema = CartonItemAddSchema()
out_schema = CartonOutSchema()


def _current_user(db):
    username = get_jwt_identity()
    return db.query(User).filter(User.username == username).first()


def _serialize(carton: Carton) -> dict:
    total = sum(item.harvest.weight_kg for item in carton.items)
    return out_schema.dump(
        {
            "id": carton.id,
            "shed_id": carton.shed_id,
            "carton_no": carton.carton_no,
            "sealed_at": carton.sealed_at,
            "items": [
                {
                    "id": item.id,
                    "harvest_id": item.harvest.id,
                    "room_id": item.harvest.room_id,
                    "harvested_at": item.harvest.harvested_at,
                    "flush_no": item.harvest.flush_no,
                    "weight_kg": item.harvest.weight_kg,
                    "grade": item.harvest.grade,
                    "operator_name": item.harvest.operator_name,
                }
                for item in carton.items
            ],
            "total_kg": round(total, 3),
        }
    )


@bp.get("")
@jwt_required()
def list_cartons():
    db = SessionLocal()
    try:
        shed_id = request.args.get("shedId", type=int)
        q = db.query(Carton)
        if shed_id is not None:
            q = q.filter(Carton.shed_id == shed_id)
        cartons = q.order_by(Carton.shed_id, Carton.id).all()
        return jsonify([_serialize(c) for c in cartons])
    finally:
        db.close()


@bp.post("")
@jwt_required()
def create_carton():
    db = SessionLocal()
    try:
        try:
            data = create_schema.load(request.get_json(silent=True) or {})
        except ValidationError as err:
            return validation_error_response(err)
        shed = db.query(Shed).filter(Shed.id == data["shed_id"]).first()
        if not shed:
            return jsonify({"detail": "菇房不存在"}), 400
        existing = (
            db.query(Carton)
            .filter(Carton.shed_id == data["shed_id"], Carton.carton_no == data["carton_no"])
            .first()
        )
        if existing:
            return (
                jsonify({"detail": "该菇房下箱号已存在", "cartonId": existing.id}),
                409,
            )
        carton = Carton(shed_id=data["shed_id"], carton_no=data["carton_no"])
        db.add(carton)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            clash = (
                db.query(Carton)
                .filter(
                    Carton.shed_id == data["shed_id"], Carton.carton_no == data["carton_no"]
                )
                .first()
            )
            payload = {"detail": "该菇房下箱号已存在"}
            if clash:
                payload["cartonId"] = clash.id
            return jsonify(payload), 409
        db.refresh(carton)
        return jsonify(_serialize(carton)), 201
    finally:
        db.close()


@bp.get("/reconcile")
@jwt_required()
def reconcile():
    db = SessionLocal()
    try:
        # 箱侧：按箱所属棚汇总箱数与公斤（Carton.shed_id 归属）
        carton_rows = (
            db.query(
                Carton.shed_id.label("shed_id"),
                func.count(func.distinct(Carton.id)).label("carton_count"),
                func.coalesce(func.sum(FlushHarvest.weight_kg), 0.0).label("total_kg"),
            )
            .outerjoin(CartonItem, CartonItem.carton_id == Carton.id)
            .outerjoin(FlushHarvest, FlushHarvest.id == CartonItem.harvest_id)
            .group_by(Carton.shed_id)
            .all()
        )
        by_carton = {
            r.shed_id: (int(r.carton_count), float(r.total_kg)) for r in carton_rows
        }

        # 明细侧：按潮次所属室的棚，对箱内条目求和
        detail_rows = (
            db.query(
                Room.shed_id.label("shed_id"),
                func.coalesce(func.sum(FlushHarvest.weight_kg), 0.0).label("detail_kg"),
            )
            .select_from(CartonItem)
            .join(FlushHarvest, FlushHarvest.id == CartonItem.harvest_id)
            .join(Room, Room.id == FlushHarvest.room_id)
            .group_by(Room.shed_id)
            .all()
        )
        by_detail = {r.shed_id: float(r.detail_kg) for r in detail_rows}

        sheds = db.query(Shed).order_by(Shed.id).all()
        by_shed = []
        for shed in sheds:
            carton_count, carton_kg = by_carton.get(shed.id, (0, 0.0))
            detail_kg = by_detail.get(shed.id, 0.0)
            if abs(carton_kg - detail_kg) > 0.001:  # 双路求和必须对得上
                return (
                    jsonify(
                        {
                            "detail": "拼箱汇总与明细求和不一致",
                            "shedId": shed.id,
                            "differenceKg": round(abs(carton_kg - detail_kg), 6),
                        }
                    ),
                    409,
                )
            by_shed.append(
                {
                    "shedId": shed.id,
                    "shedName": shed.name,
                    "cartonCount": carton_count,
                    "totalKg": round(carton_kg, 3),
                }
            )
        return jsonify({"byShed": by_shed})
    finally:
        db.close()


@bp.get("/<int:carton_id>")
@jwt_required()
def get_carton(carton_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        return jsonify(_serialize(carton))
    finally:
        db.close()


@bp.post("/<int:carton_id>/items")
@jwt_required()
def add_item(carton_id: int):
    db = SessionLocal()
    try:
        try:
            data = item_add_schema.load(request.get_json(silent=True) or {})
        except ValidationError as err:
            return validation_error_response(err)
        carton = db.query(Carton).filter(Carton.id == carton_id).with_for_update().first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return jsonify({"detail": "纸箱已封箱，不能再加入潮次", "cartonId": carton.id}), 409

        harvest = (
            db.query(FlushHarvest)
            .filter(FlushHarvest.id == data["harvest_id"])
            .with_for_update()
            .first()
        )
        if not harvest:
            return jsonify({"detail": "采收记录不存在"}), 404

        room = db.query(Room).filter(Room.id == harvest.room_id).first()
        if room.shed_id != carton.shed_id:
            return (
                jsonify({"detail": "该潮次的出菇室不属于这只箱所在的菇房，不能串棚拼箱"}),
                409,
            )

        existing_item = (
            db.query(CartonItem).filter(CartonItem.harvest_id == harvest.id).first()
        )
        if existing_item:
            return (
                jsonify(
                    {
                        "detail": "该潮次已在一只箱中，一笔潮次只能待在一只未封箱里",
                        "cartonId": existing_item.carton_id,
                    }
                ),
                409,
            )

        item = CartonItem(carton_id=carton.id, harvest_id=harvest.id)
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            clash = (
                db.query(CartonItem).filter(CartonItem.harvest_id == harvest.id).first()
            )
            payload = {
                "detail": "该潮次已在一只箱中，一笔潮次只能待在一只未封箱里",
            }
            if clash:
                payload["cartonId"] = clash.carton_id
            return jsonify(payload), 409
        db.refresh(carton)
        return jsonify(_serialize(carton)), 201
    finally:
        db.close()


@bp.delete("/<int:carton_id>/items/<int:item_id>")
@jwt_required()
def remove_item(carton_id: int, item_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return jsonify({"detail": "纸箱已封箱，不能移出潮次", "cartonId": carton.id}), 409
        item = (
            db.query(CartonItem)
            .filter(CartonItem.id == item_id, CartonItem.carton_id == carton_id)
            .first()
        )
        if not item:
            return jsonify({"detail": "箱内条目不存在"}), 404
        db.delete(item)
        db.commit()
        db.refresh(carton)
        return jsonify(_serialize(carton))
    finally:
        db.close()


@bp.post("/<int:carton_id>/seal")
@jwt_required()
def seal_carton(carton_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).with_for_update().first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return jsonify({"detail": "纸箱已封箱", "cartonId": carton.id}), 409
        total = sum(item.harvest.weight_kg for item in carton.items)
        if len(carton.items) < 2 or total <= 0:
            return (
                jsonify(
                    {
                        "detail": "至少两笔潮次且重量合计大于 0 才可封箱",
                        "cartonId": carton.id,
                        "itemCount": len(carton.items),
                        "totalKg": round(total, 3),
                    }
                ),
                409,
            )
        carton.sealed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(carton)
        return jsonify(_serialize(carton))
    finally:
        db.close()


@bp.post("/<int:carton_id>/unseal")
@jwt_required()
def unseal_carton(carton_id: int):
    db = SessionLocal()
    try:
        user = _current_user(db)
        if not user or user.role != "admin":
            return jsonify({"detail": "仅管理员可拆封纸箱"}), 403
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        # 拆封不清空条目，只解除封箱状态，之后可把条目改挂到别的未封箱
        carton.sealed_at = None
        db.commit()
        db.refresh(carton)
        return jsonify(_serialize(carton))
    finally:
        db.close()
