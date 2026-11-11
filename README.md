# 📡 Radar Inversor

Panel local (se abre en tu navegador, pero todo corre en tu ordenador) para hacerte una idea de cómo puede moverse una acción
y qué hay alrededor de ella. **Gratis, sin claves de API, sin cuentas.**

## Cómo arrancarlo

**Lee primero `GUIA.md`** (también está dentro del programa, en 📘 Guía).

- **Windows:** extrae el zip y haz doble clic en `iniciar.bat`. Si no tienes Python, lo instala solo.
- **Mac / Linux:** doble clic en `iniciar.command` (si no se abre: `chmod +x iniciar.command`, o ejecuta `python3 lanzar.py`)

La primera vez instala las librerías (un par de minutos). Después se abre solo en `http://localhost:8501`.
Para cerrarlo, cierra la ventana negra.

## Qué incluye

Novedades de cada versión en `NOVEDADES.md`. Lo más nuevo: **🧠 Análisis** completo de cada acción, **💼 Negocio** (de dónde viene el dinero y quién le compra), mapa de calor, línea de comandos y actualizaciones automáticas (`actualizacion.json`).

| Sección | Qué te da | Fuente |
|---|---|---|
| 🌡️ Mercado | Termómetro: índices, VIX, petróleo, gas, oro, EUR/USD, bono 10 años, tendencia (vs. media 200 días) y noticias por tema | Yahoo Finance, Google News |
| 🌍 Mapa mundial | Globo con países por economía/bolsa/inflación, fichas de país con señales de crisis, y buscador de minas, centrales, refinerías, GNL, petroleros por puerto y estrecho, rutas marítimas, desastres naturales y buques en directo (opcional) | FMI, Banco Mundial, PortWatch, GDACS, Wikidata, WRI, aisstream.io |
| 🏢 Empresa | Ficha, gráfico, **índices en los que cotiza**, precios objetivo de analistas (bajo/medio/alto), accionistas institucionales | Yahoo Finance, Wikipedia, Nasdaq |
| 🚦 Señales | Veredicto 🟢🟡🔴 con sus motivos, plan con **stop loss y take profit**, probabilidad de tocar cada uno, resultado esperado en € con comisiones, **rango probable a 1 día, 1 semana, 2 semanas y 1 mes**, escáner de índices, prueba histórica y **comparador** de muchos valores | Cálculo propio + noticias + ETF de sector + analistas |
| 🎯 Escenarios | Precio **pesimista / mediano / optimista** en mercado alcista, bajista e histórico completo, probabilidad de pérdida, caída máxima típica y prueba de estrés | Cálculo propio sobre 5 años de precios |
| 📰 Noticias | Titulares de los últimos 7 días con tono (🟢⚪🔴), valorado con **IA (FinBERT, opcional y gratis)** o palabras clave | Google News |
| 🕸️ Conexiones | Mapa clicable de **a quién le compra y a quién le vende** cualquier empresa: base precargada (~240 relaciones), búsqueda automática de clientes/proveedores/competidores en los informes de otras empresas, su propio informe anual y tu tabla | Base propia, SEC EDGAR (búsqueda de texto completo), Yahoo |
| 🛢️ Energía y buques | Buques y petroleros por día en Ormuz, Suez, Malaca, Panamá, Gibraltar… (tendencia semanal) y mapa de centrales, refinerías y pozos con quién opera cada una | FMI PortWatch, OpenStreetMap |
| 📅 Agenda | Resultados, ex-dividendo y pagos de tu lista, posiciones y diario | Yahoo Finance |
| 🔔 Alertas | Avisos de Windows por precio, variación, noticia, OPA/fusión o resultados; también con el programa cerrado | Propio |
| ⛏️ Materias primas | 18 materias primas, países productores con su economía y empresas expuestas | Yahoo Finance, USGS/IEA/FAO (aprox.) |
| 📒 Diario | Registro de tus operaciones con acierto, resultado, R y respeto del stop | Tus datos |
| 💶 Mi compra | Qué pasaría con tu aportación (p. ej. 50 €) en cada escenario, comisión incluida, y cómo cambia la volatilidad de tu cartera | Cálculo propio |

## Antes de fiarte de él

- **No es tiempo real.** Los precios llevan algo de retraso; el tráfico marítimo del FMI se publica con unos días de retraso;
  OpenStreetMap lo edita la gente y puede estar incompleto. Sirve para ver tendencias, no para operar al segundo.
- **Los escenarios no son predicciones.** Repiten estadísticamente el pasado. No saben nada de resultados trimestrales,
  noticias ni cambios de ciclo. La barra de *Prudencia* evita que una acción que ha subido muchísimo parezca que seguirá haciéndolo.
- **La cadena de suministro es parcial.** Ninguna fuente gratuita trae el mapa completo (eso es lo que venden Bloomberg o FactSet).
  Los informes de la SEC casi nunca nombran a todos sus proveedores. Las filas de ejemplo de tu tabla vienen de conocimiento
  público: verifícalas. Y en esa tabla puedes ir apuntando lo que descubras (también sirve para prospección comercial).
- **El tono de las noticias** se calcula con palabras clave del titular. Es una pista, no un análisis.
- Herramienta informativa. **No es asesoramiento financiero.**

## Configuración de una sola vez

- **SEC (informes anuales):** la SEC exige identificarse con nombre y correo. La app te lo pide la primera vez que pulsas
  *Leer el último 10-K / 20-F* y lo guarda solo en tu ordenador. También puedes definir la variable de entorno `RADAR_SEC_UA`
  (`"Tu Nombre tu_correo@dominio.com"`).
- **Dónde se guardan tus cosas:** `~/.radar_inversor` (caché, tu tabla de relaciones, tus posiciones). Se puede cambiar con `RADAR_DIR`.

## Si algo no carga

Ejecuta `python comprobar_conexion.py`: prueba cada fuente y te dice cuál no responde. Los servidores públicos de OpenStreetMap
van saturados a veces: la app lo reintenta sola y, si no, vuelve a probar en unos minutos. Si una fuente falla, la app te
enseña el último dato guardado cuando lo tiene.

## Ideas para ampliarlo

- Posición de buques en directo en zonas concretas (aisstream.io, gratis con registro).
- Alertas por correo cuando una noticia o un precio cumpla una condición.
- Leer los informes anuales con un modelo de lenguaje para sacar proveedores y clientes con más precisión (requiere clave de pago).
- Cargar tus posiciones de Trade Republic y MyInvestor desde un CSV.

## Pruebas

`python -m pytest tests` (no necesitan internet).
