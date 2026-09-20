from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Carton(Base):
    __tablename__ = "cartons"
    __table_args__ = (UniqueConstraint("shed_id", "carton_no", name="uq_carton_shed_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shed_id: Mapped[int] = mapped_column(ForeignKey("sheds.id"), nullable=False, index=True)
    carton_no: Mapped[str] = mapped_column(String(64), nullable=False)
    sealed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[List["CartonItem"]] = relationship(
        "CartonItem",
        back_populates="carton",
        cascade="all, delete-orphan",
        order_by="CartonItem.id",
    )


class CartonItem(Base):
    __tablename__ = "carton_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    carton_id: Mapped[int] = mapped_column(ForeignKey("cartons.id"), nullable=False, index=True)
    # 一笔潮次至多挂在一只箱上（无论是否封箱）
    harvest_id: Mapped[int] = mapped_column(
        ForeignKey("flush_harvests.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )

    carton: Mapped["Carton"] = relationship("Carton", back_populates="items")
    harvest: Mapped["FlushHarvest"] = relationship("FlushHarvest")
