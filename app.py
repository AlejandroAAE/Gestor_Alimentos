import streamlit as st
import sqlite3
from datetime import datetime
import re
from st_audiorec import st_audiorec
import speech_recognition as sr
from datetime import timedelta
import tempfile
import pytesseract
from PIL import Image
from pyzbar.pyzbar import decode





# Conexión con la base de datos
conn = sqlite3.connect('alimentos.db', check_same_thread=False)
cursor = conn.cursor()

# Crear tabla alimentos si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS alimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        fecha_caducidad DATE NOT NULL,
        cantidad TEXT DEFAULT 'Entero'
    )
''')

# Crear tabla eliminados si no existe
cursor.execute('''
    CREATE TABLE IF NOT EXISTS eliminados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        fecha_eliminado DATE NOT NULL
    )
''')

# Comprobar si la columna 'etiquetas' existe antes de añadirla
cursor.execute("PRAGMA table_info(alimentos)")
columnas = [col[1] for col in cursor.fetchall()]
if "etiquetas" not in columnas:
    cursor.execute("ALTER TABLE alimentos ADD COLUMN etiquetas TEXT")



conn.commit()

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}


if 'refrescar' not in st.session_state:
    st.session_state.refrescar = False

def limpiar_nombre(nombre):
    nombre = nombre.strip()
    nombre = re.sub(r"^(el|la|los|las|un|una|unos|unas)\s+", "", nombre, flags=re.IGNORECASE)
    nombre = re.sub(r"\s+que$", "", nombre, flags=re.IGNORECASE)
    return nombre.strip().title()


# Función para normalizar nombre
def normalizar(nombre):
    return nombre.strip().title()

# Función para mostrar alimentos
def ver_alimentos():
    cursor.execute('SELECT id, nombre, fecha_caducidad, cantidad FROM alimentos ORDER BY fecha_caducidad ASC')
    return cursor.fetchall()

# Función para agregar alimento
def agregar_alimento(nombre, fecha, cantidad, etiquetas=""):
    nombre = normalizar(nombre)
    cursor.execute(
        'INSERT INTO alimentos (nombre, fecha_caducidad, cantidad, etiquetas) VALUES (?, ?, ?, ?)',
        (nombre, fecha, cantidad, etiquetas)
    )
    conn.commit()


def eliminar_alimento(id_alimento):
    cursor.execute('SELECT nombre FROM alimentos WHERE id = ?', (id_alimento,))
    fila = cursor.fetchone()
    if fila:
        nombre = fila[0]
        fecha_eliminado = datetime.now().date()
        cursor.execute('INSERT INTO eliminados (nombre, fecha_eliminado) VALUES (?, ?)', (nombre, fecha_eliminado))
    cursor.execute('DELETE FROM alimentos WHERE id = ?', (id_alimento,))
    conn.commit()


def actualizar_cantidad(id_alimento, nueva_cantidad):
    cursor.execute('UPDATE alimentos SET cantidad = ? WHERE id = ?', (nueva_cantidad, id_alimento))
    conn.commit()


def extraer_datos(texto):
    try:
        print(f"[LOG] Texto recibido: {texto}")
        texto = texto.lower()

        patron = r"(.*?)\s*caduca el (\d{1,2}) (?:de|del) (\d{1,2}|\w+)(?: (?:de|del) (\d{2,4}))?"
        coincidencias = re.search(patron, texto)

        print(f"[LOG] Coincidencias encontradas: {coincidencias.groups() if coincidencias else 'Ninguna'}")

        if coincidencias:
            nombre_alimento = limpiar_nombre(coincidencias.group(1))
            dia = int(coincidencias.group(2))
            mes_raw = coincidencias.group(3)
            anio_raw = coincidencias.group(4)

            print(f"[LOG] Alimento: '{nombre_alimento}', Día: {dia}, Mes bruto: '{mes_raw}', Año bruto: '{anio_raw}'")

            # Convertir mes
            mes = None
            if mes_raw.isdigit():
                mes = int(mes_raw)
                print(f"[LOG] Mes interpretado como número: {mes}")
            else:
                mes = convertir_palabra_a_numero(mes_raw)
                print(f"[LOG] Mes interpretado desde palabra: {mes}")

            if not mes or not (1 <= mes <= 12):
                raise ValueError(f"Mes inválido: '{mes_raw}' interpretado como {mes}")

            if anio_raw:
                anio = int(anio_raw)
                if anio < 100:
                    anio += 2000
            else:
                anio = datetime.now().year

            print(f"[LOG] Año final: {anio}")

            fecha = datetime(anio, mes, dia).date()
            print(f"[LOG] Fecha construida correctamente: {fecha}")

            return nombre_alimento, fecha

    except Exception as e:
        print(f"[ERROR] Fallo en extraer_datos: {e}")

    return None, None





def agregar_a_lista_compra(nombre):
    nombre = normalizar(nombre)
    fecha = datetime.now().date()
    cursor.execute('INSERT INTO eliminados (nombre, fecha_eliminado) VALUES (?, ?)', (nombre, fecha))
    conn.commit()





def convertir_palabra_a_numero(palabra):
    numeros = {
        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
        "septiembre": 9, "setiembre": 9, "octubre": 10,
        "noviembre": 11, "diciembre": 12
    }

    palabra = palabra.strip().lower()

    # Log: intento de conversión de palabra
    print(f"[LOG] Intentando convertir mes: '{palabra}'")

    numero = re.sub(r"[^\d]", "", palabra)
    if numero.isdigit():
        print(f"[LOG] Mes detectado como número: {numero}")
        return int(numero)

    result = numeros.get(palabra)
    print(f"[LOG] Resultado de conversión de palabra a número: {result}")
    return result


st.sidebar.title("Menú")
pagina = st.sidebar.selectbox("Ir a:", [
    "📋 Alimentos próximos a caducar", "🍽️ Añadir alimentos",
    "🛒 Lista de la compra"

])

if pagina == "📋 Alimentos próximos a caducar":


    # Interfaz: Mostrar alimentos con editar y eliminar
    st.title("📋 Alimentos próximos a caducar")

    alimentos = ver_alimentos()

    # Aviso de alimentos próximos a caducar (incluso si es otro mes)
    hoy = datetime.now().date()
    proximos = []
    for _, nombre, fecha, _ in alimentos:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        dias_restantes = (fecha_obj - hoy).days
        if 0 <= dias_restantes <= 7:
            proximos.append(f"• {nombre} (caduca en {dias_restantes} días)")

    if proximos:
        st.warning("⚠️ Alimentos que caducan pronto:\n" + "\n".join(proximos))

    # Filtro por nombre
    filtro = st.text_input("🔍 Buscar alimento por nombre").strip().lower()
    filtro_etiqueta = st.text_input("🏷️ Filtrar por etiqueta (ej. lácteo)").strip().lower()

    # Mostrar alimentos con filtro aplicado
    filtrados = []
    for id_alimento, nombre, fecha, cantidad in alimentos:
        cursor.execute('SELECT etiquetas FROM alimentos WHERE id = ?', (id_alimento,))
        row = cursor.fetchone()
        etiquetas = row[0].lower() if row and row[0] else ""

        if filtro in nombre.lower() and (filtro_etiqueta in etiquetas if filtro_etiqueta else True):
            filtrados.append((id_alimento, nombre, fecha, cantidad))

    if filtrados:


        for id_alimento, nombre, fecha, cantidad in filtrados:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            dias_restantes = (fecha_obj - datetime.now().date()).days



            # Determinar ícono y color
            if dias_restantes > 7:
                icono = "🟢"
                color = "green"
                mensaje = f"Faltan <strong>{dias_restantes} días</strong>"
            elif 0 <= dias_restantes <= 7:
                icono = "🟡"
                color = "orange"
                mensaje = f"Faltan <strong>{dias_restantes} días</strong>"
            elif -2 <= dias_restantes < 0:
                icono = "🔴"
                color = "red"
                mensaje = f"Caducado hace <strong>{abs(dias_restantes)} días</strong>"
            else:
                icono = "❌"
                color = "black"
                mensaje = f"Caducado hace <strong>{abs(dias_restantes)} días</strong>"

            cols = st.columns([4, 1, 1])
            with cols[0]:

                st.markdown(
                    f"<span style='color:{color}'>{icono} **{nombre}** – {fecha_obj.strftime('%d-%m')} – {cantidad} – {mensaje} – <em>{etiquetas}</em></span>",
                    unsafe_allow_html=True
                )

            with cols[1]:
                if st.button("Editar", key=f"edit_{id_alimento}"):
                    st.session_state[f"editando_{id_alimento}"] = True

            with cols[2]:
                if st.button("Eliminar", key=f"del_{id_alimento}"):
                    eliminar_alimento(id_alimento)
                    st.rerun()

            if st.session_state.get(f"editando_{id_alimento}", False):
                nueva_cantidad = st.text_input(f"Cambiar cantidad de {nombre}", value=cantidad,
                                               key=f"input_{id_alimento}")
                if st.button("Guardar", key=f"guardar_{id_alimento}"):
                    actualizar_cantidad(id_alimento, nueva_cantidad)
                    st.session_state[f"editando_{id_alimento}"] = False
                    st.rerun()



    else:
        st.info("No se encontraron alimentos con ese nombre.")

    st.header("📆 Calendario de Caducidades (30 días)")

    hoy = datetime.now().date()
    dias_futuros = [hoy + timedelta(days=i) for i in range(30)]

    # Agrupar alimentos por fecha de caducidad
    caducidades_por_dia = {}

    for _, nombre, fecha_str, _ in alimentos:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        if hoy <= fecha <= hoy + timedelta(days=30):
            caducidades_por_dia.setdefault(fecha, []).append(nombre)

    # Mostrar resultados ordenados por fecha
    if caducidades_por_dia:
        for fecha in sorted(caducidades_por_dia):
            nombres = caducidades_por_dia[fecha]
            dia_formateado = fecha.strftime("%d-%m")
            st.markdown(f"🗓️ **{dia_formateado}**: {len(nombres)} alimento(s)")
            for nombre in nombres:
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• {nombre}")
    else:
        st.info("No hay alimentos que caduquen en los próximos 30 días.")


elif pagina == "🍽️ Añadir alimentos":

    # Interfaz de Streamlit
    st.title("🍽️ Gestor de alimentos")

    st.header("🎤 **Usa tu voz para introducir un alimento**")
    st.markdown("ℹ️ Di algo como: *'Tortilla que caduca el 2 del 2 del 2025'*")
    audio_bytes = st_audiorec()


    if audio_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(audio_bytes)
            temp_audio_path = f.name

        recognizer = sr.Recognizer()
        with sr.AudioFile(temp_audio_path) as source:
            audio = recognizer.record(source)
            try:
                texto_voz = recognizer.recognize_google(audio, language="es-ES")
                st.write(f"📝 Texto reconocido: `{texto_voz}`")

                # Llenar automáticamente la entrada rápida y guardar
                nombre, fecha = extraer_datos(texto_voz)
                if not nombre or not fecha:
                    st.error("❌ No se pudo interpretar el nombre o la fecha del audio.")
                else:
                    agregar_alimento(nombre, fecha, "Entero")
                    st.success(f"✅ '{nombre}' añadido con fecha {fecha.strftime('%d-%m-%Y')}")

            except sr.UnknownValueError:
                st.error("❌ No se pudo entender el audio.")
            except sr.RequestError:
                st.error("❌ Error al conectar con el servicio de voz de Google.")

    st.header("📸 Escanear etiqueta de producto")

    img_data = st.camera_input("Toma una foto del código de barras")

    if img_data:
        # Leer imagen como PIL
        image = Image.open(img_data)

        # Decodificar código de barras
        decoded = decode(image)

        if decoded:
            for d in decoded:
                st.success(f"Código detectado: {d.data.decode('utf-8')}")
        else:
            st.warning("No se detectó ningún código de barras.")

    imagen = st.file_uploader("Sube una foto del alimento (etiqueta)", type=["png", "jpg", "jpeg"])

    if imagen:
        img = Image.open(imagen)
        texto_extraido = pytesseract.image_to_string(img, lang='spa')

        st.text_area("📝 Texto extraído:", value=texto_extraido, height=200)

        if st.button("🧠 Añadir desde OCR"):

            nombre, fecha = extraer_datos(texto_extraido)
            if nombre and fecha:
                agregar_alimento(nombre, fecha, "Entero")
                st.success(f"✅ '{nombre}' añadido automáticamente con fecha {fecha}")
            else:
                st.error("❌ No se pudo interpretar nombre o fecha del texto.")




    # Agregar nuevo alimento
    st.header("➕ Agregar alimento manualmente")
    nombre = st.text_input("Nombre")
    fecha_str = st.text_input("Fecha de caducidad (DD-MM)")
    cantidad = st.text_input("Cantidad", value="Entero")
    etiquetas_input = st.text_input("Etiquetas (separadas por comas)", placeholder="lácteo, desayuno, congelado")

    if st.button("Guardar"):

        try:
            if re.match(r"\d{2}-\d{2}-\d{4}", fecha_str):
                fecha = datetime.strptime(fecha_str, "%d-%m-%Y").date()
            else:
                fecha = datetime.strptime(fecha_str + f"-{datetime.now().year}", "%d-%m-%Y").date()

            agregar_alimento(nombre, fecha, cantidad, etiquetas_input.strip())
            st.success("✅ Alimento agregado correctamente.")
        except:
            st.error("❌ Fecha no válida. Usa formato DD-MM.")

    # Si el flag refrescar está activo, “reseteamos” la app
    if st.session_state.refrescar:
        st.session_state.refrescar = False
        st.rerun()

elif pagina == "🛒 Lista de la compra":
    st.title("🛒 Lista de la compra (alimentos eliminados)")

    # Añadir manualmente
    st.subheader("➕ Añadir producto manualmente a la lista")
    nuevo_producto = st.text_input("Nombre del producto a añadir")
    if st.button("Añadir a lista"):
        if nuevo_producto.strip():
            agregar_a_lista_compra(nuevo_producto)
            st.success(f"'{nuevo_producto}' añadido a la lista de la compra.")
            st.rerun()
        else:
            st.warning("Por favor, introduce un nombre.")

    # Ver productos eliminados
    
    cursor.execute("SELECT id, nombre, fecha_eliminado FROM eliminados ORDER BY fecha_eliminado DESC")
    eliminados = cursor.fetchall()

    if eliminados:
        if st.button("🧹 Eliminar toda la lista"):
            cursor.execute("DELETE FROM eliminados")
            conn.commit()
            st.success("Lista de la compra vaciada.")
            st.rerun()

        for id_eliminado, nombre, fecha in eliminados:
            cols = st.columns([6, 1])
            with cols[0]:
                st.markdown(f"• **{nombre}** (eliminado el {fecha})")
            with cols[1]:
                if st.button("Eliminar", key=f"borrar_{id_eliminado}"):
                    cursor.execute("DELETE FROM eliminados WHERE id = ?", (id_eliminado,))
                    conn.commit()
                    st.success(f"'{nombre}' eliminado permanentemente.")
                    st.rerun()
    else:
        st.info("Tu lista de la compra está vacía.")





