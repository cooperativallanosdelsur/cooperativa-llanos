import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import SessionLocal, Pago, Socio, Conciliacion, conciliacion_pago, ConciliacionEliminada
from conciliador import ejecutar_conciliacion
import os
import unicodedata
import base64
import json

# Importaciones desde reportes.py
from reportes import (generar_pdf_reporte_socios, generar_pdf_recibo,
                      generar_pdf_historial_conciliaciones, generar_pdf_detalle_conciliacion,
                      generar_pdf_historial_pagos, generar_pdf_lista_socios,
                      generar_pdf_pendientes)

st.set_page_config(page_title="Llanos del Sur", page_icon="🚛", layout="wide")

# ========== FUNCIÓN PARA MOSTRAR PDF EN NUEVA PESTAÑA ==========
def mostrar_pdf_preview(pdf_buffer, key_sufijo=""):
    if pdf_buffer is None:
        return
    pdf_bytes = pdf_buffer.getvalue()
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
    html_link = f'''
    <a href="data:application/pdf;base64,{pdf_base64}" target="_blank" 
       style="display: inline-block; 
              background-color: #4CAF50; 
              color: white; 
              padding: 10px 20px; 
              text-decoration: none; 
              border-radius: 5px; 
              font-weight: bold;">
        📂 Abrir PDF en nueva pestaña
    </a>
    '''
    st.markdown(html_link, unsafe_allow_html=True)
    st.caption("⚠️ El PDF se abrirá en una nueva pestaña de tu navegador.")

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

# Cargar datos
@st.cache_data(ttl=60)
def load_data():
    session = SessionLocal()
    socios = pd.read_sql(session.query(Socio).statement, session.bind)
    pagos = pd.read_sql(session.query(Pago).statement, session.bind)
    session.close()
    return socios, pagos

socios_df, pagos_df = load_data()

st.sidebar.divider()
st.sidebar.metric("👥 Total Socios", len(socios_df))
st.sidebar.metric("💰 Total Pagos", len(pagos_df))

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
    
    st.divider()
    col_socios1, col_socios2 = st.columns([2, 1])
    with col_socios1:
        st.subheader("👥 Últimos socios registrados")
        if not socios_df.empty:
            ultimos_socios = socios_df.tail(5)[['cupo', 'nombre', 'telefono']].sort_index(ascending=False)
            st.dataframe(ultimos_socios, use_container_width=True, hide_index=True)
        else:
            st.info("No hay socios registrados aún.")
    
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
    st.title("📥 Conciliación Bancaria")
    
    with st.expander("📤 Cargar pagos de socios (CSV/Excel)", expanded=False):
        st.info("Sube aquí el archivo con los pagos reportados por los socios.\n\n"
                "Este archivo debe tener las columnas: **Cupo**, **Monto**, **Referencia**.\n"
                "El sistema analizará los datos y te permitirá registrarlos (creando socios si es necesario).\n\n"
                "⚠️ Los pagos registrados aquí aparecerán automáticamente en la pestaña **'Pagos'**.")
        
        archivo_pagos_conc = st.file_uploader("Selecciona el archivo de pagos", type=['csv', 'xlsx'], key="upload_pagos_conc")
        
        if archivo_pagos_conc is not None:
            if st.button("🔍 Analizar pagos", key="analizar_pagos_conc"):
                try:
                    if archivo_pagos_conc.name.endswith('.csv'):
                        try:
                            df_pagos_conc = pd.read_csv(archivo_pagos_conc, encoding='utf-8-sig')
                        except:
                            df_pagos_conc = pd.read_csv(archivo_pagos_conc, encoding='latin-1')
                    else:
                        df_pagos_conc = pd.read_excel(archivo_pagos_conc)
                    
                    def normalize_column_name(col):
                        col = unicodedata.normalize('NFKD', col).encode('ascii', 'ignore').decode('utf-8')
                        return col.strip().lower()
                    
                    df_pagos_conc.columns = [normalize_column_name(col) for col in df_pagos_conc.columns]
                    
                    col_cupo = None
                    col_monto = None
                    col_ref = None
                    for col in df_pagos_conc.columns:
                        if 'cupo' in col:
                            col_cupo = col
                        elif 'monto' in col or 'importe' in col:
                            col_monto = col
                        elif 'referencia' in col or 'ref' in col:
                            col_ref = col
                    
                    if col_cupo is None or col_monto is None or col_ref is None:
                        st.error("No se encontraron las columnas 'Cupo', 'Monto' y 'Referencia'. Verifica los encabezados.")
                    else:
                        df_pagos_conc = df_pagos_conc.rename(columns={
                            col_cupo: 'cupo',
                            col_monto: 'monto',
                            col_ref: 'referencia'
                        })
                        
                        st.subheader("📋 Vista previa del archivo")
                        st.dataframe(df_pagos_conc.head(5), use_container_width=True)
                        
                        session = SessionLocal()
                        existentes_conc = []
                        no_existentes_conc = []
                        
                        for index, row in df_pagos_conc.iterrows():
                            try:
                                cupo_val = str(row['cupo']).strip()
                                monto_val = float(str(row['monto']).replace(',', '.'))
                                ref_val = str(row['referencia']).strip()
                                
                                socio = session.query(Socio).filter(Socio.cupo == cupo_val).first()
                                if socio:
                                    existentes_conc.append({
                                        "Cupo": cupo_val,
                                        "Socio": socio.nombre,
                                        "Monto": monto_val,
                                        "Referencia": ref_val
                                    })
                                else:
                                    no_existentes_conc.append({
                                        "Cupo": cupo_val,
                                        "Nombre sugerido": f"Socio {cupo_val}",
                                        "Monto": monto_val,
                                        "Referencia": ref_val
                                    })
                            except Exception as e:
                                st.warning(f"Error en fila {index+2}: {str(e)}")
                        
                        session.close()
                        
                        st.session_state['existentes_conc'] = existentes_conc
                        st.session_state['no_existentes_conc'] = no_existentes_conc
                        st.session_state['analisis_pagos_conc'] = True
                        
                        st.subheader("📊 Resumen del análisis")
                        st.info(f"Total de pagos en archivo: {len(df_pagos_conc)}")
                        st.success(f"✅ Socios existentes: {len(existentes_conc)}")
                        st.warning(f"⚠️ Socios NO existentes (se crearán si autorizas): {len(no_existentes_conc)}")
                        
                        if existentes_conc:
                            st.subheader("📋 Pagos de socios existentes")
                            st.dataframe(pd.DataFrame(existentes_conc), use_container_width=True)
                        
                        if no_existentes_conc:
                            st.subheader("🆕 Socios NO existentes (requieren autorización)")
                            st.dataframe(pd.DataFrame(no_existentes_conc), use_container_width=True)
                            st.caption("Si autorizas, se crearán con nombre genérico 'Socio C-XXX' y teléfono vacío.")
                        
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al leer el archivo: {str(e)}")
            
            if st.session_state.get('analisis_pagos_conc', False):
                st.divider()
                st.subheader("📌 Acciones de registro")
                
                col_res1, col_res2 = st.columns(2)
                with col_res1:
                    st.metric("Socios existentes", len(st.session_state.get('existentes_conc', [])))
                with col_res2:
                    st.metric("Socios NO existentes", len(st.session_state.get('no_existentes_conc', [])))
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("📝 Registrar solo pagos de socios existentes", key="btn_existentes_conc"):
                        existentes_conc = st.session_state.get('existentes_conc', [])
                        if existentes_conc:
                            session = SessionLocal()
                            registrados = 0
                            for item in existentes_conc:
                                nuevo_pago = Pago(
                                    cupo=item["Cupo"],
                                    monto=item["Monto"],
                                    referencia=item["Referencia"],
                                    estatus='Pendiente'
                                )
                                session.add(nuevo_pago)
                                registrados += 1
                            session.commit()
                            session.close()
                            st.success(f"✅ Se registraron {registrados} pagos de socios existentes. (Los socios faltantes fueron omitidos)")
                            st.session_state['analisis_pagos_conc'] = False
                            st.rerun()
                        else:
                            st.info("No hay pagos de socios existentes para registrar.")
                
                with col_btn2:
                    if st.button("🚀 Registrar TODOS los pagos (crear socios faltantes)", key="btn_todos_conc"):
                        session = SessionLocal()
                        registrados = 0
                        creados = 0
                        
                        no_existentes_conc = st.session_state.get('no_existentes_conc', [])
                        existentes_conc = st.session_state.get('existentes_conc', [])
                        
                        for item in no_existentes_conc:
                            cupo = item["Cupo"]
                            socio = session.query(Socio).filter(Socio.cupo == cupo).first()
                            if not socio:
                                nuevo_socio = Socio(cupo=cupo, nombre=f"Socio {cupo}", telefono="")
                                session.add(nuevo_socio)
                                session.flush()
                                creados += 1
                        
                        todos_pagos = existentes_conc + no_existentes_conc
                        for item in todos_pagos:
                            nuevo_pago = Pago(
                                cupo=item["Cupo"],
                                monto=item["Monto"],
                                referencia=item["Referencia"],
                                estatus='Pendiente'
                            )
                            session.add(nuevo_pago)
                            registrados += 1
                        
                        session.commit()
                        session.close()
                        st.success(f"✅ Se registraron {registrados} pagos y se crearon {creados} socios nuevos.")
                        st.session_state['analisis_pagos_conc'] = False
                        st.rerun()
    
    st.divider()
    
    with st.expander("📥 Subir Estado de Cuenta del Banco", expanded=True):
        st.info("Sube el archivo del banco (CSV o Excel) con las columnas **Referencia** y **Monto**.\n\n"
                "Luego haz clic en 'Ejecutar Conciliación' para cruzar los datos con los pagos registrados.\n\n"
                "⚠️ Después de la conciliación, se mostrará la lista detallada de los pagos que **NO** pudieron conciliarse.\n"
                "Podrás descargar esa lista en **CSV** y en **PDF**, y también ver una **vista previa** del PDF.")
        
        archivo_banco = st.file_uploader("Selecciona el archivo del banco", type=['csv', 'xlsx'], key="upload_banco")
        
        if archivo_banco is not None and st.button("🚀 Ejecutar Conciliación", key="btn_conciliar"):
            with open(f"temp_{archivo_banco.name}", "wb") as f:
                f.write(archivo_banco.getbuffer())
            with st.spinner("Cruzando datos..."):
                resultado = ejecutar_conciliacion(f"temp_{archivo_banco.name}")
            st.success(resultado["mensaje"])
            st.info(f"⏳ Pendientes: {resultado['total_pendientes_restantes']}")
            
            if resultado.get('pendientes'):
                st.subheader("📋 Detalle de pagos pendientes (no conciliados)")
                df_pendientes = pd.DataFrame(resultado['pendientes'])
                st.dataframe(df_pendientes, use_container_width=True)
                
                st.subheader("📥 Descargar lista de pendientes")
                col_csv, col_pdf = st.columns(2)
                
                pdf_buffer_pendientes = generar_pdf_pendientes(df_pendientes)
                
                with col_csv:
                    csv_pendientes = df_pendientes.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button(
                        label="📥 Descargar CSV",
                        data=csv_pendientes,
                        file_name=f"pendientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                
                with col_pdf:
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=pdf_buffer_pendientes,
                        file_name=f"pendientes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                
                st.subheader("📄 Vista previa del PDF")
                mostrar_pdf_preview(pdf_buffer_pendientes, key_sufijo="pendientes")
                
            else:
                st.success("🎉 ¡No hay pagos pendientes! Todos los pagos fueron conciliados.")
            
            os.remove(f"temp_{archivo_banco.name}")

# ==========================================
# PÁGINA 3: SOCIOS
# ==========================================
elif menu == "👥 Socios":
    st.title("👥 Transportistas")
    
    tab1, tab2, tab3 = st.tabs(["➕ Agregar Individual", "📤 Carga Masiva", "📋 Lista de Socios"])
    
    with tab1:
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
    
    with tab2:
        st.subheader("📤 Carga Masiva de Socios (CSV/Excel)")
        st.info("El archivo debe tener las columnas: **Cupo**, **Nombre** y **Teléfono**.\n\n"
                "⚠️ Los cupos duplicados serán omitidos para evitar errores.")
        
        plantilla = pd.DataFrame({
            "Cupo": ["C-001", "C-002"],
            "Nombre": ["Ana López", "Carlos Ruiz"],
            "Teléfono": ["584121234567", "584122345678"]
        })
        csv_template = plantilla.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
        st.download_button(
            label="📥 Descargar Plantilla (CSV)",
            data=csv_template,
            file_name="plantilla_socios.csv",
            mime="text/csv"
        )
        
        archivo_socios = st.file_uploader("Selecciona archivo", type=['csv', 'xlsx'], key="upload_socios")
        
        if archivo_socios is not None and st.button("🚀 Cargar Socios Masivos", key="btn_socios"):
            try:
                if archivo_socios.name.endswith('.csv'):
                    try:
                        df_socios = pd.read_csv(archivo_socios, encoding='utf-8-sig')
                    except:
                        df_socios = pd.read_csv(archivo_socios, encoding='latin-1')
                else:
                    df_socios = pd.read_excel(archivo_socios)
                
                st.subheader("📋 Vista previa del archivo")
                if len(df_socios) <= 20:
                    st.dataframe(df_socios, use_container_width=True)
                else:
                    st.dataframe(df_socios.head(10), use_container_width=True)
                    st.caption(f"Mostrando 10 de {len(df_socios)} filas.")
                
                def normalize_column_name(col):
                    col = unicodedata.normalize('NFKD', col).encode('ascii', 'ignore').decode('utf-8')
                    return col.strip().lower()
                
                df_socios.columns = [normalize_column_name(col) for col in df_socios.columns]
                
                col_cupo = None
                col_nombre = None
                col_telefono = None
                for col in df_socios.columns:
                    if 'cupo' in col:
                        col_cupo = col
                    elif 'nombre' in col or 'nomb' in col:
                        col_nombre = col
                    elif 'telef' in col or 'cel' in col:
                        col_telefono = col
                
                if col_cupo is None or col_nombre is None:
                    st.error("No se encontraron las columnas 'Cupo' y 'Nombre'. Verifica los encabezados.")
                else:
                    df_socios = df_socios.rename(columns={
                        col_cupo: 'cupo',
                        col_nombre: 'nombre',
                        col_telefono: 'telefono'
                    })
                    
                    if 'telefono' not in df_socios.columns:
                        st.warning("No se encontró columna de teléfono. Se creará vacía.")
                        df_socios['telefono'] = ''
                    
                    session = SessionLocal()
                    registrados = 0
                    duplicados = 0
                    errores = 0
                    detalles = []
                    
                    for index, row in df_socios.iterrows():
                        try:
                            cupo_val = str(row['cupo']).strip()
                            nombre_val = str(row['nombre']).strip()
                            telefono_val = str(row['telefono']).strip() if pd.notna(row['telefono']) else ''
                            
                            existe = session.query(Socio).filter(Socio.cupo == cupo_val).first()
                            if existe:
                                duplicados += 1
                                detalles.append({
                                    "Cupo": cupo_val,
                                    "Nombre": nombre_val,
                                    "Teléfono": telefono_val,
                                    "Estado": f"⚠️ Duplicado (omitido) - ya existe como '{existe.nombre}'"
                                })
                            else:
                                nuevo_socio = Socio(cupo=cupo_val, nombre=nombre_val, telefono=telefono_val)
                                session.add(nuevo_socio)
                                registrados += 1
                                detalles.append({
                                    "Cupo": cupo_val,
                                    "Nombre": nombre_val,
                                    "Teléfono": telefono_val,
                                    "Estado": "✅ Registrado"
                                })
                        except Exception as e:
                            errores += 1
                            st.warning(f"Error en fila {index+2}: {str(e)}")
                    
                    session.commit()
                    session.close()
                    
                    st.success(f"✅ ¡{registrados} socios registrados exitosamente! (Duplicados omitidos: {duplicados}, Errores: {errores})")
                    if detalles:
                        df_detalle = pd.DataFrame(detalles)
                        st.subheader("📋 Detalle de la carga")
                        st.dataframe(df_detalle, use_container_width=True)
                    st.rerun()
            except Exception as e:
                st.error(f"Error al leer el archivo: {str(e)}")
    
    with tab3:
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
            st.caption(f"Total: {len(socios_db)} socios registrados.")
            
            st.divider()
            col_csv, col_pdf = st.columns(2)
            with col_csv:
                csv_data = df_socios.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button(
                    label="📥 Descargar Lista en CSV",
                    data=csv_data,
                    file_name=f"lista_socios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_pdf:
                pdf_buffer = generar_pdf_lista_socios(df_socios)
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_buffer,
                    file_name=f"lista_socios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                st.subheader("📄 Vista previa del PDF")
                mostrar_pdf_preview(pdf_buffer, key_sufijo="lista_socios")
            
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
# PÁGINA 4: PAGOS
# ==========================================
elif menu == "📜 Pagos":
    st.title("📜 Historial de Pagos")
    
    with st.expander("➕ Agregar Pago de Prueba (Solo para testing)"):
        st.info("⚠️ El sistema validará que el socio exista.")
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
                socio = session.query(Socio).filter(Socio.cupo == cupo_pago).first()
                if not socio:
                    st.error(f"❌ El socio con cupo {cupo_pago} no existe. Regístralo primero en la pestaña 'Socios'.")
                else:
                    nuevo_pago = Pago(
                        cupo=cupo_pago,
                        monto=monto_pago,
                        referencia=ref_pago,
                        estatus='Pendiente'
                    )
                    session.add(nuevo_pago)
                    session.commit()
                    st.success(f"✅ Pago de {cupo_pago} (socio: {socio.nombre}) registrado con éxito!")
                    session.close()
                    st.rerun()
                session.close()
            else:
                st.error("Todos los campos son obligatorios.")
    
    with st.expander("📤 Carga Masiva de Pagos (Sube un archivo CSV/Excel)"):
        st.info("**Nuevo flujo:**\n\n"
                "1️⃣ Sube el archivo con columnas: **Cupo**, **Monto**, **Referencia**.\n"
                "2️⃣ El sistema analizará y te mostrará qué socios NO existen.\n"
                "3️⃣ Decide si quieres crear esos socios y registrar todos los pagos, o solo registrar los pagos de socios existentes.\n\n"
                "⚠️ Si un socio no existe y no autorizas su creación, sus pagos no se registrarán.")
        
        archivo_masivo = st.file_uploader("Selecciona archivo", type=['csv', 'xlsx'], key="masivo_upload")
        
        if archivo_masivo is not None:
            if st.button("🔍 Analizar archivo", key="analizar_btn"):
                try:
                    if archivo_masivo.name.endswith('.csv'):
                        try:
                            df_masivo = pd.read_csv(archivo_masivo, encoding='utf-8-sig')
                        except:
                            df_masivo = pd.read_csv(archivo_masivo, encoding='latin-1')
                    else:
                        df_masivo = pd.read_excel(archivo_masivo)
                    
                    def normalize_column_name(col):
                        col = unicodedata.normalize('NFKD', col).encode('ascii', 'ignore').decode('utf-8')
                        return col.strip().lower()
                    
                    df_masivo.columns = [normalize_column_name(col) for col in df_masivo.columns]
                    
                    col_cupo = None
                    col_monto = None
                    col_ref = None
                    for col in df_masivo.columns:
                        if 'cupo' in col:
                            col_cupo = col
                        elif 'monto' in col or 'importe' in col:
                            col_monto = col
                        elif 'referencia' in col or 'ref' in col:
                            col_ref = col
                    
                    if col_cupo is None or col_monto is None or col_ref is None:
                        st.error("No se encontraron las columnas 'Cupo', 'Monto' y 'Referencia'. Verifica los encabezados.")
                    else:
                        df_masivo = df_masivo.rename(columns={
                            col_cupo: 'cupo',
                            col_monto: 'monto',
                            col_ref: 'referencia'
                        })
                        
                        st.subheader("📋 Vista previa del archivo")
                        st.dataframe(df_masivo.head(5), use_container_width=True)
                        
                        session = SessionLocal()
                        existentes = []
                        no_existentes = []
                        
                        for index, row in df_masivo.iterrows():
                            try:
                                cupo_val = str(row['cupo']).strip()
                                monto_val = float(str(row['monto']).replace(',', '.'))
                                ref_val = str(row['referencia']).strip()
                                
                                socio = session.query(Socio).filter(Socio.cupo == cupo_val).first()
                                if socio:
                                    existentes.append({
                                        "Cupo": cupo_val,
                                        "Socio": socio.nombre,
                                        "Monto": monto_val,
                                        "Referencia": ref_val
                                    })
                                else:
                                    no_existentes.append({
                                        "Cupo": cupo_val,
                                        "Nombre sugerido": f"Socio {cupo_val}",
                                        "Monto": monto_val,
                                        "Referencia": ref_val
                                    })
                            except Exception as e:
                                st.warning(f"Error en fila {index+2}: {str(e)}")
                        
                        session.close()
                        
                        st.session_state['existentes'] = existentes
                        st.session_state['no_existentes'] = no_existentes
                        st.session_state['analisis_realizado'] = True
                        
                        st.subheader("📊 Resumen del análisis")
                        st.info(f"Total de pagos en archivo: {len(df_masivo)}")
                        st.success(f"✅ Socios existentes: {len(existentes)}")
                        st.warning(f"⚠️ Socios NO existentes (se crearán si autorizas): {len(no_existentes)}")
                        
                        if existentes:
                            st.subheader("📋 Pagos de socios existentes (se registrarán automáticamente)")
                            st.dataframe(pd.DataFrame(existentes), use_container_width=True)
                        
                        if no_existentes:
                            st.subheader("🆕 Socios NO existentes (requieren autorización)")
                            st.dataframe(pd.DataFrame(no_existentes), use_container_width=True)
                            st.caption("Si autorizas, se crearán con nombre genérico 'Socio C-XXX' y teléfono vacío.")
                        
                        st.rerun()
                except Exception as e:
                    st.error(f"Error al leer el archivo: {str(e)}")
        
        if st.session_state.get('analisis_realizado', False):
            st.divider()
            st.subheader("📌 Acciones de registro")
            
            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.metric("Socios existentes", len(st.session_state.get('existentes', [])))
            with col_res2:
                st.metric("Socios NO existentes", len(st.session_state.get('no_existentes', [])))
            
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("📝 Registrar solo pagos de socios existentes", key="btn_existentes"):
                    existentes = st.session_state.get('existentes', [])
                    if existentes:
                        session = SessionLocal()
                        registrados = 0
                        for item in existentes:
                            nuevo_pago = Pago(
                                cupo=item["Cupo"],
                                monto=item["Monto"],
                                referencia=item["Referencia"],
                                estatus='Pendiente'
                            )
                            session.add(nuevo_pago)
                            registrados += 1
                        session.commit()
                        session.close()
                        st.success(f"✅ Se registraron {registrados} pagos de socios existentes. (Los socios faltantes fueron omitidos)")
                        st.session_state['analisis_realizado'] = False
                        st.rerun()
                    else:
                        st.info("No hay pagos de socios existentes para registrar.")
            
            with col_btn2:
                if st.button("🚀 Registrar TODOS los pagos (crear socios faltantes)", key="btn_todos"):
                    session = SessionLocal()
                    registrados = 0
                    creados = 0
                    
                    no_existentes = st.session_state.get('no_existentes', [])
                    existentes = st.session_state.get('existentes', [])
                    
                    for item in no_existentes:
                        cupo = item["Cupo"]
                        socio = session.query(Socio).filter(Socio.cupo == cupo).first()
                        if not socio:
                            nuevo_socio = Socio(cupo=cupo, nombre=f"Socio {cupo}", telefono="")
                            session.add(nuevo_socio)
                            session.flush()
                            creados += 1
                    
                    todos_pagos = existentes + no_existentes
                    for item in todos_pagos:
                        nuevo_pago = Pago(
                            cupo=item["Cupo"],
                            monto=item["Monto"],
                            referencia=item["Referencia"],
                            estatus='Pendiente'
                        )
                        session.add(nuevo_pago)
                        registrados += 1
                    
                    session.commit()
                    session.close()
                    st.success(f"✅ Se registraron {registrados} pagos y se crearon {creados} socios nuevos.")
                    st.session_state['analisis_realizado'] = False
                    st.rerun()
    
    st.divider()
    
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
                    pdf_recibo = generar_pdf_recibo(pago, socio)
                    st.download_button(
                        label="📥 Descargar Recibo PDF",
                        data=pdf_recibo,
                        file_name=f"recibo_{socio.cupo}_{pago.id}.pdf",
                        mime="application/pdf"
                    )
                    st.subheader("📄 Vista previa del Recibo")
                    mostrar_pdf_preview(pdf_recibo, key_sufijo="recibo")
                
                with col2:
                    if st.button("📨 Enviar por WhatsApp (simulado)"):
                        st.success(f"✅ Recibo enviado exitosamente al socio {socio.nombre} (simulación).")
                        st.info("En producción se enviará el PDF por WhatsApp usando Twilio.")
        else:
            st.info("No hay pagos conciliados para enviar recibos.")
        
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
                pdf_historial = generar_pdf_historial_pagos(df_pagos)
                st.session_state['pdf_pagos_data'] = pdf_historial
                st.download_button(
                    label="📥 Descargar PDF",
                    data=pdf_historial,
                    file_name=f"historial_pagos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                st.subheader("📄 Vista previa del Historial de Pagos")
                mostrar_pdf_preview(pdf_historial, key_sufijo="historial_pagos")
        
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
# PÁGINA 5: REPORTES (CON PDF EN DETALLE Y ARCHIVO DE ELIMINADOS)
# ==========================================
else:
    st.title("📊 Reportes y Conciliaciones")
    
    # --- SECCIÓN 1: HISTORIAL DE CONCILIACIONES ACTIVAS ---
    st.header("📋 Historial de Conciliaciones Activas")
    
    session = SessionLocal()
    conciliaciones = session.query(Conciliacion).order_by(Conciliacion.fecha_hora.desc()).all()
    session.close()
    
    if conciliaciones:
        # Mostrar cada conciliación con un expander
        for c in conciliaciones:
            with st.expander(f"🔹 Conciliación #{c.id} - {c.fecha_hora.strftime('%Y-%m-%d %H:%M')} (Total: {c.total_pagos} pagos, ${c.monto_total:,.2f})"):
                # Obtener los pagos asociados a esta conciliación
                session_local = SessionLocal()
                pagos_conc = session_local.query(Pago).filter(Pago.conciliacion.any(id=c.id)).all()
                session_local.close()
                
                if pagos_conc:
                    df_detalle = pd.DataFrame([{
                        "Cupo": p.cupo,
                        "Monto": p.monto,
                        "Referencia": p.referencia,
                        "Fecha Reporte": p.fecha_reporte.strftime("%Y-%m-%d %H:%M")
                    } for p in pagos_conc])
                    st.dataframe(df_detalle, use_container_width=True)
                    
                    # Botones para descargar el detalle: CSV y PDF (NUEVO)
                    st.subheader("📥 Descargar detalle de esta conciliación")
                    col_csv_det, col_pdf_det = st.columns(2)
                    with col_csv_det:
                        csv_detalle = df_detalle.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                        st.download_button(
                            label="📥 Descargar CSV",
                            data=csv_detalle,
                            file_name=f"detalle_conciliacion_{c.id}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    with col_pdf_det:
                        # Generar PDF del detalle
                        pdf_detalle_buffer = generar_pdf_detalle_conciliacion(c.id, df_detalle)
                        st.download_button(
                            label="📥 Descargar PDF",
                            data=pdf_detalle_buffer,
                            file_name=f"detalle_conciliacion_{c.id}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                        # Vista previa
                        st.subheader("📄 Vista previa del Detalle")
                        mostrar_pdf_preview(pdf_detalle_buffer, key_sufijo=f"detalle_{c.id}")
                else:
                    st.info("Esta conciliación no tiene pagos asociados (puede haber sido eliminada).")
                
                # Opción para eliminar esta conciliación (guardándola en archivo)
                st.divider()
                col1, col2 = st.columns([3, 1])
                with col2:
                    confirmar_elim = st.checkbox(f"⚠️ Marcar para archivar/eliminar conciliación #{c.id}", key=f"del_{c.id}")
                    if st.button(f"🗑️ Archivar Conciliación #{c.id}", key=f"btn_del_{c.id}", type="primary"):
                        if confirmar_elim:
                            session_del = SessionLocal()
                            conc = session_del.query(Conciliacion).get(c.id)
                            if conc:
                                # 1. Obtener los pagos para guardar el detalle en JSON
                                pagos_conc_del = session_del.query(Pago).filter(Pago.conciliacion.any(id=c.id)).all()
                                detalle_list = []
                                for p in pagos_conc_del:
                                    detalle_list.append({
                                        "Cupo": p.cupo,
                                        "Monto": p.monto,
                                        "Referencia": p.referencia,
                                        "Fecha Reporte": p.fecha_reporte.strftime("%Y-%m-%d %H:%M")
                                    })
                                detalle_json = json.dumps(detalle_list)
                                
                                # 2. Crear registro en la tabla de eliminados
                                eliminado = ConciliacionEliminada(
                                    conciliacion_id_original=c.id,
                                    fecha_hora_original=c.fecha_hora,
                                    total_pagos=c.total_pagos,
                                    monto_total=c.monto_total,
                                    detalle_pagos_json=detalle_json
                                )
                                session_del.add(eliminado)
                                session_del.flush()
                                
                                # 3. Eliminar relaciones en tabla intermedia
                                session_del.execute(conciliacion_pago.delete().where(conciliacion_pago.c.conciliacion_id == c.id))
                                # 4. Eliminar el registro original
                                session_del.delete(conc)
                                session_del.commit()
                                st.success(f"✅ Conciliación #{c.id} archivada correctamente. Ahora está disponible en 'Conciliaciones Archivadas'.")
                                st.rerun()
                            session_del.close()
                        else:
                            st.error("❌ Debes marcar la casilla de confirmación.")
        
        st.divider()
        # Resumen general en tabla
        st.subheader("📊 Resumen general de conciliaciones activas")
        data_resumen = []
        for c in conciliaciones:
            data_resumen.append({
                "ID": c.id,
                "Fecha/Hora": c.fecha_hora.strftime("%Y-%m-%d %H:%M"),
                "Total Pagos": c.total_pagos,
                "Monto Total": c.monto_total,
                "Conciliado con el banco": "✅ Sí" if c.total_pagos > 0 else "❌ No"
            })
        df_resumen = pd.DataFrame(data_resumen)
        st.dataframe(df_resumen, use_container_width=True)
        
        # Botones para descargar resumen completo
        col_csv, col_pdf = st.columns(2)
        with col_csv:
            csv_resumen = df_resumen.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            st.download_button(
                label="📥 Descargar Resumen (CSV)",
                data=csv_resumen,
                file_name=f"resumen_conciliaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        with col_pdf:
            pdf_resumen = generar_pdf_historial_conciliaciones(df_resumen)
            st.download_button(
                label="📥 Descargar Resumen (PDF)",
                data=pdf_resumen,
                file_name=f"resumen_conciliaciones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf"
            )
            st.subheader("📄 Vista previa del Resumen")
            mostrar_pdf_preview(pdf_resumen, key_sufijo="resumen")
            
    else:
        st.info("Aún no se ha realizado ninguna conciliación.")
    
    st.divider()
    
    # --- SECCIÓN 2: CONCILIACIONES ARCHIVADAS (ELIMINADAS) ---
    st.header("🗑️ Conciliaciones Archivadas (Eliminadas)")
    
    session_arch = SessionLocal()
    archivadas = session_arch.query(ConciliacionEliminada).order_by(ConciliacionEliminada.fecha_eliminacion.desc()).all()
    session_arch.close()
    
    if archivadas:
        st.info(f"Hay {len(archivadas)} conciliaciones archivadas. Estas se guardan para consulta histórica.")
        
        for arch in archivadas:
            with st.expander(f"📂 Archivo #{arch.id} (Original #{arch.conciliacion_id_original}) - Eliminado: {arch.fecha_eliminacion.strftime('%Y-%m-%d %H:%M')} (Total: {arch.total_pagos} pagos, ${arch.monto_total:,.2f})"):
                st.write(f"**Fecha original de la conciliación:** {arch.fecha_hora_original.strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**Fecha de eliminación:** {arch.fecha_eliminacion.strftime('%Y-%m-%d %H:%M')}")
                
                # Mostrar el detalle guardado en JSON
                detalle = arch.get_detalle_pagos()
                if detalle:
                    df_arch_detalle = pd.DataFrame(detalle)
                    st.dataframe(df_arch_detalle, use_container_width=True)
                    
                    # Opción para descargar el detalle archivado en CSV
                    csv_arch = df_arch_detalle.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                    st.download_button(
                        label="📥 Descargar detalle archivado (CSV)",
                        data=csv_arch,
                        file_name=f"archivo_conciliacion_{arch.id}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    # También PDF del detalle archivado
                    pdf_arch_buffer = generar_pdf_detalle_conciliacion(arch.conciliacion_id_original, df_arch_detalle)
                    st.download_button(
                        label="📥 Descargar detalle archivado (PDF)",
                        data=pdf_arch_buffer,
                        file_name=f"archivo_conciliacion_{arch.id}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.subheader("📄 Vista previa del detalle archivado")
                    mostrar_pdf_preview(pdf_arch_buffer, key_sufijo=f"arch_{arch.id}")
                else:
                    st.info("No se encontraron detalles para esta conciliación archivada.")
    else:
        st.info("No hay conciliaciones archivadas. Cuando elimines una conciliación, aparecerá aquí.")
    
    st.divider()
    
    # --- Reporte de Socios (sin cambios) ---
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
            pdf_reporte = generar_pdf_reporte_socios(df_reporte)
            st.download_button(
                label="📥 Descargar PDF",
                data=pdf_reporte,
                file_name=f"reporte_socios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf"
            )
            st.subheader("📄 Vista previa del Reporte de Socios")
            mostrar_pdf_preview(pdf_reporte, key_sufijo="reporte_socios")
    else:
        st.info("No hay socios registrados para generar el reporte.")
