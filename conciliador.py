import pandas as pd
from database import SessionLocal, Pago
from datetime import datetime

def ejecutar_conciliacion(ruta_archivo_bancos):
    session = SessionLocal()
    
    if ruta_archivo_bancos.endswith('.csv'):
        df_bancos = pd.read_csv(ruta_archivo_bancos)
    else:
        df_bancos = pd.read_excel(ruta_archivo_bancos)
    
    df_bancos['Monto'] = df_bancos['Monto'].astype(float)
    df_bancos['Referencia'] = df_bancos['Referencia'].astype(str).str.strip()
    
    pendientes = session.query(Pago).filter(Pago.estatus == 'Pendiente').all()
    conciliados_hoy = 0
    
    for pago in pendientes:
        coincidencia = df_bancos[
            (df_bancos['Referencia'] == pago.referencia) & 
            (df_bancos['Monto'] == pago.monto)
        ]
        if not coincidencia.empty:
            pago.estatus = 'Conciliado'
            pago.fecha_conciliacion = datetime.now()
            conciliados_hoy += 1
    
    session.commit()
    restantes = session.query(Pago).filter(Pago.estatus == 'Pendiente').count()
    session.close()
    
    return {
        "mensaje": f"✅ {conciliados_hoy} pagos conciliados.",
        "total_pendientes_restantes": restantes
    }