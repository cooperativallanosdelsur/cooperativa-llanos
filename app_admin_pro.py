import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import SessionLocal, Pago, Socio, Conciliacion, conciliacion_pago
from conciliador import ejecutar_conciliacion
import os

# Importación de reportes
from reportes import (generar_pdf_reporte_socios, generar_pdf_recibo, 
                      generar_pdf_historial_conciliaciones, generar_pdf_detalle_conciliacion,
                      generar_pdf_historial_pagos)

st.set_page_config(page_title="Llanos del Sur", page_icon="🚛", layout="wide")

# --- AUTENTICACIÓN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.sidebar.title("🔐 Acceso")
    usuario = st.sidebar.text_input("Usuario")
    clave = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Ingresar"):
        if usuario == "admin" and clave == "cooperativa2026":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.sidebar.error("Credenciales incorrectas")
    st.stop()

# --- MENÚ LATERAL ---
st.sidebar.title("🚚 Menú")
menu = st.sidebar.radio("Navegación", ["📊 Dashboard", "📥 Conciliación", "👥 Socios", "📜 Pagos", "📊 Reportes"])

# --- CARGA DE DATOS ---
@st.cache_data(ttl=60)
def load_data():
    session = SessionLocal()
    socios = pd.read_sql(session.query(Socio).statement, session.bind)
    pagos = pd.read_sql(session.query(Pago).statement, session.bind)
    session.close()
    return socios, pagos

socios_df, pagos_df = load_data()

# ==========================================
# PÁGINA 1: DASHBOARD
# ==========================================
if menu == "📊 Dashboard":
    st.title("📊 Panel de Control")
    col1, col2, col3, col4 = st.columns(4)
    total = len(pagos_df)
    conc = len(pagos_df[pagos_df['estatus'] == 'Conciliado'])
    pend = len(pagos_df[pagos_df['estatus'] == 'Pendiente'])
    monto_total = pagos_df['monto'].sum() if not pagos_df.empty else 0
    
    col1.metric("💰 Total Pagos", total)
    col2.metric("✅ Conciliados", conc, delta=f"{round(conc/total*100 if total>0 else 0, 1)}%")
    col3.metric("⏳ Pendientes", pend)
    col4.metric("💵 Monto Total", f"${monto_total:,.2f}")
    
    if not pagos_df.empty:
        pagos_df['fecha'] = pd.to_datetime(pagos_df['fecha_reporte']).dt.date
        daily = pagos_df.groupby('fecha').size().reset_index(name='cantidad')
        fig = px.bar(daily, x='fecha', y='cantidad', title="📈 Pagos por Día")
        st.plotly_chart(fig, use_container_width=True)
        
        st.subheader("📋 Últimos pagos")
        st.dataframe(pagos_df.sort_values('fecha_reporte', ascending=False).head(10)[['cupo', 'monto', 'referencia', 'estatus']])

# ==========================================
# PÁGINA 2: CONCILIACIÓN
# ==========================================
elif menu == "📥 Conciliación":
    st.title("📥 Subir Estado de Cuenta")
    archivo = st.file_uploader("Carga tu archivo .CSV o .XLSX", type=['csv', 'xlsx'])
    
    if archivo is not None and st.button("🚀 Ejecutar Conciliación"):
        with open(f"temp_{archivo.name}", "wb") as f:
            f.write(archivo.getbuffer())
        with st.spinner("Cruzando datos..."):
            resultado = ejecutar_conciliacion(f"temp_{archivo.name}")
        st.success(resultado["mensaje"])
        st.info(f"⏳ Pendientes: {resultado['total_pendientes_restantes']}")
        os.remove(f"temp_{archivo.name}")

# ==========================================
# PÁGINA 3: SOCIOS
# ==========================================
elif menu == "👥 Socios":
    st.title("👥 Transportistas")
    
    with st.form("form_socio"):
        col1, col2, col3 = st.columns(3)
        with col1:
            cupo = st.text_input("Cupo (Ej: C-001)")
        with col2:
            nombre = st.text_input("Nombre completo")
        with col3:
            telefono = st.text_input("WhatsApp")
        if st.form_submit_button("➕ Registrar Socio"):
            if cupo and nombre:
                session = SessionLocal()
                existe = session.query(Socio).filter(Socio.cupo == cupo).first()
                if existe:
                    st.warning(f"⚠️ El cupo {cupo} ya está registrado.")
                else:
                    session.add(Socio(cupo=cupo, nombre=nombre, telefono=telefono))
                    session.commit()
                    st.success(f"✅ Socio {nombre} registrado con éxito!")
                    session.close()
                    st.rerun()
                session.close()
            else:
                st.error("Cupo y nombre son obligatorios.")
    
    st.divider()
    st.subheader("📋 Lista de Socios Actuales")
    
    session = SessionLocal()
    socios_db = session.query(Socio).all()
    session.close()
    
    if socios_db:
        df_socios = pd.DataFrame([{
            "Cupo": s.cupo, 
            "Nombre": s.nombre, 
            "Teléfono": s.telefono
        } for s in socios_db])
        st.dataframe(df_socios, use_container_width=True)
        
        st.divider()
        st.subheader("🗑️ Eliminar Socio")
        lista_cupos = [s.cupo for s in socios_db]
        cupo_a_eliminar = st.selectbox("Selecciona el Cupo del socio que deseas eliminar:", lista_cupos)
        if st.button("🗑️ Eliminar Socio Seleccionado", type="primary"):
            session = SessionLocal()
            socio = session.query(Socio).filter(Socio.cupo == cupo_a_eliminar).first()
            if socio:
                pagos_asociados = session.query(Pago).filter(Pago.cupo == cupo_a_eliminar).count()
                if pagos_asociados > 0:
                    st.warning(f"⚠️ Este socio tiene {pagos_asociados} pagos registrados. No se puede eliminar.")
                else:
                    session.delete(socio)
                    session.commit()
                    st.success(f"✅ Socio {cupo_a_eliminar} eliminado correctamente.")
                    session.close()
                    st.rerun()
                session.close()
            else:
                st.error("Socio no encontrado.")
    else:
        st.info("📭 No hay socios registrados aún.")

# ==========================================
# PÁGINA 4: PAGOS (CON CARGA MASIVA MEJORADA)
# ==========================================
elif menu == "📜 Pagos":
    st.title("📜 Historial de Pagos")
    
    # --- 1. CARGA MANUAL (1 a 1) ---
    with st.expander("➕ Agregar Pago de Prueba (Solo para testing)"):
        col1, col2, col3 = st.columns(3)
        with col1:
            cupo_pago = st.text_input("Cupo del socio", "C-001")
        with col2:
            monto_pago = st.number_input("Monto", value=250.00, step=10.0)
        with col3:
            ref_pago = st.text_input("Referencia (4 dígitos)", "1234")
        if st.button("Registrar Pago de Prueba"):
            if cupo_pago and monto_pago and ref_pago:
                session = SessionLocal()
                nuevo_pago = Pago(
                    cupo=cupo_pago,
                    monto=monto_pago,
                    referencia=ref_pago,
                    estatus='Pendiente'
                )
                session.add(nuevo_pago)
                session.commit()
                session.close()
                st.success(f"✅ Pago de {cupo_pago} registrado con éxito!")
                st.rerun()
    
    # --- 2. CARGA MASIVA (OPCIÓN A CON DETALLE DE SOCIOS CREADOS) ---
    with st.expander("📤 Carga Masiva de Pagos (Sube un archivo CSV/Excel)"):
        st.info("El archivo debe tener las columnas: **Cupo**, **Monto** y **Referencia**.\n\n"
                "⚠️ **Opción A activada:** Si un socio no existe, el sistema lo creará automáticamente con el nombre 'Socio C-XXX' y teléfono vacío. Luego deberás editar sus datos en la pestaña 'Socios'.\n\n"
                "📌 **Detalle:** Al finalizar, te mostraremos cuántos socios ya existían y cuántos fueron creados nuevos.")
        archivo_masivo = st.file_uploader("Selecciona archivo", type=['csv', 'xlsx'], key="masivo_upload")
        
        if archivo_masivo is not None and st.button("🚀 Cargar Pagos Masivos", key="masivo_btn"):
            try:
                # Leer archivo
                if archivo_masivo.name.endswith('.csv'):
                    df_masivo = pd.read_csv(archivo_masivo)
                else:
                    df_masivo = pd.read_excel(archivo_masivo)
                
                # Limpiar nombres de columnas
                df_masivo.columns = df_masivo.columns.str.strip().str.lower()
                
                # Verificar columnas requeridas
                columnas_requeridas = ['cupo', 'monto', 'referencia']
                if not all(col in df_masivo.columns for col in columnas_requeridas):
                    st.error(f"El archivo debe contener las columnas: {', '.join(columnas_requeridas)} (sin importar mayúsculas).")
                else:
                    session = SessionLocal()
                    registrados = 0
                    errores = 0
                    socios_creados = 0
                    socios_existentes = 0
                    detalles = []  # Para mostrar el detalle de cada fila
                    
                    for index, row in df_masivo.iterrows():
                        try:
                            cupo_val = str(row['cupo']).strip()
                            monto_val = float(str(row['monto']).replace(',', '.'))
                            ref_val = str(row['referencia']).strip()
                            
                            # Verificar si el socio existe
                            socio = session.query(Socio).filter(Socio.cupo == cupo_val).first()
                            if not socio:
                                nuevo_socio = Socio(cupo=cupo_val, nombre=f"Socio {cupo_val}", telefono="")
                                session.add(nuevo_socio)
                                session.flush()
                                socios_creados += 1
                                estado_socio = "🆕 Creado"
                            else:
                                socios_existentes += 1
                                estado_socio = "✅ Existente"
                            
                            # Crear el pago
                            nuevo_pago = Pago(
                                cupo=cupo_val,
                                monto=monto_val,
                                referencia=ref_val,
                                estatus='Pendiente'
                            )
                            session.add(nuevo_pago)
                            registrados += 1
                            
                            # Guardar detalle (opcional, para mostrarlo si se desea)
                            detalles.append({
                                "Cupo": cupo_val,
                                "Monto": monto_val,
                                "Referencia": ref_val,
                                "Estado Socio": estado_socio
                            })
                        except Exception as e:
                            errores += 1
                            st.warning(f"Error en fila {index+2}: {str(e)}")
                    
                    session.commit()
                    session.close()
                    
                    # Mostrar resumen detallado
                    st.success(f"✅ ¡{registrados} pagos cargados exitosamente! (Errores: {errores})")
                    st.info(f"📊 **Resumen de socios:** {socios_existentes} ya existían, {socios_creados} fueron creados automáticamente.")
                    
                    # Opcional: mostrar una tabla con el detalle de socio creado o existente
                    if detalles:
                        df_detalle = pd.DataFrame(detalles)
                        st.subheader("📋 Detalle de la carga")
                        st.dataframe(df_detalle, use_container_width=True)
                    
                    if socios_creados > 0:
                        st.warning("⚠️ Recuerda editar los datos de los socios creados automáticamente (nombre y teléfono) en la pestaña 'Socios'.")
                    
                    st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
    
    st.divider()
    
    # --- TABLA DE PAGOS ---
    col_filtro, col_acciones, col_borrar = st.columns([2, 1, 1])
    with col_filtro:
        filtro = st.selectbox("Filtrar por estatus", ["Todos", "Pendiente", "Conciliado"])
    
    session = SessionLocal()
    pagos_db = session.query(Pago).all()
    session.close()
    
    if pagos_db:
        df_pagos = pd.DataFrame([{
            "ID": p.id,
            "Cupo": p.cupo,
            "Monto": p.monto,
            "Referencia": p.referencia,
            "Estatus": p.estatus,
            "Fecha Reporte": p.fecha_reporte.strftime("%Y-%m-%d %H:%M"),
            "Fecha Conciliación": p.fecha_conciliacion.strftime("%Y-%m-%d %H:%M") if p.fecha_conciliacion else "N/A"
        } for p in pagos_db])
        
        if filtro != "Todos":
            df_filtrado = df_pagos[df_pagos['Estatus'] == filtro]
        else:
            df_filtrado = df_pagos
        
        st.dataframe(df_filtrado, use_container_width=True)
        
        # --- BOTÓN ENVIAR RECIBO ---
        st.subheader("📨 Enviar Recibo de Pago")
        conciliados = df_pagos[df_pagos['Estatus'] == 'Conciliado']
        if not conciliados.empty:
            opciones = {f"{row['Cupo']} - ${row['Monto']} (Ref: {row['Referencia']})": row['ID'] for _, row in conciliados.iterrows()}
            seleccion = st.selectbox("Selecciona el pago para enviar recibo:", list(opciones.keys()))
            pago_id = opciones[seleccion]
            
            session = SessionLocal()
            pago = session.query(Pago).get(pago_id)
            socio = session.query(Socio).filter(Socio.cupo == pago.cupo).first()
            session.close()
            
            if pago and socio:
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📄 Vista previa del Recibo (PDF)"):
                        pdf_recibo = generar_pdf_recibo(pago, socio)
                        st.download_button(
                            label="📥 Descargar Recibo PDF",
                            data=pdf_recibo,
                            file_name=f"recibo_{socio.cupo}_{pago.id}.pdf",
                            mime="application/pdf"
                        )
                with col2:
                    if st.button("📨 Enviar por WhatsApp (simulado)"):
                        st.success(f"✅ Recibo enviado exitosamente al socio {socio.nombre} (simulación).")
                        st.info("En producción se enviará el PDF por WhatsApp usando Twilio.")
        else:
            st.info("No hay pagos conciliados para enviar recibos.")
        
        # --- COLUMNA PARA ARCHIVAR (CSV y PDF) ---
        with col_acciones:
            st.write("")
            st.write("")
            csv_completo = df_pagos.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar CSV",
                data=csv_completo,
                file_name=f"historial_pagos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            if st.button("📄 Generar Historial PDF", key="gen_pdf_pagos"):
                st.session_state['pdf_pagos_data'] = generar_pdf_historial_pagos(df_pagos)
            
            if 'pdf_pagos_data' in st.session_state:
                st.download_button(
                    label="📥 Descargar PDF",
                    data=st.session_state['pdf_pagos_data'],
                    file_name=f"historial_pagos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        
        # --- COLUMNA PARA BORRAR TODOS LOS PAGOS ---
        with col_borrar:
            st.write("")
            st.write("")
            confirmar_borrado = st.checkbox("⚠️ Marcar para confirmar borrado TOTAL")
            if st.button("🗑️ Eliminar TODOS los Pagos", use_container_width=True, type="primary"):
                if confirmar_borrado:
                    session = SessionLocal()
                    borrados = session.query(Pago).delete()
                    session.commit()
                    session.close()
                    st.success(f"✅ Se eliminaron {borrados} pagos.")
                    st.rerun()
                else:
                    st.error("❌ Debes marcar la casilla de confirmación.")
    else:
        st.info("📭 No hay pagos registrados aún.")

# ==========================================
# PÁGINA 5: REPORTES
# ==========================================
else:
    st.title("📊 Reportes y Conciliaciones")
    
    # --- SECCIÓN 1: HISTORIAL DE CONCILIACIONES ---
    st.header("📋 Historial de Conciliaciones")
    
    session = SessionLocal()
    conciliaciones = session.query(Conciliacion).order_by(Conciliacion.fecha_hora.desc()).all()
    session.close()
    
    if conciliaciones:
        data = []
        for c in conciliaciones:
            data.append({
                "ID": c.id,
                "Fecha/Hora": c.fecha_hora.strftime("%Y-%m-%d %H:%M"),
                "Total Pagos": c.total_pagos,
                "Monto Total": c.monto_total,
                "Conciliado con el banco": "✅ Sí" if c.total_pagos > 0 else "❌ No"
            })
        df_conciliaciones = pd.DataFrame(data)
        st.dataframe(df_conciliaciones, use_container_width=True)
        
        st.subheader("📌 Acciones por Conciliación")
        opciones = {f"{row['Fecha/Hora']} - {row['Total Pagos']} pagos - ${row['Monto Total']:,.2f}": row['ID'] for _, row in df_conciliaciones.iterrows()}
        seleccion = st.selectbox("Selecciona una conciliación para gestionar:", list(opciones.keys()))
        conciliacion_id = opciones[seleccion]
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📄 Exportar Detalle (PDF)"):
                session = SessionLocal()
                conciliacion = session.query(Conciliacion).get(conciliacion_id)
                pagos = conciliacion.pagos
                if pagos:
                    df_detalle = pd.DataFrame([{
                        "Cupo": p.cupo,
                        "Monto": p.monto,
                        "Referencia": p.referencia,
                        "Fecha Reporte": p.fecha_reporte.strftime("%Y-%m-%d %H:%M")
                    } for p in pagos])
                    session.close()
                    if not df_detalle.empty:
                        pdf_buffer = generar_pdf_detalle_conciliacion(conciliacion_id, df_detalle)
                        st.download_button(
                            label="📥 Descargar PDF",
                            data=pdf_buffer,
                            file_name=f"conciliacion_{conciliacion_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf"
                        )
                else:
                    st.warning("Esta conciliación no tiene pagos asociados.")
        
        with col2:
            if st.button("📄 Exportar Detalle (CSV)"):
                session = SessionLocal()
                conciliacion = session.query(Conciliacion).get(conciliacion_id)
                pagos = conciliacion.pagos
                if pagos:
                    df_detalle = pd.DataFrame([{
                        "Cupo": p.cupo,
                        "Monto": p.monto,
                        "Referencia": p.referencia,
                        "Fecha Reporte": p.fecha_reporte.strftime("%Y-%m-%d %H:%M")
                    } for p in pagos])
                    session.close()
                    if not df_detalle.empty:
                        csv_detalle = df_detalle.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                        st.download_button(
                            label="📥 Descargar CSV",
                            data=csv_detalle,
                            file_name=f"conciliacion_{conciliacion_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                else:
                    st.warning("Esta conciliación no tiene pagos asociados.")
        
        with col3:
            confirmar = st.checkbox("⚠️ Marcar para eliminar esta conciliación")
            if st.button("🗑️ Eliminar Conciliación", type="primary"):
                if confirmar:
                    session = SessionLocal()
                    conciliacion = session.query(Conciliacion).get(conciliacion_id)
                    if conciliacion:
                        session.execute(conciliacion_pago.delete().where(conciliacion_pago.c.conciliacion_id == conciliacion_id))
                        session.delete(conciliacion)
                        session.commit()
                        st.success(f"✅ Conciliación #{conciliacion_id} eliminada.")
                        st.rerun()
                    session.close()
                else:
                    st.error("❌ Debes marcar la casilla de confirmación.")
        
        st.divider()
        col_csv, col_pdf = st.columns(2)
        with col_csv:
            csv_hist = df_conciliaciones.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Historial Completo (CSV)",
                data=csv_hist,
                file_name=f"historial_conciliaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        with col_pdf:
            if st.button("📄 Generar Historial Completo (PDF)"):
                pdf_buffer = generar_pdf_historial_conciliaciones(df_conciliaciones)
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_buffer,
                    file_name=f"historial_conciliaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
    else:
        st.info("Aún no se ha realizado ninguna conciliación.")
    
    st.divider()
    
    # --- SECCIÓN 2: REPORTE DE SOCIOS ---
    st.header("📄 Reporte de Socios - Estado de Pagos")
    
    session = SessionLocal()
    socios = session.query(Socio).all()
    pagos = session.query(Pago).all()
    session.close()
    
    if socios:
        reporte = []
        for socio in socios:
            pagos_socio = [p for p in pagos if p.cupo == socio.cupo]
            total_pagado = sum(p.monto for p in pagos_socio if p.estatus == 'Conciliado')
            total_pendiente = sum(p.monto for p in pagos_socio if p.estatus == 'Pendiente')
            estado = "Al día" if total_pendiente == 0 else "Moroso"
            reporte.append({
                "Cupo": socio.cupo,
                "Nombre": socio.nombre,
                "Teléfono": socio.telefono,
                "Total Pagado": total_pagado,
                "Total Pendiente": total_pendiente,
                "Estado": estado
            })
        
        df_reporte = pd.DataFrame(reporte)
        st.dataframe(df_reporte, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            csv_reporte = df_reporte.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Reporte en CSV",
                data=csv_reporte,
                file_name=f"reporte_socios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        with col2:
            if st.button("📄 Generar Reporte en PDF"):
                pdf_buffer = generar_pdf_reporte_socios(df_reporte)
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_buffer,
                    file_name=f"reporte_socios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf"
                )
    else:
        st.info("No hay socios registrados para generar el reporte.")
