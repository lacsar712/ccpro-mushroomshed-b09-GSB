from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from marshmallow import ValidationError
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.carton import Carton
from app.models.carton_item import CartonItem
from app.models.flush_harvest import FlushHarvest
from app.models.room import Room
from app.models.shed import Shed
from app.models.user import User
from app.schemas.carton import CartonCreateSchema, CartonItemAddSchema, CartonOutSchema
from app.utils import validation_error_response

bp = Blueprint("cartons", __name__, url_prefix="/api")

create_schema = CartonCreateSchema()
item_add_schema = CartonItemAddSchema()
out_schema = CartonOutSchema()


def _round_kg(value: float) -> float:
    return round(float(value or 0.0), 6)


def carton_payload(carton: Carton) -> dict:
    items = []
    total = 0.0
    for item in carton.items:
        h = item.harvest
        items.append(
            {
                "harvest_id": item.harvest_id,
                "room_id": h.room_id if h else None,
                "harvested_at": h.harvested_at if h else None,
                "flush_no": h.flush_no if h else None,
                "weight_kg": h.weight_kg if h else 0.0,
                "grade": h.grade if h else None,
                "operator_name": h.operator_name if h else None,
            }
        )
        if h:
            total += h.weight_kg
    return {
        "id": carton.id,
        "shed_id": carton.shed_id,
        "carton_no": carton.carton_no,
        "sealed_at": carton.sealed_at,
        "items": items,
        "total_kg": _round_kg(total),
    }


# ---------------------------------------------------------------------------
# Shed-scoped carton collection
# ---------------------------------------------------------------------------


@bp.get("/sheds/<int:shed_id>/cartons")
@jwt_required()
def list_cartons(shed_id: int):
    db = SessionLocal()
    try:
        shed = db.query(Shed).filter(Shed.id == shed_id).first()
        if not shed:
            return jsonify({"detail": "菇房不存在"}), 404
        rows = (
            db.query(Carton)
            .filter(Carton.shed_id == shed_id)
            .order_by(Carton.id)
            .all()
        )
        return jsonify(out_schema.dump([carton_payload(c) for c in rows], many=True))
    finally:
        db.close()


@bp.post("/sheds/<int:shed_id>/cartons")
@jwt_required()
def create_carton(shed_id: int):
    db = SessionLocal()
    try:
        try:
            data = create_schema.load(request.get_json(silent=True) or {})
        except ValidationError as err:
            return validation_error_response(err)
        if data["shed_id"] != shed_id:
            return jsonify({"detail": "shedId 与路径不一致"}), 400
        shed = db.query(Shed).filter(Shed.id == shed_id).first()
        if not shed:
            return jsonify({"detail": "菇房不存在"}), 404
        carton = Carton(shed_id=shed_id, carton_no=data["carton_no"], sealed_at=None)
        db.add(carton)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return jsonify({"detail": "同一菇房下箱号已存在"}), 409
        db.refresh(carton)
        return jsonify(out_schema.dump(carton_payload(carton))), 201
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Single carton
# ---------------------------------------------------------------------------


@bp.get("/cartons/reconcile")
@jwt_required()
def reconcile_cartons():
    """按菇房汇总箱数与公斤，并与明细直接求和核对（差应 ≤ 0.001）。"""
    db = SessionLocal()
    try:
        cartons = db.query(Carton).order_by(Carton.shed_id, Carton.id).all()
        by_shed: dict[int, dict] = {}
        for c in cartons:
            bucket = by_shed.setdefault(
                c.shed_id,
                {
                    "shed_id": c.shed_id,
                    "shed_name": c.shed.name if c.shed else None,
                    "carton_count": 0,
                    "carton_kg": 0.0,
                    "item_kg": 0.0,
                },
            )
            bucket["carton_count"] += 1
            bucket["carton_kg"] += carton_payload(c)["total_kg"]

        # 直接从明细求和（不经过箱合计），用于核对
        detail_rows = (
            db.query(Carton.shed_id, func.coalesce(func.sum(FlushHarvest.weight_kg), 0.0))
            .join(CartonItem, CartonItem.carton_id == Carton.id)
            .join(FlushHarvest, FlushHarvest.id == CartonItem.harvest_id)
            .group_by(Carton.shed_id)
            .all()
        )
        for shed_id, item_kg in detail_rows:
            bucket = by_shed.setdefault(
                shed_id,
                {
                    "shed_id": shed_id,
                    "shed_name": None,
                    "carton_count": 0,
                    "carton_kg": 0.0,
                    "item_kg": 0.0,
                },
            )
            bucket["item_kg"] = float(item_kg or 0.0)

        by_shed_out = []
        total_carton_kg = 0.0
        total_item_kg = 0.0
        total_count = 0
        for bucket in by_shed.values():
            carton_kg = _round_kg(bucket["carton_kg"])
            item_kg = _round_kg(bucket["item_kg"])
            delta = _round_kg(carton_kg - item_kg)
            by_shed_out.append(
                {
                    "shedId": bucket["shed_id"],
                    "shedName": bucket["shed_name"],
                    "cartonCount": bucket["carton_count"],
                    "cartonKg": carton_kg,
                    "itemKg": item_kg,
                    "deltaKg": delta,
                }
            )
            total_carton_kg += carton_kg
            total_item_kg += item_kg
            total_count += bucket["carton_count"]

        total_carton_kg = _round_kg(total_carton_kg)
        total_item_kg = _round_kg(total_item_kg)
        delta_total = _round_kg(total_carton_kg - total_item_kg)
        return jsonify(
            {
                "byShed": by_shed_out,
                "totalCartons": total_count,
                "cartonKg": total_carton_kg,
                "itemKg": total_item_kg,
                "deltaKg": delta_total,
                "balanced": abs(delta_total) <= 0.001,
            }
        )
    finally:
        db.close()


@bp.get("/cartons/<int:carton_id>")
@jwt_required()
def get_carton(carton_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        return jsonify(out_schema.dump(carton_payload(carton)))
    finally:
        db.close()


@bp.post("/cartons/<int:carton_id>/items")
@jwt_required()
def add_carton_item(carton_id: int):
    db = SessionLocal()
    try:
        try:
            data = item_add_schema.load(request.get_json(silent=True) or {})
        except ValidationError as err:
            return validation_error_response(err)
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return (
                jsonify({"detail": "纸箱已封箱，不能再加入潮次", "cartonId": carton.id}),
                409,
            )
        harvest = db.query(FlushHarvest).filter(FlushHarvest.id == data["harvest_id"]).first()
        if not harvest:
            return jsonify({"detail": "采收记录不存在"}), 404

        room = db.query(Room).filter(Room.id == harvest.room_id).first()
        if not room or room.shed_id != carton.shed_id:
            return (
                jsonify(
                    {
                        "detail": "该潮次的出菇室不属于本菇房，不能跨棚拼箱",
                        "cartonId": carton.id,
                    }
                ),
                409,
            )

        existing = (
            db.query(CartonItem).filter(CartonItem.harvest_id == harvest.id).first()
        )
        if existing:
            return (
                jsonify(
                    {
                        "detail": "该潮次已在另一只纸箱中，一笔潮次只能待在一只未封箱",
                        "cartonId": existing.carton_id,
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
            existing = (
                db.query(CartonItem).filter(CartonItem.harvest_id == harvest.id).first()
            )
            return (
                jsonify(
                    {
                        "detail": "该潮次已在另一只纸箱中，一笔潮次只能待在一只未封箱",
                        "cartonId": existing.carton_id if existing else carton.id,
                    }
                ),
                409,
            )
        db.refresh(carton)
        return jsonify(out_schema.dump(carton_payload(carton))), 201
    finally:
        db.close()


@bp.delete("/cartons/<int:carton_id>/items/<int:harvest_id>")
@jwt_required()
def remove_carton_item(carton_id: int, harvest_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return (
                jsonify({"detail": "纸箱已封箱，不能移出潮次", "cartonId": carton.id}),
                409,
            )
        item = (
            db.query(CartonItem)
            .filter(CartonItem.carton_id == carton.id, CartonItem.harvest_id == harvest_id)
            .first()
        )
        if not item:
            return jsonify({"detail": "该潮次不在本纸箱中"}), 404
        db.delete(item)
        db.commit()
        db.refresh(carton)
        return jsonify(out_schema.dump(carton_payload(carton)))
    finally:
        db.close()


@bp.post("/cartons/<int:carton_id>/seal")
@jwt_required()
def seal_carton(carton_id: int):
    db = SessionLocal()
    try:
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        if carton.sealed_at is not None:
            return jsonify({"detail": "纸箱已封箱", "cartonId": carton.id}), 409

        payload = carton_payload(carton)
        if len(payload["items"]) < 2:
            return (
                jsonify(
                    {
                        "detail": "封箱失败：箱内至少两笔潮次才可封箱",
                        "cartonId": carton.id,
                    }
                ),
                409,
            )
        if payload["total_kg"] <= 0:
            return (
                jsonify(
                    {
                        "detail": "封箱失败：箱内重量合计须大于 0",
                        "cartonId": carton.id,
                    }
                ),
                409,
            )

        carton.sealed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(carton)
        return jsonify(out_schema.dump(carton_payload(carton)))
    finally:
        db.close()


@bp.post("/cartons/<int:carton_id>/unseal")
@jwt_required()
def unseal_carton(carton_id: int):
    db = SessionLocal()
    try:
        username = get_jwt_identity()
        user = db.query(User).filter(User.username == username).first()
        if not user or user.role != "admin":
            return jsonify({"detail": "仅管理员（admin）可拆封纸箱"}), 403
        carton = db.query(Carton).filter(Carton.id == carton_id).first()
        if not carton:
            return jsonify({"detail": "纸箱不存在"}), 404
        # 拆封不清空条目，仅解除封箱状态
        carton.sealed_at = None
        db.commit()
        db.refresh(carton)
        return jsonify(out_schema.dump(carton_payload(carton)))
    finally:
        db.close()
