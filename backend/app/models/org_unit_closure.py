from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrgUnitClosure(Base):
    __tablename__ = "org_unit_closure"

    ancestor_id: Mapped[str] = mapped_column(ForeignKey("org_units.id"), primary_key=True)
    descendant_id: Mapped[str] = mapped_column(ForeignKey("org_units.id"), primary_key=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("ancestor_id", "descendant_id", name="uq_org_unit_closure_pair"),)
