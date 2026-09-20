from marshmallow import Schema, fields, validate


class CartonCreateSchema(Schema):
    carton_no = fields.Str(
        required=True, data_key="cartonNo", validate=validate.Length(min=1, max=64)
    )
    shed_id = fields.Int(required=True, data_key="shedId")


class CartonItemAddSchema(Schema):
    harvest_id = fields.Int(required=True, data_key="harvestId")


class CartonItemOutSchema(Schema):
    id = fields.Int(dump_only=True)
    harvest_id = fields.Int(data_key="harvestId")
    room_id = fields.Int(data_key="roomId")
    harvested_at = fields.DateTime(data_key="harvestedAt")
    flush_no = fields.Int(data_key="flushNo")
    weight_kg = fields.Float(data_key="weightKg")
    grade = fields.Str()
    operator_name = fields.Str(data_key="operatorName")


class CartonOutSchema(Schema):
    id = fields.Int(dump_only=True)
    shed_id = fields.Int(data_key="shedId")
    carton_no = fields.Str(data_key="cartonNo")
    sealed_at = fields.DateTime(allow_none=True, data_key="sealedAt")
    items = fields.List(fields.Nested(CartonItemOutSchema))
    total_kg = fields.Float(data_key="totalKg")
