# 📘 Guía de Radar Inversor

Esta guía explica, paso a paso, cómo instalar el programa, qué hace cada pantalla y cómo usarlo para operar con
cantidades pequeñas (unos 100 €) a 1 mes o menos, **perdiendo lo mínimo cuando te equivoques**.

---

## ⭐ Novedades de la versión 2.0 (léelo primero)

**🧠 Análisis.** Al abrir cualquier empresa sale un análisis completo en 11 pasos: métricas (cada una comparada con su propia
historia, con competidores y con el sector), calidad del negocio, para qué tipo de inversión sirve, si es apta para DCA,
catalizadores, momento técnico, tres escenarios de precio a 12-18 meses con sus supuestos, riesgos, veredicto, recomendación
(🟢 comprar / 🟡 mantener o esperar / 🔴 evitar) y un resumen en lenguaje llano.
Lo escriben **reglas automáticas**, no una persona ni una IA: es coherente y prudente, pero no sabe lo que no está en los datos
(un cambio de director, un producto nuevo). Al final tienes un botón para copiar todos los datos y pedirle una segunda opinión a una IA.
Cómo decide: calcula cuánto podrías ganar en el escenario más probable y exige un mínimo según la calidad (15 % si es buena,
25 % si es aceptable, 40 % si es mediocre, y más si hay riesgos graves). Si no llega, te da el precio al que sí interesaría.

**💼 Negocio.** De dónde viene el dinero de la empresa y a dónde va lo que produce: reparto de ingresos por producto, negocio,
tipo de cliente y país, y la lista de clientes con **para qué** usan lo que compran. Para empresas que cotizan en EE. UU. las cifras
son las oficiales del informe anual (hay que guardar una vez tu nombre y correo para la SEC); para el resto son aproximadas.

**⌨️ Línea de comandos** (arriba a la izquierda). Escribe y pulsa Intro: `NVDA AN` (análisis), `NVDA NEG` (negocio),
`SAN.MC N` (noticias), `REP.MC CON` (conexiones), `ITX.MC SEN` (señales), o solo `CALOR`, `HOY`, `ORO`, `COBRE`, `AGENDA`…

**🟩 Mapa de calor** (📈 Mercados): todo un índice de un vistazo; el tamaño es lo que se negocia y el color, lo que sube o baja.

**📰 Noticias filtradas.** Solo economía y mercados. Si quieres verlo todo, activa «Ver todo sin filtrar».

**💡 Ideas** (menú principal). Elige un grupo (IBEX 35, Europa, EE. UU. o Nasdaq-100) y pulsa «Buscar ideas»: el programa pasa su
análisis a todas y te enseña las diez que mejor salen para comprar a 6-12 meses, con el motivo, lo que puede salir mal y un botón
para abrir el análisis completo. Tarda de 1 a 3 minutos la primera vez. Si hay menos de diez compras claras, completa la lista con
buenas empresas a las que les falta bajar un poco, con su precio de entrada. Es una lista para empezar a mirar, no una orden de compra.

**📌 Picks del día** (menú principal). Las empresas que presentan resultados en los próximos días. Para cada una: qué beneficio se
espera, cuántas veces batió o falló las previsiones y qué hizo la acción al día siguiente en cada caso, cuánto movimiento descuentan
las opciones y si llega subiendo o castigada. No predice la dirección: te da las frecuencias reales. «Interés alto» significa que
puede moverse mucho o que la tienes en tus listas, no que haya que comprarla.

**Veredicto por plazos.** 🚦 Señales y 🧠 Análisis responden a preguntas distintas, y por eso a veces parecen contradecirse:
Señales mira si el precio acompaña *ahora* (días o semanas); Análisis mira si el negocio vale más de lo que cuesta (más de un año).
El recuadro «Veredicto por plazos» los pone juntos, añade el medio plazo y te dice qué hacer cuando no coinciden
(lo habitual: buena empresa que está cayendo → entrar por partes o esperar a que la señal corta mejore).
En 🚦 Señales puedes elegir el horizonte de la operación, de 1 semana a 6 meses.

**📊 Macro** (📈 Mercados). Tipos de interés, inflación, paro, prima de riesgo, divisas y termómetros del miedo (VIX, oro, bonos).
Regla rápida: tipos subiendo perjudican a las acciones caras y a las empresas con deuda; curva invertida (el corto paga más que el
largo) suele avisar de recesión con meses de adelanto.

**🖥️ Monitor** (📈 Mercados). Tu lista de seguimiento en una pantalla. Se edita en «Cambiar la lista» con símbolos de Yahoo.

**🧮 Buscador** (📈 Mercados). Filtra las acciones de un índice por sus números. Es un colador: lo que salga, míralo en 🧠 Análisis.

**🧺 Cartera** (menú principal). Apunta tus posiciones y verás en qué estás concentrado (empresa, sector, país, divisa), si tus
acciones se mueven todas a la vez y de qué proveedores dependen varias. Correlación media por encima de 0,6 = poca diversificación real.

**🔬 Profundizar** (en cada empresa). Tres pestañas: quién es el dueño (fondos y directivos: fíjate en las *compras* de directivos),
opciones (cuánto movimiento espera el mercado hasta una fecha; solo acciones de EE. UU.) y con qué se mueve la acción.

**Exportar.** Al final de 🧠 Análisis puedes descargar el informe (HTML; con Ctrl+P lo guardas como PDF) y los datos en Excel.

**Más comandos:** `MACRO`, `MONITOR`, `BUSCADOR`, `CARTERA`, `NVDA PRO`.

**🔄 Actualizaciones.** El programa busca versiones nuevas cada vez que lo abres y se actualiza solo. Tus datos no se tocan.
Si algo va mal tras actualizar, la versión anterior queda guardada en la carpeta `_version_anterior`.

---

## 0. Lo que tienes que saber antes de operar

**1. Las comisiones son tu mayor enemigo con 100 €.** Con 1 € por orden pagas 2 € entre la compra y la venta, es decir,
un **2 %** del importe. La acción tiene que subir un 2 % solo para que te quedes igual. En acciones españolas grandes se
suma un 0,2 % de impuesto sobre transacciones financieras.

**2. Lo he medido.** Apliqué la señal técnica del programa a los últimos 5 años de 12 valores conocidos
(NVIDIA, Apple, Microsoft, Lockheed, Exxon, Santander, Inditex, Iberdrola, Repsol, Rheinmetall, SAP y BP), con SL, TP
y un máximo de 1 mes:

| Importe por operación | Resultado medio por operación |
|---|---|
| Sin comisiones | **+1,3 %** |
| 500 € con 1 € por orden | **+0,9 %** |
| 100 € con 1 € por orden | **−0,7 %** (pierde en 11 de 12 valores) |

Es decir, la señal tiene algo de ventaja, pero **con 100 € por operación las comisiones se la comen**. Opciones
razonables: operar menos veces con importes mayores (300–500 €), o empezar con 100 € sabiendo que el objetivo de los
primeros meses es **aprender sin perder mucho**, no ganar.

Y aun con 500 €, la señal **no gana en todos los valores**. En el IBEX 35 (5 años, 500 € por operación) solo en **8 de 35**
valores ganó y además mejor que entrar al azar; en 13 ganó sin aportar nada y en 14 perdió. Por eso el programa trae un
**📊 Comparador**: úsalo para quedarte solo con los valores donde la señal ha funcionado.

**3. La mayoría de quien hace trading a corto plazo pierde dinero.** El programa no cambia eso por sí solo. Lo que sí
hace es obligarte a tener un plan (dónde entro, dónde salgo si me equivoco, dónde recojo beneficios) y a medir si te funciona.

**4. Nada de esto es asesoramiento financiero.** Son reglas automáticas con datos gratuitos. Tú decides.

**5. Qué tan actualizados están los datos** (medido en un día de mercado):

| Dato | Retraso aproximado |
|---|---|
| Precio de acciones e índices (Yahoo Finance) | ~15 minutos con la bolsa abierta; cerrada, el cierre de la última sesión |
| Materias primas (petróleo, oro, cobre…) | ~10-15 minutos |
| Noticias, incluidas compras, fusiones y OPAs (Google News) | de minutos a pocas horas |
| Comunicados oficiales a la SEC (empresas de EE. UU.) | en cuanto la empresa los presenta |
| Compras y ventas de directivos | 1-2 días (tienen 2 días hábiles para declararlas) |
| Agenda de resultados y dividendos | diaria (las fechas a veces son estimadas) |
| Petroleros por puerto y estrechos | ~5 días |
| Centrales eléctricas del mapa | 2021 (solo para hacerse una idea) |

Para entrar en una operación, mira siempre el precio final en tu bróker.

---

## 1. Instalación (Windows, una sola vez)

1. Descarga `radar-inversor.zip`.
2. Haz clic derecho sobre el zip → **Extraer todo…** → elige una carpeta, por ejemplo `Documentos\radar-inversor`.
   ⚠️ No lo ejecutes desde dentro del zip sin extraer: no funcionará.
3. Entra en la carpeta extraída y haz doble clic en **`iniciar.bat`**.
4. Si Windows muestra *"Windows protegió su PC"*: pulsa **Más información → Ejecutar de todas formas**
   (sale porque el archivo no está firmado, no porque sea peligroso; puedes abrirlo con el Bloc de notas para ver lo que hace).
5. Si no tienes Python, el propio archivo lo instala con el instalador oficial de Windows (*winget*). Acepta si te pide permiso.
   - Si no lo consigue, se abrirá la web de Python: descarga **Python 3.12**, y al instalar **marca "Add python.exe to PATH"**.
     Luego vuelve a hacer doble clic en `iniciar.bat`.
6. La primera vez tarda **3–5 minutos** (instala librerías). Después se abre solo tu navegador en `http://localhost:8501`.
7. Para cerrar el programa, cierra la ventana negra.

**Las siguientes veces:** la primera instalación deja un icono **Radar Inversor** en tu escritorio. Doble clic en él y en
unos segundos está abierto (si no aparece, haz doble clic una vez en `crear_acceso_directo.bat`).

**¿Los datos se actualizan solos?** Sí: cada vez que abres el programa descarga precios, noticias, índices e informes del
momento (los precios con ~15 minutos de retraso en horario de bolsa; el tráfico de buques, con unos días). Además, al
arrancar actualiza sola la librería de Yahoo Finance, que es la que más cambia. Lo único fijo es la *base precargada* de
conexiones entre empresas (información hasta 2026); la búsqueda en informes de la SEC sí está siempre al día.

---

## 2. La pantalla, de un vistazo

**Al abrir el programa** aparece el **globo terráqueo** con un **buscador grande** encima. Escribe lo que quieras:
- algo del mapa (*petroleros*, *mina de cobre*, *centrales nucleares*, *GNL*, *terremotos*…) y se pinta en el globo;
- o una empresa (*Nvidia*, *Repsol*, *Inditex*, *SAN.MC*…) y te salen botones para abrirla.

Debajo tienes botones de ejemplo (Petroleros, Minas de oro, Centrales nucleares…) para ir más rápido.

**Menú (izquierda):**

| Menú | Qué hay dentro |
|---|---|
| 🌍 Inicio | El globo con el buscador: minas, centrales, refinerías, GNL, petroleros, rutas, desastres y países por economía o bolsa. Pincha en un país para ver su ficha |
| 📈 Mercados → 🌡️ Hoy | Qué bolsas están abiertas, cómo abrieron y cómo van, lo que más sube y baja, y compras/fusiones/OPAs del día |
| 📈 Mercados → 🔍 Oportunidades | Escáner de índices enteros y comparador de la señal en muchos valores |
| 📈 Mercados → ⛏️ Materias primas | Precios, países productores y empresas expuestas |
| 📈 Mercados → 📅 Agenda | Resultados y dividendos de tu lista |
| 📈 Mercados → 🛢️ Energía y buques | Tráfico de petroleros por estrechos y mapa de centrales por zonas |
| 🏢 Empresa | Solo cuando has abierto una empresa: 🏢 Ficha · 🚦 Señales · 🎯 Escenarios · 📰 Noticias · 🕸️ Conexiones · 💶 Mi compra |
| 🔔 Alertas | Avisos de Windows cuando se cumpla lo que elijas |
| 📒 Diario | Apuntar cada operación y ver si de verdad ganas |
| 📘 Guía | Esta guía |

**🔎 Buscar una empresa** (barra lateral): escribe el nombre o el ticker y pulsa el resultado; se abre en 🏢 Empresa. Las
acciones españolas terminan en `.MC`, alemanas en `.DE`, francesas en `.PA`, británicas en `.L`; las de EE. UU. sin sufijo.
**✕ Cerrar empresa** la quita.

**⚙️ Ajustes** (barra lateral): horizonte de los escenarios, prudencia del modelo (déjala en 50 %; súbela si la acción ha
subido muchísimo), índice de referencia (se pone solo), idioma de las noticias, IA de noticias y borrar caché.

---

## 3. Rutina semanal (domingo, 30–45 minutos)

Aquí es donde se decide. Durante la semana solo se ejecuta y se vigila.

### Paso 1 · ¿Acompaña el mercado? (📈 Mercados → 🌡️ Hoy, 3 min)
- Lee la frase de arriba. Si dice **tendencia bajista** o el **VIX está por encima de 25**, sé mucho más selectivo
  (o no operes esa semana). En mercado bajista casi todas las compras a corto plazo salen peor.
- Mira el petróleo, el oro y el bono a 10 años: si se mueven con fuerza, afectan a energía, bancos y tecnología.
- Repasa las noticias por tema que te interesen (defensa, energía, tipos de interés…).

### Paso 2 · Buscar candidatas (📈 Mercados → 🔍 Oportunidades → Escáner, 5 min)
- Elige una lista (empieza por **IBEX 35** o **Mi lista**) y pulsa **Escanear**.
- Quédate con **3–5 valores** que cumplan:
  - Puntuación técnica **≥ +3**.
  - **RSI entre 40 y 60** (retroceso dentro de una subida). Evita RSI > 70: ya ha subido mucho.
  - Volatilidad diaria **por debajo del 3–4 %** (si no, el stop salta por ruido).
  - Fuerza frente al índice positiva.

### Paso 2 bis · Quedarte solo con valores donde la señal funciona (📊 Comparador, una vez al mes)
- En **📈 Mercados → 🔍 Oportunidades → 📊 Comparador**, elige la lista, pon tu importe real y pulsa **Comparar**.
- Apunta los valores **🟢 Aporta ventaja**. Esa es tu lista buena: en el escáner, usa **Mi lista** con esos tickers.
- Evita los **🔴 Pierde**, y en los **🟡** piénsatelo: ganaron solo porque el mercado subía.

### Paso 3 · Analizar cada candidata (🚦 Señales → 📋 Plan, 5 min por valor)
Pincha en el valor desde el escáner (o búscalo en la barra lateral) y abre **🚦 Señales**:
1. **Veredicto:** 🟢 candidata · 🟡 vigilar · 🔴 no entrar. Solo sigue con 🟢 (o 🟡 muy cerca del verde).
2. Lee **"Por qué"**: cada ✅ suma y cada ⚠️ resta. Si una ⚠️ te parece grave (p. ej., noticias de una investigación), descártala.
3. Revisa el **plan**: entrada, stop loss, take profit, probabilidades y **resultado esperado en €**.
   - Si el resultado esperado es **negativo**, no entres.
   - Si sale el aviso de *objetivo ambicioso*, cambia el perfil de stop a "Ajustado" o descarta.
4. Abre **🧪 Prueba histórica**: si en este valor la señal **no habría ganado tras comisiones**, o no mejora a
   "entrar a ciegas", descártalo. Mira también la fila *sin comisiones*: te dice cuánto te están costando.

### Paso 4 · Contexto (opcional, 5 min)
- **📰 Noticias:** ¿hay resultados trimestrales en las próximas 2 semanas? Las acciones pegan saltos ese día,
  en ambos sentidos. Si no quieres esa lotería, espera a después de los resultados.
- **🕸️ Conexiones:** si su cliente o proveedor principal tiene problemas (o buenas noticias), le afectará. Ejemplo: si
  TSMC anuncia retrasos, mira en el mapa quién depende de TSMC.
- **🛢️ Energía y buques:** para petroleras, refineras, navieras o químicas, mira si el tráfico de petroleros
  en Ormuz/Suez cambia mucho frente a las semanas anteriores.

### Paso 5 · Decidir y apuntar
- Elige **como máximo 1–2 operaciones** para la semana.
- Pulsa **📒 Apuntar este plan en el diario**.

---

## 3 bis. El mapa de conexiones (🕸️ Conexiones)

Para cualquier empresa te enseña **a quién le compra** (proveedores, a la izquierda) y **a quién le vende** (clientes, a la
derecha). **Pincha en cualquier empresa del mapa** y pasa a ser el centro, con sus propias conexiones: así puedes recorrer la
cadena entera (por ejemplo NVIDIA → TSMC → ASML → Zeiss). Con **Niveles = 2** ves de golpe los proveedores de sus proveedores
y los clientes de sus clientes. El botón **Analizar … en todo el programa** lleva esa empresa a todas las secciones.

De dónde salen las conexiones (cada una indica su fuente y su confianza):
1. **Base precargada:** unas 240 relaciones conocidas entre unas 145 grandes empresas (chips, nube e IA, automoción,
   aviación y defensa, energía, pagos, telecomunicaciones y empresas españolas). Es información pública hasta 2026:
   la de confianza *media* conviene verificarla.
2. **Buscar en informes de otras empresas:** para **cualquier** empresa (también privadas como OpenAI), busca qué empresas
   cotizadas en EE. UU. la nombran en su informe anual y deduce si son sus **clientes, proveedores o competidores** leyendo
   la frase. Ejemplo con NVIDIA: encuentra a CoreWeave, Nebius, IREN o Bitdeer como clientes. Tarda 30–60 s la primera
   vez. Es automático y a veces se equivoca: **lee siempre la frase** antes de fiarte.
3. **El informe anual de la propia empresa:** proveedores que ella misma nombra.
4. **Tu tabla:** lo que tú añadas (sale en azul).

**Lo que no puede hacer:** ninguna fuente gratuita tiene *todas* las conexiones (eso es lo que venden Bloomberg o FactSet).
Las empresas europeas o asiáticas que no presentan informes en EE. UU. solo aparecen si están en la base o si otra empresa
las nombra.

---

## 3 quater. El mapa mundial (🌍 Mapa mundial)

**Buscador:** escribe lo que quieres ver en lenguaje normal ("mina de cobre", "centrales nucleares y GNL",
"¿dónde están los petroleros?", "terremotos") y el programa elige las capas. También puedes añadir o quitar capas a mano.

**Qué puedes ver:**
- **Minas** de oro, cobre, hierro, litio, uranio, plata, níquel, cobalto, carbón, platino, zinc, diamantes, estaño o potasa.
  Por defecto salen las grandes (unas 50 de la base del programa, con su empresa y ticker); el interruptor *Minas: incluir
  todas* añade todas las registradas en Wikidata (cientos, incluidas pequeñas o históricas).
- **Centrales eléctricas** de todo el mundo por tipo (nuclear, carbón, gas, hidroeléctrica, solar, eólica…), con el tamaño
  según su potencia. Fuente: base mundial del WRI (datos de 2021; las construidas después no salen).
- **Refinerías y terminales de GNL** principales (unas 80, ubicación aproximada), con su operador.
- **Petroleros:** escalas de petroleros por puerto en los últimos 7 días (cuántos cargan y descargan) y tránsito diario
  por los estrechos (Ormuz, Suez, Malaca…). Lo estima el FMI con datos de satélite y se publica con **unos 5 días de retraso**.
- **Rutas marítimas principales** del mundo.
- **Desastres naturales** activos (terremotos, ciclones, inundaciones, sequías, incendios) con alerta naranja o roja.

**Países por colores:** *Economía* = verde si su PIB crece un 2 % o más, amarillo entre 0 y 2 %, rojo si se contrae.
También puedes colorear por **bolsa del país en el año** (con su ETF en dólares), inflación, paro o deuda. Los datos
económicos vienen del FMI (estimación del año en curso) o, si no responde, del Banco Mundial (último año cerrado).

**Pincha en un país** para ver su ficha: crecimiento, inflación, paro, deuda, bolsa, señales de crisis (recesión,
inflación o paro muy altos, deuda muy alta), desastres activos, sus refinerías/minas/GNL clave y sus noticias.

Debajo del mapa, **Mercado relacionado** te enseña el precio de la materia prima (oro, cobre, petróleo, gas…) y las
empresas cotizadas ligadas a lo que estás viendo.

**Buques en directo (opcional):** si quieres ver la posición real de los barcos en una zona (Gibraltar, Ormuz, Canal de
la Mancha…), crea gratis una clave en **aisstream.io** (te registras con una cuenta de GitHub), pégala en el apartado
*Buques en directo* y pulsa *Ver buques ahora*. El programa escucha unos segundos y pinta los buques, con los petroleros
en rojo.

---

## 3 quinquies. Agenda, alertas, directivos y materias primas

**📅 Agenda:** pon tu lista de seguimiento (se guarda) y verás las fechas de **resultados** (el día que más se mueve una
acción), **ex-dividendo** (hay que tener la acción el día anterior para cobrar) y **pago**. Se añaden solas tus posiciones y
los valores de tu diario (marcados con ⭐). Si una empresa en la que tienes una operación abierta presenta resultados antes
de tu fecha de salida, decide antes si quieres asumir ese salto.

**🔔 Alertas:** crea avisos del tipo *SAN.MC por encima de 12,5*, *NVDA baja más de un 4 % en el día*, *noticia de Repsol con
la palabra "dividendo"*, *cualquier OPA, fusión o compra relacionada con Telefónica* o *IBE.MC presenta resultados en 3 días
o menos*. Con el programa abierto se revisan cada 5 minutos y salen como **notificación de Windows**. Si pulsas *Activar
avisos con el programa cerrado*, Windows las revisa cada 30 minutos aunque no tengas el programa abierto (con el ordenador
encendido); lo puedes desactivar en el mismo sitio.

**👔 Directivos (en 🏢 Empresa):** si los directivos **compran** acciones de su empresa con su dinero suele ser señal de
confianza; las **ventas** son más habituales y dicen menos. Sobre todo para empresas de EE. UU.

**📑 Comunicados oficiales (en 🏢 Empresa):** para empresas de EE. UU., cada documento que presentan a la SEC traducido a
lenguaje llano: hechos relevantes, alguien supera el 5 %, OPAs, fusiones, resultados… Para empresas españolas, los hechos
relevantes oficiales están en la web de la CNMV.

**⛏️ Materias primas:** precio de 18 materias primas, su gráfico, **qué países las producen** (con cuota aproximada y
cómo va su economía), lo concentrada que está la producción (si 3 países producen casi todo, un problema en uno mueve el
precio) y las empresas cotizadas expuestas.

---

## 3 sexies. Criptomonedas (🪙 Cripto)

Arriba ves cómo está el mercado en conjunto: cuánto vale todo, qué parte es bitcoin, el índice de **miedo y codicia**
(0 = pánico, 100 = euforia) y cuántos meses han pasado desde el último recorte de emisión de bitcoin.

Debajo, la tabla de precios (en dólares y en euros) con lo que ha subido o bajado cada moneda en 24 horas, 7 días, 30 días y un año.

Al elegir una moneda sale su análisis:

- **Solidez (0-10).** Si es de las que aguantan: tamaño, años cotizando, liquidez, cuántas monedas quedan por salir y para qué sirve.
  No dice si va a subir.
- **Veredicto por plazos.** Corto (días), medio (meses) y largo (años) pueden no coincidir: una moneda sólida puede estar en mal momento.
- **Hasta dónde puede moverse en 12 meses.** No es una predicción, es el rango normal según lo que se ha movido hasta ahora.
- **Peso máximo orientativo.** Qué parte de tus ahorros invertidos tendría sentido como mucho.

Importante: una criptomoneda no tiene ventas ni beneficios, así que nadie puede calcular cuánto «debería» valer. Las monedas
estables (valen siempre 1 dólar) aparecen marcadas como «no es una inversión».

## 3 septies. Plan mensual (🧺 Cartera → 📅 Plan mensual)

Sirve para revisar tu cartera y lo que compras cada mes.

1. Elige tu **perfil de riesgo**: bajo (no quieres sustos), medio o alto (aceptas caídas fuertes a cambio de más recorrido).
   Cambia cómo se juzga la cartera: lo que para un perfil bajo es demasiado especulativo, para uno alto puede estar bien.
2. En la tabla escribe cada activo (nombre o ticker), los **euros al mes** y, si ya tienes algo, cuánto en **«Ya tengo (€)»**.
   Para una compra nueva, deja «Ya tengo» vacío o en 0. Valen acciones, fondos y ETF, criptomonedas y materias primas. De 2 a 20.
3. Si un fondo no aparece en Yahoo (pasa con los indexados de MyInvestor), ponle el nombre que quieras y elige su tipo en la última columna.
4. Pulsa **Analizar cartera**.

Qué te devuelve:

- **Cómo repartiría los mismos euros al mes.** No cambia el total: mueve dinero de lo que conviene pausar a lo que conviene comprar.
  «Pausar» significa dejar de aportar, no vender. Lo que ya pesa mucho en tu cartera recibe menos. Si nada está para comprar,
  te dice cuánto queda sin asignar.
- **Por dónde flaquea.** 🔴 importante, 🟡 a vigilar, ℹ️ para que lo sepas.
- **Para qué sirve cada pieza**, **qué le falta** y **qué le sobra**.
- **🧪 ¿Y si…?** Escribe un activo para añadir, o elige alguno para quitar, y pulsa «Probar»: ves cómo cambiarían la nota, la parte
  especulativa y los puntos débiles. No toca tu plan guardado.
- **Aparte: si quisieras añadir un fondo indexado.** No cuenta para la nota. Dice qué tipo de fondo complementaría lo tuyo y cuáles
  te duplicarían lo que ya tienes.
- **Si mantienes este plan**: lo que podría valer en 5, 10 y 20 años, en tres escenarios. No es una predicción.

Revísalo cada dos o tres meses. Las reglas no conocen tus impuestos ni tu situación: úsalo como orientación.

## 3 ter. IA para leer las noticias

Por defecto, el tono de las noticias se calcula con palabras clave. En la barra lateral puedes pulsar **Instalar IA de
noticias**: instala **FinBERT**, un modelo entrenado con textos financieros que entiende mucho mejor un titular (por ejemplo,
distingue "recorta pérdidas" de "pérdidas"). Ocupa ~1 GB, se instala una sola vez, funciona en tu ordenador y es gratis.
Después cierra y abre el programa, y activa **Valorar titulares con IA**. Lee titulares en **inglés** (más cobertura
internacional). Recuerda: cuando una noticia llega a Google News, el precio suele haberse movido ya; úsala como contexto.

---

## 4. Cómo ejecutar la operación en tu bróker

Ejemplo con el plan que te da el programa: entrada 12,00 €, stop loss 11,40 €, take profit 13,20 €, 100 €, 1 mes.

1. **Compra** por el importe elegido. Puedes comprar a mercado o con **orden límite** al precio que te sugiere
   ("o límite en…", medio ATR por debajo): si no baja hasta ahí, no entras, y no pasa nada.
2. En cuanto se ejecute, pon una **orden stop (stop loss)** de venta al precio de SL. **Esto no es opcional.**
3. Pon una **orden límite de venta** al precio de TP. Si tu bróker no permite tener las dos a la vez sobre las mismas
   acciones, deja puesto el **stop** y crea una **alerta de precio** en el objetivo para vender a mano.
4. **Fecha de caducidad:** si a 1 mes (o el horizonte que elegiste) no ha tocado ninguna, **cierra** y apunta el resultado.
5. Rellena en **📒 Diario** la fecha y el precio de salida.

Trade Republic, según su información pública, admite órdenes de mercado, límite, stop y stop‑límite, y fracciones de
acción desde 1 €, con 1 € de comisión por orden. Compruébalo en tu app antes de operar.

---

## 5. Reglas de gestión del riesgo (las que más dinero te ahorrarán)

1. **Define tu capital de trading** (dinero que puedes perder sin que te afecte) y sepáralo de tu cartera de largo plazo
   (fondos indexados, plan de ahorro, etc.). No los mezcles.
2. **Nunca muevas el stop hacia abajo.** Si lo tocas, sales. Moverlo hacia arriba cuando la acción ya sube sí está bien
   (por ejemplo, al precio de entrada cuando ya vas +1 ATR a favor).
3. **Nunca promedies a la baja** (comprar más porque ha caído). Eso convierte una pérdida pequeña en una grande.
4. **Máximo 2–3 operaciones abiertas a la vez**, y no todas del mismo sector.
5. **Para tras 3 pérdidas seguidas** o si pierdes más del 6 % de tu capital de trading en un mes: una semana sin operar
   y revisa el diario.
6. **No operes por aburrimiento.** Si el escáner no da nada claro, la mejor operación es no hacer ninguna.
7. **No metas importes mayores hasta tener 20 operaciones** apuntadas con resultado positivo.

---

## 6. Cómo leer cada número

| Dato | Qué significa | Cómo usarlo |
|---|---|---|
| **Nota global (0–100)** | Resume técnica + noticias + sector + analistas | ≥ 65 favorable, ≤ 40 desfavorable |
| **Técnica (−6 a +6)** | Tendencia, impulso, RSI y mercado | ≥ +3 para plantearse entrar |
| **Contexto (−3 a +3)** | Tono de noticias, sector frente al S&P 500, potencial según analistas | Suma o resta confianza |
| **ATR** | Lo que se mueve la acción en un día normal | El SL se pone a ~2 ATR para que el ruido no lo salte |
| **RSI** | 0–100: >70 sobrecomprada, <30 sobrevendida | Mejor entrar con 40–60 en tendencia alcista |
| **Media de 200 sesiones** | Tendencia de fondo | Por encima = alcista; por debajo = mejor no comprar a corto |
| **Stop loss (SL)** | Precio al que sales si te equivocas | Fíjalo siempre en el bróker |
| **Take profit (TP)** | Precio objetivo para recoger beneficios | 2 veces lo que arriesgas (2:1) |
| **Prob. de llegar al TP / SL** | En miles de simulaciones, qué sale antes | Con 2:1, basta ~35–40 % de TP para ganar a la larga (sin costes) |
| **Resultado esperado** | Media en € de todas las simulaciones, con costes | Si es negativo, no entres |
| **Mínimo / máximo probable** | Lo que suele tocar en 1 día, 1 semana, 2 semanas o 1 mes | Para no asustarte con movimientos normales |
| **Cierre P10–P90** | Entre esos precios termina el periodo 8 de cada 10 veces | Rango razonable de llegada |
| **Factor de beneficio** | Lo ganado ÷ lo perdido en la prueba histórica | > 1,3 razonable; < 1 la regla pierde |
| **R** (en el diario) | Cuántas veces el riesgo ganas o pierdes | Media > 0,2 R es buena señal |

---

## 7. Checklist antes de pulsar "comprar"

- [ ] El mercado no está en tendencia bajista ni con el VIX > 25.
- [ ] Veredicto 🟢 y técnica ≥ +3.
- [ ] RSI entre 40 y 60 (no estoy persiguiendo una subida).
- [ ] Resultado esperado positivo con mis comisiones.
- [ ] La prueba histórica gana en este valor y mejor que entrar a ciegas.
- [ ] No hay resultados trimestrales en los próximos días (o acepto el riesgo).
- [ ] Sé exactamente dónde está mi stop y lo voy a poner en el bróker.
- [ ] Si salta el stop, la pérdida en € me parece asumible.
- [ ] Lo he apuntado en el diario.

---

## 8. Revisión mensual (15 minutos)

Abre **📒 Diario**:
- **Acierto** y **resultado total**: ¿ganas o pierdes de verdad, después de comisiones?
- **Respeto del stop**: debería ser casi 100 %. Si no, el problema no es la señal, es la disciplina.
- Lee la columna **"Qué aprendí"** de las perdedoras: ¿se repite algo? (entrar con RSI alto, operar con resultados cerca,
  mercado bajista…). Conviértelo en una regla nueva.
- Tras **20 operaciones**: si vas en negativo, para y replantea (más importe por operación, menos operaciones, o
  pasar esa cantidad a tu cartera de largo plazo). Si vas en positivo, sigue igual; no subas el importe de golpe.

---

## 9. Impuestos en España (resumen)

- Las ganancias por vender acciones tributan en la **base del ahorro del IRPF**: 19 % hasta 6.000 € de ganancia
  y 21 % de 6.000 a 50.000 €.
- Las **pérdidas** compensan ganancias, **pero ojo con la regla de los dos meses**: si vendes con pérdida y vuelves a
  comprar la misma acción dentro de los 2 meses anteriores o posteriores, esa pérdida no se puede aplicar todavía.
  Con trading frecuente sobre los mismos valores esto pasa a menudo.
- Comprar acciones españolas de más de 1.000 M€ de capitalización paga un **0,2 %** de impuesto sobre transacciones
  financieras (el programa ya lo incluye en sus cálculos).
- Guarda los extractos de tu bróker; para dudas concretas, consulta con un asesor fiscal.

---

## 10. Problemas frecuentes

| Problema | Solución |
|---|---|
| La IA de noticias no se activa tras instalarla | Cierra la ventana negra y vuelve a abrir `iniciar.bat` |
| El mapa mundial tarda la primera vez | Descarga datos de varias fuentes (10–30 s). Después queda guardado y va rápido |
| La búsqueda en informes de otras empresas tarda | Normal la primera vez (lee hasta 15–40 informes). Luego queda guardada una semana |
| `iniciar.bat` se cierra al momento | Asegúrate de haber extraído el zip. Ábrelo de nuevo; si persiste, instala Python a mano (sección 1) |
| "No pude obtener… ahora mismo" | Fuente gratuita saturada o sin conexión. Espera unos minutos; si había un dato guardado, se usa ese |
| El mapa de energía tarda o falla | Los servidores de OpenStreetMap van saturados a ratos. Prueba una zona más pequeña o más tarde |
| No encuentra un valor | Prueba con el ticker de Yahoo Finance (p. ej. `ITX.MC`, `RHM.DE`, `BP.L`) |
| Leer informes de la SEC pide nombre y correo | Es obligatorio para la SEC. Se guarda solo en tu ordenador |
| Quiero comprobar todas las fuentes | En la carpeta del programa: `.venv\Scripts\python.exe comprobar_conexion.py` |
| Los datos parecen viejos | Barra lateral → **Borrar caché de datos** |

---

## 11. Qué NO hace el programa

- **No da precios al segundo.** Yahoo Finance lleva algo de retraso; para entrar, mira el precio en tu bróker.
- **No sabe el futuro.** Las simulaciones repiten estadísticamente el pasado; las noticias se valoran con palabras clave.
- **No tiene histórico de noticias**, así que la prueba histórica solo mide la parte técnica.
- **No opera por ti.** Todas las órdenes las pones tú en tu bróker.

Tus datos (diario, posiciones, tu tabla de relaciones) se guardan solo en tu ordenador, en la carpeta
`.radar_inversor` de tu usuario.
