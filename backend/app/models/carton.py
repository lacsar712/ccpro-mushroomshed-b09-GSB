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
    sealed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    shed: Mapped["Shed"] = relationship("Shed")
    items: Mapped[List["CartonItem"]] = relationship(
        "CartonItem",
        back_populates="carton",
        cascade="all, delete-orphan",
        order_by="CartonItem.id",
    )
