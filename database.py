from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

Base = declarative_base()
engine = create_engine('sqlite:///cooperativa.db', echo=False)
SessionLocal = sessionmaker(bind=engine)

# Tabla intermedia para la relación muchos a muchos entre Conciliacion y Pago
conciliacion_pago = Table(
    'conciliacion_pago',
    Base.metadata,
    Column('conciliacion_id', Integer, ForeignKey('conciliaciones.id')),
    Column('pago_id', Integer, ForeignKey('pagos.id'))
)

class Socio(Base):
    __tablename__ = 'socios'
    id = Column(Integer, primary_key=True)
    cupo = Column(String(20), unique=True, nullable=False)
    nombre = Column(String(100))
    telefono = Column(String(20))

class Pago(Base):
    __tablename__ = 'pagos'
    id = Column(Integer, primary_key=True)
    cupo = Column(String(20), nullable=False)
    monto = Column(Float, nullable=False)
    referencia = Column(String(50), nullable=False)
    fecha_reporte = Column(DateTime, default=datetime.now)
    fecha_conciliacion = Column(DateTime, nullable=True)
    estatus = Column(String(20), default='Pendiente')

class Conciliacion(Base):
    __tablename__ = 'conciliaciones'
    id = Column(Integer, primary_key=True)
    fecha_hora = Column(DateTime, default=datetime.now)
    total_pagos = Column(Integer, default=0)
    monto_total = Column(Float, default=0.0)
    # Relación con los pagos conciliados en este evento
    pagos = relationship("Pago", secondary=conciliacion_pago, backref="conciliacion")

# Crear todas las tablas (esto se ejecutará al iniciar la app)
Base.metadata.create_all(engine)
