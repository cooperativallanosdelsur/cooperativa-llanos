import pandas as pd
from database import SessionLocal, Pago, Conciliacion, conciliacion_pago
from datetime import datetime

def ejecutar_conciliacion(ruta_archivo_bancos):
    session = SessionLocal()
    
    # Cargar archivo (Excel o CSV)
    if ruta_archivo_bancos.endswith('.csv'):
        df = pd.read_csv(ruta_archivo_bancos, header=None)
    else:
        df = pd.read_excel(ruta_archivo_bancos, header=None)
    
    # Buscar la fila donde están los encabezados
    header_row = None
    for i, row in df.iterrows():
        row_text = ' '.join(str(val) for val in row.values if pd.notna(val))
        if 'referencia' in row_text.lower() and 'monto' in row_text.lower():
            header_row = i
            break
    
    if header_row is None:
        raise ValueError("No se encontró la fila con 'Referencia' y 'Monto' en el archivo.")
    
    # Usar esa fila como encabezado y leer los datos desde la siguiente fila
    df_clean = pd.read_excel(ruta_archivo_bancos, header=header_row) if not ruta_archivo_bancos.endswith('.csv') else pd.read_csv(ruta_archivo_bancos, header=header_row)
    
    # Limpiar columnas: eliminar espacios y normalizar nombres
    df_clean.columns = df_clean.columns.str.strip().str.lower()
    df_clean = df_clean.dropna(how='all')
    
    # Identificar las columnas correctas (pueden llamarse "referencia" o "monto")
    ref_col = None
    monto_col = None
    for col in df_clean.columns:
        if 'referencia' in col or 'ref' in col:
            ref_col = col
        if 'monto' in col or 'monto' in col or 'importe' in col:
            monto_col = col
    
    if ref_col is None or monto_col is None:
        raise ValueError("No se encontraron las columnas 'Referencia' y 'Monto'.")
    
    # Limpiar datos
    df_clean[ref_col] = df_clean[ref_col].astype(str).str.strip()
    df_clean[monto_col] = df_clean[monto_col].astype(str).str.replace(',', '.').astype(float)
    
    # Eliminar filas que sean "Total" o tengan valores vacíos
    df_clean = df_clean[~df_clean[ref_col].str.lower().str.contains('total', na=False)]
    df_clean = df_clean[df_clean[ref_col] != '']
    df_clean = df_clean[df_clean[ref_col].notna()]
    
    # Buscar pagos pendientes
    pendientes = session.query(Pago).filter(Pago.estatus == 'Pendiente').all()
    pagos_conciliados = []
    conciliados_hoy = 0
    
    for pago in pendientes:
        # Buscar coincidencia en el DataFrame
        coincidencia = df_clean[
            (df_clean[ref_col] == pago.referencia) & 
            (df_clean[monto_col] == pago.monto)
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
        session.flush()
        
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
