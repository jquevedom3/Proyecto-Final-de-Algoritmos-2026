"""
NexusGT - Sistema inteligente para la gestión y control de gastos empresariales
Versión inicial académica.

Funciones:
- Registro manual de gastos.
- Base de datos SQLite.
- Búsqueda y filtros.
- Reporte por categoría y período.
- Detección de posibles duplicados.
- Presupuesto mensual por categoría.
- Lectura OCR opcional de imágenes de facturas.

Requisitos:
- Python 3.10 o superior recomendado.
- OCR opcional: pip install pillow pytesseract
- También debe instalarse Tesseract OCR en el sistema operativo para usar OCR.
"""

import os
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime
from collections import defaultdict

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "nexusgt.db")

CATEGORIAS = [
    "Combustible", "Alimentación", "Hospedaje", "Transporte",
    "Materiales", "Oficina", "Servicios", "Otros"
]
METODOS = ["Manual", "OCR"]
CAMPOS = [
    "proveedor", "nit", "fecha", "numero_factura", "categoria",
    "subtotal", "iva", "total", "metodo", "observaciones"
]


def conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_bd():
    with conectar() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proveedor TEXT NOT NULL,
                nit TEXT DEFAULT '',
                fecha TEXT NOT NULL,
                numero_factura TEXT DEFAULT '',
                categoria TEXT NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                iva REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL,
                metodo TEXT NOT NULL DEFAULT 'Manual',
                observaciones TEXT DEFAULT '',
                fecha_creacion TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS presupuestos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mes TEXT NOT NULL,
                categoria TEXT NOT NULL,
                monto REAL NOT NULL,
                UNIQUE(mes, categoria)
            )
        """)


def dinero(valor):
    try:
        return f"Q {float(valor):,.2f}"
    except (ValueError, TypeError):
        return "Q 0.00"


def validar_fecha(texto):
    try:
        datetime.strptime(texto, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def posibles_duplicados(proveedor, numero, fecha, total, excluir_id=None):
    consulta = """
        SELECT id, proveedor, numero_factura, fecha, total
        FROM gastos
        WHERE lower(trim(proveedor)) = lower(trim(?))
          AND fecha = ?
          AND abs(total - ?) < 0.01
    """
    parametros = [proveedor, fecha, total]
    if numero.strip():
        consulta += " AND numero_factura = ?"
        parametros.append(numero.strip())
    if excluir_id is not None:
        consulta += " AND id != ?"
        parametros.append(excluir_id)
    with conectar() as conn:
        return conn.execute(consulta, parametros).fetchall()


class NexusGTApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NexusGT | Gestión y control de gastos")
        self.root.geometry("1180x760")
        self.root.minsize(980, 650)
        self.ocr_texto = ""

        self.estilo = ttk.Style()
        try:
            self.estilo.theme_use("clam")
        except tk.TclError:
            pass

        self.crear_interfaz()
        self.refrescar_gastos()
        self.refrescar_resumen()

    def crear_interfaz(self):
        encabezado = ttk.Frame(self.root, padding=(16, 12))
        encabezado.pack(fill="x")
        ttk.Label(
            encabezado, text="NexusGT",
            font=("Arial", 22, "bold")
        ).pack(anchor="w")
        ttk.Label(
            encabezado,
            text="Sistema inteligente para la gestión y control de gastos empresariales"
        ).pack(anchor="w", pady=(2, 0))

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.tab_registro = ttk.Frame(self.tabs, padding=12)
        self.tab_gastos = ttk.Frame(self.tabs, padding=12)
        self.tab_reportes = ttk.Frame(self.tabs, padding=12)
        self.tab_presupuesto = ttk.Frame(self.tabs, padding=12)

        self.tabs.add(self.tab_registro, text="Registrar gasto")
        self.tabs.add(self.tab_gastos, text="Consultar gastos")
        self.tabs.add(self.tab_reportes, text="Reportes")
        self.tabs.add(self.tab_presupuesto, text="Presupuestos")

        self.crear_tab_registro()
        self.crear_tab_gastos()
        self.crear_tab_reportes()
        self.crear_tab_presupuesto()

    def crear_tab_registro(self):
        frame = self.tab_registro
        ttk.Label(
            frame, text="Datos del gasto",
            font=("Arial", 14, "bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 12))

        self.vars = {
            "proveedor": tk.StringVar(),
            "nit": tk.StringVar(),
            "fecha": tk.StringVar(value=date.today().isoformat()),
            "numero_factura": tk.StringVar(),
            "categoria": tk.StringVar(value=CATEGORIAS[0]),
            "subtotal": tk.StringVar(value="0.00"),
            "iva": tk.StringVar(value="0.00"),
            "total": tk.StringVar(value="0.00"),
            "metodo": tk.StringVar(value="Manual"),
            "observaciones": tk.StringVar(),
        }

        def campo(etiqueta, clave, fila, columna, ancho=32):
            ttk.Label(frame, text=etiqueta).grid(
                row=fila, column=columna, sticky="w", padx=(0, 8), pady=6
            )
            entrada = ttk.Entry(frame, textvariable=self.vars[clave], width=ancho)
            entrada.grid(row=fila, column=columna + 1, sticky="ew", padx=(0, 18), pady=6)
            return entrada

        campo("Proveedor *", "proveedor", 1, 0)
        campo("NIT", "nit", 1, 2)
        campo("Fecha (AAAA-MM-DD) *", "fecha", 2, 0)
        campo("Número de factura", "numero_factura", 2, 2)

        ttk.Label(frame, text="Categoría *").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Combobox(
            frame, textvariable=self.vars["categoria"], values=CATEGORIAS,
            state="readonly", width=29
        ).grid(row=3, column=1, sticky="ew", padx=(0, 18), pady=6)

        ttk.Label(frame, text="Método de registro").grid(row=3, column=2, sticky="w", pady=6)
        ttk.Combobox(
            frame, textvariable=self.vars["metodo"], values=METODOS,
            state="readonly", width=29
        ).grid(row=3, column=3, sticky="ew", padx=(0, 18), pady=6)

        campo("Subtotal (Q) *", "subtotal", 4, 0)
        campo("IVA (Q)", "iva", 4, 2)
        campo("Total (Q) *", "total", 5, 0)
        campo("Observaciones", "observaciones", 5, 2)

        botones = ttk.Frame(frame)
        botones.grid(row=6, column=0, columnspan=4, sticky="w", pady=14)
        ttk.Button(botones, text="Guardar gasto", command=self.guardar_gasto).pack(side="left", padx=(0, 8))
        ttk.Button(botones, text="Limpiar formulario", command=self.limpiar_formulario).pack(side="left", padx=(0, 8))
        ttk.Button(botones, text="Cargar factura con OCR", command=self.cargar_ocr).pack(side="left")

        self.ocr_estado = tk.StringVar(value="OCR opcional: selecciona una imagen para intentar extraer datos.")
        ttk.Label(
            frame, textvariable=self.ocr_estado, wraplength=850
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=(8, 0))

        ttk.Label(
            frame,
            text="Nota: revisa siempre los datos extraídos por OCR antes de guardar.",
            foreground="#555555"
        ).grid(row=8, column=0, columnspan=4, sticky="w", pady=(8, 0))

        for col in (1, 3):
            frame.columnconfigure(col, weight=1)

    def limpiar_formulario(self):
        for clave, variable in self.vars.items():
            variable.set("")
        self.vars["fecha"].set(date.today().isoformat())
        self.vars["categoria"].set(CATEGORIAS[0])
        self.vars["subtotal"].set("0.00")
        self.vars["iva"].set("0.00")
        self.vars["total"].set("0.00")
        self.vars["metodo"].set("Manual")
        self.ocr_estado.set("Formulario listo para un nuevo gasto.")
        self.ocr_texto = ""

    def guardar_gasto(self):
        proveedor = self.vars["proveedor"].get().strip()
        nit = self.vars["nit"].get().strip()
        fecha = self.vars["fecha"].get().strip()
        numero = self.vars["numero_factura"].get().strip()
        categoria = self.vars["categoria"].get().strip()
        metodo = self.vars["metodo"].get().strip()
        observaciones = self.vars["observaciones"].get().strip()

        if not proveedor:
            messagebox.showerror("Dato requerido", "Ingresa el nombre del proveedor.")
            return
        if not validar_fecha(fecha):
            messagebox.showerror("Fecha inválida", "Usa el formato AAAA-MM-DD, por ejemplo 2026-10-14.")
            return
        if categoria not in CATEGORIAS:
            messagebox.showerror("Categoría inválida", "Selecciona una categoría de la lista.")
            return

        try:
            subtotal = float(self.vars["subtotal"].get().replace(",", ""))
            iva = float(self.vars["iva"].get().replace(",", ""))
            total = float(self.vars["total"].get().replace(",", ""))
            if subtotal < 0 or iva < 0 or total < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Montos inválidos", "Subtotal, IVA y total deben ser números iguales o mayores que cero.")
            return

        duplicados = posibles_duplicados(proveedor, numero, fecha, total)
        if duplicados:
            ids = ", ".join(str(row["id"]) for row in duplicados)
            continuar = messagebox.askyesno(
                "Posible duplicado",
                f"Ya existe un gasto parecido (ID: {ids}).\n"
                "¿Deseas guardar este registro de todos modos?"
            )
            if not continuar:
                return

        with conectar() as conn:
            conn.execute("""
                INSERT INTO gastos
                (proveedor, nit, fecha, numero_factura, categoria, subtotal,
                 iva, total, metodo, observaciones, fecha_creacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proveedor, nit, fecha, numero, categoria, subtotal, iva, total,
                metodo, observaciones, datetime.now().isoformat(timespec="seconds")
            ))

        messagebox.showinfo("NexusGT", "El gasto se guardó correctamente.")
        self.limpiar_formulario()
        self.refrescar_gastos()
        self.refrescar_resumen()

    def cargar_ocr(self):
        ruta = filedialog.askopenfilename(
            title="Seleccionar imagen de factura",
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("Todos los archivos", "*.*")
            ]
        )
        if not ruta:
            return

        try:
            from PIL import Image
            import pytesseract
            texto = pytesseract.image_to_string(Image.open(ruta), lang="spa")
        except ImportError:
            messagebox.showwarning(
                "Falta instalar OCR",
                "Para usar OCR instala las dependencias con:\n\n"
                "pip install pillow pytesseract\n\n"
                "También necesitas instalar Tesseract OCR en tu computadora."
            )
            return
        except Exception as exc:
            messagebox.showerror(
                "No se pudo leer la imagen",
                "Verifica que Tesseract OCR esté instalado y configurado.\n\n"
                f"Detalle: {exc}"
            )
            return

        self.ocr_texto = texto
        self.vars["metodo"].set("OCR")

        # Extracción heurística: los formatos de factura varían y requieren revisión humana.
        lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
        if lineas and not self.vars["proveedor"].get().strip():
            self.vars["proveedor"].set(lineas[0][:120])

        nit_match = re.search(r"\bNIT\s*[:#]?\s*([0-9Kk-]{4,})", texto, re.IGNORECASE)
        if nit_match:
            self.vars["nit"].set(nit_match.group(1))

        fecha_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", texto)
        if fecha_match:
            anio, mes, dia = fecha_match.groups()
            try:
                self.vars["fecha"].set(date(int(anio), int(mes), int(dia)).isoformat())
            except ValueError:
                pass
        else:
            fecha_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", texto)
            if fecha_match:
                dia, mes, anio = fecha_match.groups()
                try:
                    self.vars["fecha"].set(date(int(anio), int(mes), int(dia)).isoformat())
                except ValueError:
                    pass

        total_match = re.search(
            r"(?:TOTAL(?:\s+A\s+PAGAR)?|GRAN TOTAL)\s*[:Q$]?\s*([0-9,]+(?:\.[0-9]{2})?)",
            texto, re.IGNORECASE
        )
        if total_match:
            try:
                total = float(total_match.group(1).replace(",", ""))
                self.vars["total"].set(f"{total:.2f}")
            except ValueError:
                pass

        messagebox.showinfo(
            "OCR completado",
            "Se procesó la imagen. Se intentaron identificar algunos campos.\n"
            "Revisa y corrige todos los datos antes de guardar.\n\n"
            "El reconocimiento depende de la calidad y el formato de la factura."
        )
        self.ocr_estado.set(f"Imagen procesada: {os.path.basename(ruta)}. Revisa los datos detectados.")

    def crear_tab_gastos(self):
        filtros = ttk.LabelFrame(self.tab_gastos, text="Filtros de búsqueda", padding=10)
        filtros.pack(fill="x", pady=(0, 10))

        self.f_proveedor = tk.StringVar()
        self.f_categoria = tk.StringVar(value="Todas")
        self.f_desde = tk.StringVar()
        self.f_hasta = tk.StringVar()

        ttk.Label(filtros, text="Proveedor").grid(row=0, column=0, sticky="w")
        ttk.Entry(filtros, textvariable=self.f_proveedor, width=22).grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Label(filtros, text="Categoría").grid(row=0, column=2, sticky="w", padx=(10, 0))
        ttk.Combobox(
            filtros, textvariable=self.f_categoria, values=["Todas"] + CATEGORIAS,
            state="readonly", width=18
        ).grid(row=0, column=3, padx=6)
        ttk.Label(filtros, text="Desde (AAAA-MM-DD)").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(filtros, textvariable=self.f_desde, width=22).grid(row=1, column=1, padx=6, pady=(8, 0), sticky="ew")
        ttk.Label(filtros, text="Hasta (AAAA-MM-DD)").grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(8, 0))
        ttk.Entry(filtros, textvariable=self.f_hasta, width=22).grid(row=1, column=3, padx=6, pady=(8, 0))
        ttk.Button(filtros, text="Buscar", command=self.refrescar_gastos).grid(row=0, column=4, padx=8)
        ttk.Button(filtros, text="Limpiar filtros", command=self.limpiar_filtros).grid(row=1, column=4, padx=8, pady=(8, 0))

        columnas = ("id", "fecha", "proveedor", "nit", "factura", "categoria", "total", "metodo")
        self.tabla = ttk.Treeview(self.tab_gastos, columns=columnas, show="headings", height=17)
        titulos = {
            "id": "ID", "fecha": "Fecha", "proveedor": "Proveedor", "nit": "NIT",
            "factura": "Factura", "categoria": "Categoría", "total": "Total (Q)", "metodo": "Método"
        }
        anchos = {"id": 50, "fecha": 100, "proveedor": 180, "nit": 100, "factura": 120,
                  "categoria": 130, "total": 110, "metodo": 80}
        for col in columnas:
            self.tabla.heading(col, text=titulos[col])
            self.tabla.column(col, width=anchos[col], anchor="w")
        self.tabla.pack(fill="both", expand=True)

        abajo = ttk.Frame(self.tab_gastos)
        abajo.pack(fill="x", pady=(8, 0))
        self.total_filtrado = tk.StringVar(value="Total mostrado: Q 0.00")
        ttk.Label(abajo, textvariable=self.total_filtrado, font=("Arial", 10, "bold")).pack(side="left")
        ttk.Button(abajo, text="Ver detalle", command=self.ver_detalle).pack(side="right", padx=(6, 0))
        ttk.Button(abajo, text="Exportar CSV", command=self.exportar_csv).pack(side="right")

    def limpiar_filtros(self):
        self.f_proveedor.set("")
        self.f_categoria.set("Todas")
        self.f_desde.set("")
        self.f_hasta.set("")
        self.refrescar_gastos()

    def obtener_gastos_filtrados(self):
        consulta = "SELECT * FROM gastos WHERE 1=1"
        params = []
        proveedor = self.f_proveedor.get().strip()
        categoria = self.f_categoria.get()
        desde = self.f_desde.get().strip()
        hasta = self.f_hasta.get().strip()

        if proveedor:
            consulta += " AND proveedor LIKE ?"
            params.append(f"%{proveedor}%")
        if categoria and categoria != "Todas":
            consulta += " AND categoria = ?"
            params.append(categoria)
        if desde:
            if not validar_fecha(desde):
                raise ValueError("La fecha 'Desde' debe tener formato AAAA-MM-DD.")
            consulta += " AND fecha >= ?"
            params.append(desde)
        if hasta:
            if not validar_fecha(hasta):
                raise ValueError("La fecha 'Hasta' debe tener formato AAAA-MM-DD.")
            consulta += " AND fecha <= ?"
            params.append(hasta)
        consulta += " ORDER BY fecha DESC, id DESC"
        with conectar() as conn:
            return conn.execute(consulta, params).fetchall()

    def refrescar_gastos(self):
        if not hasattr(self, "tabla"):
            return
        try:
            filas = self.obtener_gastos_filtrados()
        except ValueError as exc:
            messagebox.showerror("Filtro inválido", str(exc))
            return
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        total = 0
        for g in filas:
            total += g["total"]
            self.tabla.insert("", "end", values=(
                g["id"], g["fecha"], g["proveedor"], g["nit"],
                g["numero_factura"], g["categoria"], f'{g["total"]:.2f}', g["metodo"]
            ))
        self.total_filtrado.set(f"Registros: {len(filas)} | Total mostrado: {dinero(total)}")

    def gasto_seleccionado(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            messagebox.showwarning("Selecciona un gasto", "Selecciona un registro en la tabla.")
            return None
        valores = self.tabla.item(seleccion[0], "values")
        with conectar() as conn:
            return conn.execute("SELECT * FROM gastos WHERE id = ?", (valores[0],)).fetchone()

    def ver_detalle(self):
        g = self.gasto_seleccionado()
        if not g:
            return
        mensaje = (
            f'ID: {g["id"]}\nProveedor: {g["proveedor"]}\nNIT: {g["nit"]}\n'
            f'Fecha: {g["fecha"]}\nFactura: {g["numero_factura"]}\n'
            f'Categoría: {g["categoria"]}\nSubtotal: {dinero(g["subtotal"])}\n'
            f'IVA: {dinero(g["iva"])}\nTotal: {dinero(g["total"])}\n'
            f'Método: {g["metodo"]}\nObservaciones: {g["observaciones"]}'
        )
        messagebox.showinfo("Detalle del gasto", mensaje)

    def exportar_csv(self):
        try:
            filas = self.obtener_gastos_filtrados()
        except ValueError as exc:
            messagebox.showerror("Filtro inválido", str(exc))
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar reporte CSV", defaultextension=".csv",
            filetypes=[("Archivo CSV", "*.csv")]
        )
        if not ruta:
            return
        import csv
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow([
                "ID", "Proveedor", "NIT", "Fecha", "Número de factura", "Categoría",
                "Subtotal", "IVA", "Total", "Método", "Observaciones"
            ])
            for g in filas:
                escritor.writerow([g[c] for c in (
                    "id", "proveedor", "nit", "fecha", "numero_factura", "categoria",
                    "subtotal", "iva", "total", "metodo", "observaciones"
                )])
        messagebox.showinfo("Exportación", f"Reporte exportado correctamente:\n{ruta}")

    def crear_tab_reportes(self):
        frame = self.tab_reportes
        ttk.Label(frame, text="Resumen de gastos", font=("Arial", 14, "bold")).pack(anchor="w")
        filtros = ttk.Frame(frame)
        filtros.pack(fill="x", pady=10)

        self.r_desde = tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.r_hasta = tk.StringVar(value=date.today().isoformat())
        ttk.Label(filtros, text="Desde").pack(side="left")
        ttk.Entry(filtros, textvariable=self.r_desde, width=14).pack(side="left", padx=6)
        ttk.Label(filtros, text="Hasta").pack(side="left", padx=(10, 0))
        ttk.Entry(filtros, textvariable=self.r_hasta, width=14).pack(side="left", padx=6)
        ttk.Button(filtros, text="Generar reporte", command=self.generar_reporte).pack(side="left", padx=8)

        self.resumen_texto = tk.Text(frame, height=22, wrap="word", state="disabled")
        self.resumen_texto.pack(fill="both", expand=True)
        self.generar_reporte()

    def generar_reporte(self):
        desde = self.r_desde.get().strip()
        hasta = self.r_hasta.get().strip()
        if not validar_fecha(desde) or not validar_fecha(hasta):
            messagebox.showerror("Fechas inválidas", "Usa el formato AAAA-MM-DD en ambas fechas.")
            return
        if desde > hasta:
            messagebox.showerror("Período inválido", "La fecha inicial no puede ser posterior a la fecha final.")
            return

        with conectar() as conn:
            gastos = conn.execute(
                "SELECT * FROM gastos WHERE fecha >= ? AND fecha <= ? ORDER BY fecha",
                (desde, hasta)
            ).fetchall()

        total = sum(g["total"] for g in gastos)
        por_categoria = defaultdict(float)
        por_proveedor = defaultdict(float)
        for g in gastos:
            por_categoria[g["categoria"]] += g["total"]
            por_proveedor[g["proveedor"]] += g["total"]

        lineas = [
            f"PERÍODO: {desde} a {hasta}",
            "=" * 52,
            f"Cantidad de gastos: {len(gastos)}",
            f"Gasto total: {dinero(total)}",
            "",
            "GASTOS POR CATEGORÍA",
            "-" * 52
        ]
        if por_categoria:
            for categoria, monto in sorted(por_categoria.items(), key=lambda x: x[1], reverse=True):
                porcentaje = (monto / total * 100) if total else 0
                lineas.append(f"{categoria}: {dinero(monto)} ({porcentaje:.1f}%)")
        else:
            lineas.append("No hay gastos registrados en este período.")

        lineas.extend(["", "PRINCIPALES PROVEEDORES", "-" * 52])
        if por_proveedor:
            for proveedor, monto in sorted(por_proveedor.items(), key=lambda x: x[1], reverse=True)[:10]:
                lineas.append(f"{proveedor}: {dinero(monto)}")
        else:
            lineas.append("Sin datos.")

        if por_categoria:
            categoria_mayor, monto_mayor = max(por_categoria.items(), key=lambda x: x[1])
            lineas.extend(["", f"Categoría con mayor gasto: {categoria_mayor} ({dinero(monto_mayor)})"])

        self.resumen_texto.configure(state="normal")
        self.resumen_texto.delete("1.0", "end")
        self.resumen_texto.insert("1.0", "\n".join(lineas))
        self.resumen_texto.configure(state="disabled")

    def crear_tab_presupuesto(self):
        frame = self.tab_presupuesto
        ttk.Label(frame, text="Control básico de presupuesto mensual", font=("Arial", 14, "bold")).pack(anchor="w")
        formulario = ttk.Frame(frame)
        formulario.pack(fill="x", pady=12)

        self.p_mes = tk.StringVar(value=date.today().strftime("%Y-%m"))
        self.p_categoria = tk.StringVar(value=CATEGORIAS[0])
        self.p_monto = tk.StringVar()

        ttk.Label(formulario, text="Mes (AAAA-MM)").grid(row=0, column=0, sticky="w")
        ttk.Entry(formulario, textvariable=self.p_mes, width=14).grid(row=0, column=1, padx=6)
        ttk.Label(formulario, text="Categoría").grid(row=0, column=2, padx=(12, 0), sticky="w")
        ttk.Combobox(
            formulario, textvariable=self.p_categoria, values=CATEGORIAS,
            state="readonly", width=18
        ).grid(row=0, column=3, padx=6)
        ttk.Label(formulario, text="Presupuesto (Q)").grid(row=0, column=4, padx=(12, 0), sticky="w")
        ttk.Entry(formulario, textvariable=self.p_monto, width=14).grid(row=0, column=5, padx=6)
        ttk.Button(formulario, text="Guardar presupuesto", command=self.guardar_presupuesto).grid(row=0, column=6, padx=6)

        ttk.Button(frame, text="Actualizar estado", command=self.refrescar_presupuestos).pack(anchor="w", pady=(0, 8))
        columnas = ("categoria", "presupuesto", "gastado", "disponible", "estado")
        self.tabla_presupuesto = ttk.Treeview(frame, columns=columnas, show="headings", height=16)
        for col, titulo, ancho in [
            ("categoria", "Categoría", 200), ("presupuesto", "Presupuesto (Q)", 160),
            ("gastado", "Gastado (Q)", 160), ("disponible", "Disponible (Q)", 160),
            ("estado", "Estado", 180)
        ]:
            self.tabla_presupuesto.heading(col, text=titulo)
            self.tabla_presupuesto.column(col, width=ancho, anchor="w")
        self.tabla_presupuesto.pack(fill="both", expand=True)
        self.refrescar_presupuestos()

    def guardar_presupuesto(self):
        mes = self.p_mes.get().strip()
        categoria = self.p_categoria.get()
        try:
            datetime.strptime(mes, "%Y-%m")
            monto = float(self.p_monto.get().replace(",", ""))
            if monto <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Datos inválidos",
                "Ingresa un mes válido (AAAA-MM) y un presupuesto numérico mayor que cero."
            )
            return

        with conectar() as conn:
            conn.execute("""
                INSERT INTO presupuestos (mes, categoria, monto)
                VALUES (?, ?, ?)
                ON CONFLICT(mes, categoria) DO UPDATE SET monto = excluded.monto
            """, (mes, categoria, monto))
        self.p_monto.set("")
        self.refrescar_presupuestos()
        messagebox.showinfo("Presupuesto", "Presupuesto guardado correctamente.")

    def refrescar_presupuestos(self):
        if not hasattr(self, "tabla_presupuesto"):
            return
        for item in self.tabla_presupuesto.get_children():
            self.tabla_presupuesto.delete(item)
        with conectar() as conn:
            presupuestos = conn.execute(
                "SELECT * FROM presupuestos ORDER BY mes DESC, categoria"
            ).fetchall()
            gastos = conn.execute("""
                SELECT substr(fecha, 1, 7) AS mes, categoria, SUM(total) AS gastado
                FROM gastos GROUP BY substr(fecha, 1, 7), categoria
            """).fetchall()
        gastado_por = {(g["mes"], g["categoria"]): g["gastado"] for g in gastos}

        for p in presupuestos:
            gastado = gastado_por.get((p["mes"], p["categoria"]), 0.0)
            disponible = p["monto"] - gastado
            if gastado > p["monto"]:
                estado = "Presupuesto excedido"
            elif gastado >= p["monto"] * 0.8:
                estado = "Cerca del límite (80%+)"
            else:
                estado = "Dentro del presupuesto"
            self.tabla_presupuesto.insert("", "end", values=(
                f'{p["mes"]} | {p["categoria"]}',
                f'{p["monto"]:.2f}', f'{gastado:.2f}',
                f'{disponible:.2f}', estado
            ))

    def refrescar_resumen(self):
        # Mantiene los reportes y presupuesto actualizados después de guardar.
        if hasattr(self, "resumen_texto"):
            self.generar_reporte()
        if hasattr(self, "tabla_presupuesto"):
            self.refrescar_presupuestos()


def main():
    inicializar_bd()
    root = tk.Tk()
    NexusGTApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
