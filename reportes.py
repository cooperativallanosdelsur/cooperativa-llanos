from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from io import BytesIO
import pandas as pd
from datetime import datetime

def generar_pdf_reporte_socios(df_reporte):
    """Genera un PDF con el reporte de socios en formato tabla legible."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    estilo_titulo = styles['Title']
    estilo_normal = styles['Normal']
    
    contenido = []
    contenido.append(Paragraph("REPORTE DE SOCIOS - ESTADO DE PAGOS", estilo_titulo))
    contenido.append(Spacer(1, 0.5*cm))
    contenido.append(Paragraph(f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", estilo_normal))
    contenido.append(Spacer(1, 1*cm))
    
    data = [["Cupo", "Nombre", "Teléfono", "Pagado", "Pendiente", "Estado"]]
    for _, row in df_reporte.iterrows():
        data.append([
            row['Cupo'],
            row['Nombre'],
            row['Teléfono'],
            f"${row['Total Pagado']:,.2f}",
            f"${row['Total Pendiente']:,.2f}",
            row['Estado']
        ])
    
    tabla = Table(data, colWidths=[2.5*cm, 4*cm, 3*cm, 3*cm, 3*cm, 2.5*cm])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    contenido.append(tabla)
    contenido.append(Spacer(1, 2*cm))
    contenido.append(Paragraph("Cooperativa Mensajeros Llanos del Sur, R.L.", styles['Normal']))
    
    doc.build(contenido)
    buffer.seek(0)
    return buffer

def generar_pdf_recibo(pago, socio):
    """Genera un recibo individual en PDF para un pago conciliado."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    estilo_titulo = styles['Title']
    estilo_normal = styles['Normal']
    estilo_centro = ParagraphStyle('Centro', parent=styles['Normal'], alignment=1)
    
    contenido = []
    contenido.append(Paragraph("COOPERATIVA MENSAJEROS LLANOS DEL SUR", estilo_titulo))
    contenido.append(Paragraph("R.L.", estilo_centro))
    contenido.append(Spacer(1, 0.5*cm))
    contenido.append(Paragraph("RECIBO DE PAGO", styles['Heading2']))
    contenido.append(Spacer(1, 1*cm))
    
    contenido.append(Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M')}", estilo_normal))
    contenido.append(Paragraph(f"<b>Número de Cupo:</b> {socio.cupo}", estilo_normal))
    contenido.append(Paragraph(f"<b>Nombre:</b> {socio.nombre}", estilo_normal))
    contenido.append(Paragraph(f"<b>Teléfono:</b> {socio.telefono}", estilo_normal))
    contenido.append(Spacer(1, 0.5*cm))
    
    # CORREGIDO: un solo colon en el formato y FONTSIZE en lugar de FONTSTYLE
    data = [
        ["Concepto", "Referencia", "Monto"],
        [f"Pago de cuota", pago.referencia, f"${pago.monto:.2f}"]
    ]
    tabla = Table(data, colWidths=[6*cm, 4*cm, 4*cm])
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONTSIZE', (0,0), (-1,-1), 10),   # CORREGIDO
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    contenido.append(tabla)
    contenido.append(Spacer(1, 1*cm))
    contenido.append(Paragraph("Este comprobante certifica que el pago ha sido conciliado con el banco.", estilo_normal))
    contenido.append(Paragraph("¡Gracias por su puntualidad!", estilo_normal))
    contenido.append(Spacer(1, 2*cm))
    contenido.append(Paragraph("_______________________", estilo_centro))  # Línea de firma
    contenido.append(Paragraph("Firma autorizada", estilo_centro))
    
    doc.build(contenido)
    buffer.seek(0)
    return buffer
