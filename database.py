from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine('sqlite:///cooperativa.db', echo=False)
SessionLocal = sessionmaker(bind=engine)

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

# ⚠️ IMPORTANTE: Esta línea SIEMPRE se ejecutará al iniciar la app,
# asegurando que las tablas existan en la nube.
Base.metadata.create_all(engine)
