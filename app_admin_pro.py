import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from database import SessionLocal, Pago, Socio
from conciliador import ejecutar_conciliacion
import os

st.set_page_config(page_title="Llanos del Sur", page_icon="🚛", layout="wide")

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

st.sidebar.title("🚚 Menú")
menu = st.sidebar.radio("Navegación", ["📊 Dashboard", "📥 Conciliación", "👥 Socios", "📜 Pagos"])

@st.cache_data(ttl=60)
def load_data():
    session = SessionLocal()
    socios = pd.read_sql(session.query(Socio).statement, session.bind)
    pagos = pd.read_sql(session.query(Pago).statement, session.bind)
    session.close()
    return socios, pagos

socios_df, pagos_df = load_data()

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
                session.add(Socio(cupo=cupo, nombre=nombre, telefono=telefono))
                session.commit()
                session.close()
                st.success("✅ Registrado")
                st.rerun()
    st.dataframe(socios_df[['cupo', 'nombre', 'telefono']], use_container_width=True)

else:
    st.title("📜 Historial de Pagos")
    
    # --- FORMULARIO PARA AGREGAR PAGO DE PRUEBA ---
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
    # --- FIN FORMULARIO ---

    filtro = st.selectbox("Filtrar por estatus", ["Todos", "Pendiente", "Conciliado"])
    df_filtrado = pagos_df.copy()
    if filtro != "Todos":
        df_filtrado = df_filtrado[df_filtrado['estatus'] == filtro]
    st.dataframe(df_filtrado[['cupo', 'monto', 'referencia', 'estatus']], use_container_width=True)
