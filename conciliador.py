# ========== INICIO DEL ARCHIVO ==========
import pandas as pd
from database import SessionLocal, Pago, Conciliacion, conciliacion_pago
from datetime import datetime

def ejecutar_conciliacion(ruta_archivo_bancos):
    session = SessionLocal()
    
    # Cargar archivo
    if ruta_archivo_bancos.endswith('.csv'):
        df_bancos = pd.read_csv(ruta_archivo_bancos)
    else:
        df_bancos = pd.read_excel(ruta_archivo_bancos)
    
    # Limpiar datos
    df_bancos['Monto'] = df_bancos['Monto'].astype(float)
    df_bancos['Referencia'] = df_bancos['Referencia'].astype(str).str.strip()
    
    # Buscar pagos pendientes
    pendientes = session.query(Pago).filter(Pago.estatus == 'Pendiente').all()
    pagos_conciliados = []
    conciliados_hoy = 0
    
    for pago in pendientes:
        coincidencia = df_bancos[
            (df_bancos['Referencia'] == pago.referencia) & 
            (df_bancos['Monto'] == pago.monto)
        ]
        if not coincidencia.empty:
            pago.estatus = 'Conciliado'
            pago.fecha_conciliacion = datetime.now()
            pagos_conciliados.append(pago)
            conciliados_hoy += 1
    
    # Si se concilió al menos un pago, crear un registro de conciliación
    if conciliados_hoy > 0:
        nueva_conciliacion = Conciliacion(
            fecha_hora=datetime.now(),
            total_pagos=conciliados_hoy,
            monto_total=sum(p.monto for p in pagos_conciliados)
        )
        session.add(nueva_conciliacion)
        session.flush()  # Para obtener el ID de la conciliación
        
        # Asociar los pagos conciliados con esta conciliación
        for pago in pagos_conciliados:
            session.execute(
                conciliacion_pago.insert().values(
                    conciliacion_id=nueva_conciliacion.id,
                    pago_id=pago.id
                )
            )
    
    session.commit()
    
    restantes = session.query(Pago).filter(Pago.estatus == 'Pendiente').count()
    session.close()
    
    return {
        "mensaje": f"✅ {conciliados_hoy} pagos conciliados automáticamente.",
        "total_pendientes_restantes": restantes
    }
# ========== FIN DEL ARCHIVO ==========
