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

# Cargar datos para mostrar contadores
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
    with col_socios2:
        st.write("")
        st.write("")
        st.write("")
        try:
            st.page_link("app_admin_pro.py", label="📋 Ver todos los socios", icon="👥")
        except:
            st.markdown("[📋 Ver todos los socios](#)", unsafe_allow_html=True)
    
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
# PÁGINA 3: SOCIOS (con carga masiva)
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
                        st.warning(f"⚠️ El cupo {cupo} ya está registrado con el nombre '{existe.nombre}'. No se permite duplicar.")
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
                # Leer archivo
                if archivo_socios.name.endswith('.csv'):
                    df_socios = pd.read_csv(archivo_socios, encoding='utf-8')
                else:
                    df_socios = pd.read_excel(archivo_socios)
                
                df_socios.columns = df_socios.columns.str.strip().str.lower()
                columnas_requeridas = ['cupo', 'nombre', 'telefono']
                if not all(col in df_socios.columns for col in columnas_requeridas):
                    st.error(f"El archivo debe contener las columnas: {', '.join(columnas_requeridas)} (sin importar mayúsculas).")
                else:
                    session = SessionLocal()
                    registrados = 0
                    duplicados = 0
                    errores = 0
                    detalles = []
                    
                    for index, row in df_socios.iterrows():
                        try:
                            cupo_val = str(row['cupo']).strip()
                            nombre_val = str(row['nombre']).strip()
                            telefono_val = str(row['telefono']).strip()
                            
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
                    
                    if duplicados > 0:
                        st.info("ℹ️ Los socios duplicados fueron omitidos para evitar duplicación.")
                    
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
# PÁGINA 4: PAGOS (con nuevo flujo de autorización corregido)
# ==========================================
elif menu == "📜 Pagos":
    st.title("📜 Historial de Pagos")
    
    # --- 1. CARGA MANUAL (1 a 1) ---
    with st.expander("➕ Agregar Pago de Prueba (Solo para testing)"):
        st.info("⚠️ El sistema validará que el socio exista. Si no existe, no se registrará el pago.")
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
    
    # --- 2. CARGA MASIVA CON AUTORIZACIÓN (CORREGIDA) ---
    with st.expander("📤 Carga Masiva de Pagos (Sube un archivo CSV/Excel)"):
        st.info("**Nuevo flujo:**\n\n"
                "1️⃣ Sube el archivo con columnas: **Cupo**, **Monto**, **Referencia**.\n"
                "2️⃣ El sistema analizará y te mostrará qué socios NO existen.\n"
                "3️⃣ Decide si quieres crear esos socios y registrar todos los pagos, o solo registrar los pagos de socios existentes.\n\n"
                "⚠️ Si un socio no existe y no autorizas su creación, sus pagos no se registrarán.")
        
        archivo_masivo = st.file_uploader("Selecciona archivo", type=['csv', 'xlsx'], key="masivo_upload")
        
        if archivo_masivo is not None:
            # Botón para analizar
            if st.button("🔍 Analizar archivo", key="analizar_btn"):
                try:
                    # Leer archivo
                    if archivo_masivo.name.endswith('.csv'):
                        df_masivo = pd.read_csv(archivo_masivo, encoding='utf-8')
                    else:
                        df_masivo = pd.read_excel(archivo_masivo)
                    
                    df_masivo.columns = df_masivo.columns.str.strip().str.lower()
                    columnas_requeridas = ['cupo', 'monto', 'referencia']
                    if not all(col in df_masivo.columns for col in columnas_requeridas):
                        st.error(f"El archivo debe contener las columnas: {', '.join(columnas_requeridas)} (sin importar mayúsculas).")
                    else:
                        # Procesar y clasificar
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
                        
                        # Mostrar resultados
                        st.subheader("📊 Resumen del análisis")
                        st.info(f"Total de pagos en archivo: {len(df_masivo)}")
                        st.success(f"✅ Socios existentes: {len(existentes)}")
                        st.warning(f"⚠️ Socios NO existentes (se crearán si autorizas): {len(no_existentes)}")
                        
                        if existentes:
                            st.subheader("📋 Pagos de socios existentes (se registrarán automáticamente)")
                            df_existentes = pd.DataFrame(existentes)
                            st.dataframe(df_existentes, use_container_width=True)
                        
                        if no_existentes:
                            st.subheader("🆕 Socios NO existentes (requieren autorización)")
                            df_no_existentes = pd.DataFrame(no_existentes)
                            st.dataframe(df_no_existentes, use_container_width=True)
                            st.caption("Si autorizas, se crearán con nombre genérico 'Socio C-XXX' y teléfono vacío.")
                        
                        # Guardar en session_state para usarlos en los botones
                        st.session_state['existentes'] = existentes
                        st.session_state['no_existentes'] = no_existentes
                        
                        # Botones de acción
                        st.divider()
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("📝 Registrar solo pagos de socios existentes", key="btn_existentes"):
                                if 'existentes' in st.session_state and st.session_state['existentes']:
                                    session = SessionLocal()
                                    registrados = 0
                                    for item in st.session_state['existentes']:
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
                                    st.rerun()
                                else:
                                    st.info("No hay pagos de socios existentes para registrar.")
                        
                        with col_btn2:
                            if st.button("🚀 Registrar TODOS los pagos (crear socios faltantes)", key="btn_todos"):
                                session = SessionLocal()
                                registrados = 0
                                creados = 0
                                
                                # Crear socios faltantes
                                if 'no_existentes' in st.session_state:
                                    for item in st.session_state['no_existentes']:
                                        cupo = item["Cupo"]
                                        socio = session.query(Socio).filter(Socio.cupo == cupo).first()
                                        if not socio:
                                            nuevo_socio = Socio(cupo=cupo, nombre=f"Socio {cupo}", telefono="")
                                            session.add(nuevo_socio)
                                            session.flush()
                                            creados += 1
                                
                                # Registrar todos los pagos (existentes y no existentes)
                                todos_pagos = []
                                if 'existentes' in st.session_state:
                                    todos_pagos.extend(st.session_state['existentes'])
                                if 'no_existentes' in st.session_state:
                                    todos_pagos.extend(st.session_state['no_existentes'])
                                
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
                                st.rerun()
                        
                        # Limpiar session_state después de usar (opcional)
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
