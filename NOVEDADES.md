# Novedades

## Versión 2.4 (noviembre de 2026)

- **🪙 Cripto** (menú principal): precios de las 100 mayores criptomonedas en dólares y euros, ánimo del mercado (miedo y codicia),
  peso de bitcoin y punto del ciclo. Eliges una y te hace su análisis: qué es, solidez de 0 a 10, veredicto a corto, medio y largo
  plazo, hasta dónde puede moverse en 12 meses, riesgos y qué peso máximo tendría sentido. Comando: `CRIPTO`.
- **Análisis de empresas que aún no ganan dinero** (Rocket Lab, Palantir, CrowdStrike, Tesla…): antes salían resultados raros
  («precio atractivo» pero «evitar», o porcentajes disparatados). Ahora se valoran por ventas, se etiquetan como
  **«especulativa: solo como apuesta pequeña»** cuando crecen deprisa, y como «evitar» solo si no crecen o se les acaba la caja.
- Los escenarios optimistas ya no pueden dar cifras absurdas cuando el beneficio actual es casi cero.

## Versión 2.3 (noviembre de 2026)

- **💡 Ideas** (menú principal): las 10 acciones más atractivas de un grupo (IBEX 35, Europa, EE. UU., Nasdaq-100) para comprar
  a 6-12 meses, con acceso directo a su análisis.
- **📌 Picks del día** pasa al menú principal.
- Corregido: el análisis ya no sugiere «esperar a que baje» a un precio que está por encima del actual. Cuando el precio da margen
  pero el negocio es flojo, lo dice claramente («solo como apuesta pequeña»).

## Versión 2.2 (noviembre de 2026)

- **📌 Picks del día** (📈 Mercados): las empresas que presentan resultados en los próximos días, ordenadas por interés, con lo
  que pasó otras veces («si bate previsiones…, si falla…»), el movimiento que descuentan las opciones y si llegan subiendo o castigadas.
- **Veredicto por plazos** en 🧠 Análisis y 🚦 Señales: corto (1 semana-1 mes), medio (3-6 meses) y largo (12-18 meses), con una
  explicación de qué hacer cuando no coinciden.
- **🚦 Señales** admite operaciones de hasta 6 meses: el stop y el objetivo se ajustan al plazo.

## Versión 2.1.5

- Reúne los arreglos de las versiones 2.1.2 a 2.1.4 (inicio más rápido, descarga en Excel y buscador por nombre).

## Versión 2.1.4

- Buscador de empresas: ya se puede escribir el nombre (no solo el ticker), tolera erratas («microsft», «acenture») y elige la bolsa principal de cada empresa.

## Versión 2.1.3

- Corregido un error al preparar la descarga en Excel del análisis con versiones recientes de pandas.

## Versión 2.1.2

- La pantalla de inicio carga más rápido: los datos de países se descargan a la vez y, si una fuente no responde, se pasa a la siguiente en segundos.

## Versión 2.1.1

- Actualizaciones automáticas activadas.
- El aspecto oscuro ya no depende de la carpeta `.streamlit`.

## Versión 2.1 (noviembre de 2026)

- **📊 Macro**: curva de tipos de EE. UU., tipos oficiales, inflación, paro, prima de riesgo, divisas y termómetros del miedo.
- **🖥️ Monitor**: tu lista de seguimiento (acciones, índices, materias primas, divisas, cripto) en una pantalla.
- **🧮 Buscador**: filtra las acciones de un índice por PER, dividendo, ROE, crecimiento o caída desde máximos.
- **🧺 Cartera**: reparto por posición, sector, país y divisa, correlaciones, volatilidad y proveedores comunes.
- **🔬 Profundizar** (en cada empresa): quién es el dueño y qué hacen los directivos, opciones (movimiento esperado,
  volatilidad implícita, puts frente a calls) y con qué se mueve la acción.
- **💼 Negocio** avisa si los clientes o proveedores de la empresa están cayendo en bolsa.
- **🧠 Análisis** se puede descargar como informe (HTML imprimible a PDF) y como Excel.
- Las cifras oficiales de la SEC se ordenan mejor (negocio principal arriba y su desglose debajo).

## Versión 2.0 (noviembre de 2026)

- **🧠 Análisis** (nueva pantalla, la primera al abrir una empresa): análisis completo en 11 pasos — métricas con contexto
  (su historia, competidores y sector), calidad del negocio, para qué perfil sirve, DCA, catalizadores, momento técnico,
  tres escenarios de precio a 12-18 meses, riesgos, veredicto, recomendación y resumen en lenguaje llano.
  Lo generan reglas automáticas sobre los datos, no una IA; al final hay un botón para llevarte todos los datos a una IA.
- **💼 Negocio** (nueva): de dónde viene el dinero (por producto, negocio, cliente y país) y quién le compra y para qué.
  Con cifras oficiales de la SEC para las empresas que cotizan en EE. UU. y una base propia aproximada para el resto.
- **Base de conexiones ampliada**: de 150 a ~300 empresas y de 250 a ~630 relaciones, ahora con la finalidad de cada compra.
- **Noticias solo de economía y mercados**: buscar «oro» ya no trae el Balón de Oro.
- **Índices**: 19 índices (antes 7) y aparecen en la cabecera de cada empresa.
- **🟩 Mapa de calor** de índices y **línea de comandos** («NVDA AN», «SAN.MC N», «ORO», «CALOR»).
- **Aspecto oscuro** tipo terminal.
- **Actualizaciones automáticas**: el programa se pone al día solo al abrirlo.
