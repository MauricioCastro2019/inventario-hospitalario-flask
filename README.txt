
📦 SISTEMA DE INVENTARIO PERSONAL - HMV DIGITAL

Este es un sistema web sencillo desarrollado con Python y Flask para llevar el control de productos en inventario. Incluye carga de imagen, registro de entradas y salidas, cálculo automático de precio con utilidad, y más.

-------------------------------
📁 ESTRUCTURA DEL PROYECTO:
-------------------------------
- app.py                → Código principal de la aplicación
- db.sqlite3            → Base de datos SQLite
- requirements.txt      → Librerías necesarias
- static/uploads/       → Carpeta de imágenes de productos
- templates/            → HTMLs de la interfaz
- migrations/           → Carpeta de migraciones para modificar la base sin perder datos

-------------------------------
▶️ CÓMO EJECUTAR EL PROYECTO:
-------------------------------

1. Abre una terminal y ve a la carpeta del proyecto:

   cd ruta/del/proyecto

2. Activa tu entorno (si usas uno) o asegúrate de tener Python instalado.

3. Instala las librerías necesarias:

   pip install -r requirements.txt

4. Ejecuta la app:

   python app.py

5. Abre tu navegador y visita:

   http://127.0.0.1:5000

-------------------------------
⚙️ FUNCIONALIDADES:
-------------------------------

✔️ Agregar producto con imagen
✔️ Edición completa de producto
✔️ Precio sugerido automático (35%)
✔️ Categorías para organizar mejor
✔️ Búsqueda por nombre, código o categoría
✔️ Registro de movimientos (entradas y salidas)
✔️ Última modificación automática

-------------------------------
💡 NOTAS:
-------------------------------
- Esta app no es multisesión ni multiusuario por ahora.
- Puedes subirla a un servidor Flask, PythonAnywhere o ejecutarla localmente.
- Para actualizar el modelo, usa: flask db migrate + flask db upgrade

-------------------------------
👤 Desarrollado por:
-------------------------------
Mauricio Banquells ✨
Con ayuda de su compa digital (ya sabes quién soy 😎)

PASOS PARA ARRANCAR EL PROYECTO
1. Abrir carpeta en VS Code
2. Activar entorno: .\.venv\Scripts\Activate.ps1
3. python app.py
