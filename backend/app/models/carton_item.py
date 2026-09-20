from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CartonItem(Base):
    __tablename__ = "carton_items"
    __table_args__ = (
        UniqueConstraint("carton_id", "harvest_id", name="uq_carton_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    carton_id: Mapped[int] = mapped_column(ForeignKey("cartons.id"), nullable=False, index=True)
    harvest_id: Mapped[int] = mapped_column(
        ForeignKey("flush_harvests.id"), nullable=False, unique=True, index=True
    )

    carton: Mapped["Carton"] = relationship("Carton", back_populates="items")
    harvest: Mapped["FlushHarvest"] = relationship("FlushHarvest")
