from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)


class Property(db.Model):
    __tablename__ = "properties"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255), nullable=False)


class Unit(db.Model):
    __tablename__ = "units"

    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(
        db.Integer,
        db.ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    unit_number = db.Column(db.String(255), nullable=False)
    rent_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="vacant")

    __table_args__ = (
        UniqueConstraint("property_id", "unit_number", name="uq_units_property_unit_number"),
    )


class Tenant(db.Model):
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(
        db.Integer,
        db.ForeignKey("units.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(32), nullable=False)
    id_number = db.Column(db.String(64), nullable=False)
    move_in_date = db.Column(db.String(32), nullable=False)


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.String(32), nullable=False)
    payment_method = db.Column(db.String(32), nullable=False)
    mpesa_code = db.Column(db.String(128), nullable=True)
    payment_month = db.Column(db.String(16), nullable=False)
