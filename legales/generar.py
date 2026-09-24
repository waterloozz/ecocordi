#!/usr/bin/env python3
# ============================================================
#  ECOCORDI - Genera las páginas legales (términos, privacidad,
#  cookies y devoluciones) con el mismo diseño y los mismos datos
#  de la empresa en todas.
#
#  Para cambiar un texto: edita este archivo y ejecuta
#      python3 legales/generar.py
#  Para completar los datos de la empresa: rellena EMPRESA (abajo)
#  y vuelve a ejecutar. Si cambias el contenido de los Términos o la
#  Política de privacidad, sube también VERSION_TERMINOS en server.py.
#
#  IMPORTANTE: estos textos son un borrador bien fundado, pero deben
#  ser revisados por un abogado antes de publicar el sitio.
# ============================================================
import html
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FECHA = "24 de septiembre de 2026"
CORREO = "pinturas@ecocordi.cl"

# Datos oficiales de la empresa. None = todavía no los tenemos.
EMPRESA = {
    "Nombre comercial": "Pinturas Ecocordi",
    "Razón social": None,
    "RUT": None,
    "Domicilio legal": None,
    "Representante legal": None,
    "Teléfono": None,
    "Correo": CORREO,
}


def datos_empresa():
    filas = []
    for campo, valor in EMPRESA.items():
        if valor is None:
            dd = '<dd class="por-confirmar">Por confirmar</dd>'
        elif campo == "Correo":
            dd = f'<dd><a href="mailto:{valor}">{valor}</a></dd>'
        else:
            dd = f"<dd>{html.escape(valor)}</dd>"
        filas.append(f"      <div><dt>{campo}</dt>{dd}</div>")
    return '    <dl class="datos-empresa">\n' + "\n".join(filas) + "\n    </dl>"


def pendiente(texto):
    return f'    <div class="legal__pendiente"><p><strong>Pendiente:</strong> {texto}</p></div>'


PAGINAS = [
    ("terminos.html", "Términos y condiciones", "Términos y <em>condiciones</em>"),
    ("privacidad.html", "Política de privacidad", "Política de <em>privacidad</em>"),
    ("cookies.html", "Política de cookies", "Política de <em>cookies</em>"),
    ("devoluciones.html", "Cambios y devoluciones", "Cambios y <em>devoluciones</em>"),
]


def otras(actual):
    enlaces = "".join(f'<li><a href="{a}">{t}</a></li>' for a, t, _ in PAGINAS if a != actual)
    enlaces += '<li><a href="creditos.html">Créditos de fotografías</a></li>'
    return f'''    <nav class="legal__otras" aria-label="Otras políticas">
      <h2>Otras políticas</h2>
      <ul>{enlaces}</ul>
    </nav>'''


def pagina(archivo, titulo, titulo_html, cuerpo):
    return f'''<!DOCTYPE html>
<html lang="es" data-luz="manana">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{titulo} | Pinturas Ecocordi</title>
  <link rel="icon" href="img/favicon.png" type="image/png" />
  <link rel="stylesheet" href="css/estilos.css" />
  <script src="js/luz.js"></script>
</head>
<body>
  <!-- Página generada por legales/generar.py: edita ese archivo, no este. -->
  <a class="saltar" href="#contenido">Saltar al contenido</a>
  <header class="cabecera">
    <div class="contenedor cabecera__interior">
      <a href="index.html" class="marca" aria-label="Pinturas Ecocordi, volver a la tienda">
        <span class="marca__nombre">Ecocordi</span>
        <span class="marca__sub">Pinturas</span>
      </a>
      <div class="cabecera__acciones">
        <a href="index.html" class="cuenta__link">Volver a la tienda</a>
      </div>
    </div>
  </header>
  <main class="contenedor legal" id="contenido">
    <h1>{titulo_html}</h1>
    <p class="legal__fecha">Última actualización: {FECHA}.</p>
{cuerpo}
{otras(archivo)}
  </main>
</body>
</html>
'''


# ------------------------------------------------------------------
TERMINOS = f'''
    <div class="legal__resumen">
      <p><strong>En resumen:</strong> hoy el sitio no cobra en línea. Cuando envías un pedido, queda
      registrado y Pinturas Ecocordi te contacta para coordinar el pago y la entrega o retiro.
      Tienes derecho a retracto y a garantía legal según la Ley 19.496 (ver
      <a href="devoluciones.html">Cambios y devoluciones</a>). Nada de estos términos limita
      los derechos que te da la ley.</p>
    </div>

    <h2>1. Quién vende</h2>
    <p>Este sitio es operado por Pinturas Ecocordi:</p>
{datos_empresa()}
{pendiente("completar razón social, RUT, domicilio, representante legal y teléfono, que el Reglamento de Comercio Electrónico exige informar antes y después de la compra.")}

    <h2>2. Aceptación de estos términos</h2>
    <p>Para crear una cuenta o enviar un pedido debes aceptar expresamente estos términos marcando
    la casilla correspondiente. Guardamos la fecha y la versión que aceptaste. Puedes leer, guardar o
    imprimir esta página cuando quieras; la versión vigente es la que tiene la fecha indicada arriba.</p>

    <h2>3. Tu cuenta</h2>
    <ul>
      <li>Puedes crear tu cuenta con tu nombre, un correo válido y una contraseña de al menos 8 caracteres, o con tu cuenta de Google (“Continuar con Google”). Una cuenta creada con Google entra solo con Google.</li>
      <li>Eres responsable de mantener tu contraseña en reserva. Si crees que alguien la conoce, escríbenos.</li>
      <li>Puedes eliminar tu cuenta cuando quieras desde “Mis pedidos” (ver la <a href="privacidad.html">Política de privacidad</a>).</li>
      <li>Si eres menor de edad, pide a tu madre, padre o representante legal que haga la compra.</li>
    </ul>

    <h2>4. Productos, imágenes y precios</h2>
    <ul>
      <li>Cada producto muestra su nombre, descripción, superficies para las que sirve, precio y disponibilidad (“Quedan N” o “Agotado”) antes de que envíes tu pedido.</li>
      <li>Las fotografías son <strong>imágenes referenciales</strong> de superficies y ambientes: no muestran el envase ni el color exacto del producto.</li>
      <li>Los precios están en pesos chilenos. El precio que se aplica es el vigente al momento de enviar tu pedido.</li>
    </ul>
{pendiente("confirmar si los precios incluyen IVA e indicarlo junto a cada precio; informar costos de despacho, zonas y plazos de entrega o retiro, y los medios de pago aceptados.")}

    <h2>5. Cómo funciona un pedido</h2>
    <ul>
      <li>Antes de enviarlo, el carrito te muestra los productos, cantidades, precios y el total.</li>
      <li>Al enviarlo, el pedido queda registrado con estado “Pendiente” y las unidades quedan reservadas.</li>
      <li><strong>No se cobra nada en línea.</strong> Pinturas Ecocordi te contactará al correo de tu cuenta para coordinar el pago y la entrega o retiro.</li>
      <li>Puedes seguir el estado de tus pedidos (pendiente, pagado, enviado, entregado o cancelado) en “Mis pedidos”.</li>
      <li>Mientras tu pedido no esté pagado, puedes pedir su anulación escribiendo a <a href="mailto:{CORREO}">{CORREO}</a>, sin costo.</li>
    </ul>
{pendiente("definir y describir el proceso real de confirmación, pago y entrega, y enviar al cliente una copia escrita de cada pedido (por ejemplo, un correo automático). El Reglamento de Comercio Electrónico exige esa copia; hoy el sitio no envía correos.")}

    <h2>6. Retracto y garantía legal</h2>
    <p>Tienes derecho a retracto de 10 días en compras a distancia y a la garantía legal de 6 meses,
    con las condiciones y excepciones que explicamos en <a href="devoluciones.html">Cambios y devoluciones</a>.</p>

    <h2>7. Propiedad intelectual</h2>
    <p>El nombre y el logo de Pinturas Ecocordi pertenecen a la empresa. Las fotografías son de
    Unsplash y se usan bajo su licencia (ver <a href="creditos.html">Créditos</a>). Las tipografías
    se usan bajo la licencia SIL Open Font License.</p>

    <h2>8. Uso del sitio</h2>
    <p>No está permitido usar el sitio para fines ilícitos, intentar acceder a cuentas ajenas o
    afectar su funcionamiento. Podemos suspender cuentas que se usen de esa forma.</p>

    <h2>9. Consultas y reclamos</h2>
    <p>Para consultas, reclamos, cambios o devoluciones escríbenos a <a href="mailto:{CORREO}">{CORREO}</a>
    indicando tu número de pedido. También puedes acudir al Servicio Nacional del Consumidor
    (<a href="https://www.sernac.cl" target="_blank" rel="noopener">SERNAC</a>) o al Juzgado de Policía
    Local competente, según la Ley 19.496 sobre Protección de los Derechos de los Consumidores.</p>

    <h2>10. Ley aplicable y cambios</h2>
    <p>Estos términos se rigen por las leyes de Chile. Si los cambiamos, publicaremos la nueva versión
    con su fecha; cada pedido se rige por la versión que aceptaste al enviarlo.</p>
'''

PRIVACIDAD = f'''
    <div class="legal__resumen">
      <p><strong>En resumen:</strong> pedimos solo tu nombre, tu correo y una contraseña (o los recibimos de
      Google si eliges “Continuar con Google”), y guardamos tus pedidos. Los usamos para tu cuenta y tus pedidos. No los vendemos, no los usamos para publicidad
      y no usamos herramientas de analítica ni de seguimiento. Puedes eliminar tu cuenta cuando quieras.</p>
    </div>

    <h2>1. Responsable de tus datos</h2>
{datos_empresa()}
{pendiente("completar la identificación del responsable (razón social, RUT y domicilio).")}

    <h2>2. Qué datos tratamos</h2>
    <ul>
      <li><strong>Cuenta:</strong> nombre, correo electrónico y contraseña. La contraseña se guarda transformada (“hash” PBKDF2 con sal): nadie, ni siquiera nosotros, puede leerla.</li>
      <li><strong>Si entras con Google:</strong> Google nos envía tu nombre, tu correo (verificado por Google), un identificador de tu cuenta de Google y la dirección de tu foto de perfil. Guardamos solo el nombre, el correo y el identificador; la foto no. Nunca recibimos tu contraseña de Google.</li>
      <li><strong>Pedidos:</strong> productos, cantidades, precios, total, fecha y estado.</li>
      <li><strong>Consentimiento:</strong> la fecha y la versión de los términos que aceptaste.</li>
      <li><strong>Sesión:</strong> una cookie técnica que te mantiene conectado (ver la <a href="cookies.html">Política de cookies</a>).</li>
      <li><strong>Seguridad:</strong> si un intento de iniciar sesión o registrarse falla, la dirección IP se usa solo en la memoria del servidor para bloquear intentos repetidos, y se descarta a los pocos minutos (el bloqueo dura 10). No se guarda en la base de datos ni en registros.</li>
    </ul>
    <p>No pedimos RUT, dirección, teléfono ni datos de tarjetas, y no tratamos datos sensibles.</p>

    <h2>3. Para qué los usamos</h2>
    <ul>
      <li>Crear y mantener tu cuenta.</li>
      <li>Registrar tus pedidos, mostrarte su estado y contactarte para coordinar el pago y la entrega.</li>
      <li>Proteger el sitio y tu cuenta (por ejemplo, frente a intentos de adivinar contraseñas).</li>
      <li>Cumplir obligaciones legales, como las de protección al consumidor y tributarias.</li>
    </ul>
    <p>No los usamos para publicidad, no hacemos perfiles y no los vendemos ni los cedemos.</p>

    <h2>4. Base para usarlos</h2>
    <p>Tu consentimiento, que entregas al marcar la casilla al crear tu cuenta, y la necesidad de
    gestionar los pedidos que tú envías. Puedes retirar tu consentimiento eliminando tu cuenta.</p>

    <h2>5. Con quién los compartimos</h2>
    <p><strong>Google:</strong> si eliges “Continuar con Google”, Google sabrá que iniciaste sesión en
    Pinturas Ecocordi y trata esos datos según su propia
    <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">política de privacidad</a>.
    Es opcional: siempre puedes usar correo y contraseña.</p>
    <p>Fuera de eso, con nadie para fines propios de otras empresas. Solo podrían acceder a ellos los proveedores
    que sean necesarios para operar el sitio (por ejemplo, el servicio donde se aloje) y las
    autoridades cuando la ley lo exija.</p>
{pendiente("cuando se elija dónde publicar el sitio, indicar aquí el proveedor de alojamiento y, si guarda los datos fuera de Chile, informar esa transferencia internacional.")}

    <h2>6. Cuánto tiempo los guardamos</h2>
    <ul>
      <li><strong>Cuenta:</strong> hasta que la elimines.</li>
      <li><strong>Sesión:</strong> 7 días, o hasta que cierres sesión.</li>
      <li><strong>Pedidos:</strong> el tiempo que exijan las normas tributarias y de protección al consumidor. Si eliminas tu cuenta, tus pedidos quedan registrados sin tu nombre ni tu correo.</li>
      <li><strong>IP de intentos fallidos:</strong> unos 10 minutos, solo en memoria.</li>
    </ul>

    <h2>7. Tus derechos</h2>
    <p>Según la Ley 19.628 sobre Protección de la Vida Privada puedes pedir <strong>acceso</strong>,
    <strong>rectificación</strong>, <strong>cancelación</strong> (eliminación) y <strong>oposición</strong>
    respecto de tus datos. Desde el 1 de diciembre de 2026, con la entrada en vigencia de la Ley 21.719,
    se suman los derechos de <strong>portabilidad</strong> y <strong>bloqueo</strong>.</p>
    <ul>
      <li>Para eliminar tus datos: entra a tu cuenta, abre “Mis pedidos” y usa “Eliminar mi cuenta”. Eso también desvincula tu cuenta de Google; para quitarle el acceso desde Google, entra a <a href="https://myaccount.google.com/connections" target="_blank" rel="noopener">tus conexiones de Google</a>.</li>
      <li>Para cualquier otra solicitud: escribe a <a href="mailto:{CORREO}">{CORREO}</a> desde el correo de tu cuenta. Responderemos dentro de los plazos que fija la ley.</li>
      <li>Si no quedas conforme, puedes recurrir a los tribunales y, desde el 1 de diciembre de 2026, a la Agencia de Protección de Datos Personales.</li>
    </ul>

    <h2>8. Cómo protegemos tus datos</h2>
    <p>Contraseñas transformadas con PBKDF2, cookie de sesión inaccesible para JavaScript (HttpOnly),
    límite de intentos de inicio de sesión, política de seguridad de contenidos (CSP) y acceso al panel
    de administración solo para administradores. Ningún sistema es infalible: si ocurriera un incidente
    que afecte tus datos, te informaremos según lo exija la ley.</p>

    <h2>9. Cambios en esta política</h2>
    <p>Si la cambiamos, publicaremos la nueva versión con su fecha. Si un cambio implica usar tus datos
    para algo nuevo, te pediremos tu consentimiento otra vez.</p>
'''

COOKIES = f'''
    <div class="legal__resumen">
      <p><strong>En resumen:</strong> usamos una sola cookie, necesaria para iniciar sesión, y guardamos
      en tu propio navegador el carrito y la luz que eliges. No usamos cookies de analítica, de
      publicidad ni de terceros. Por eso no te pedimos que aceptes cookies.</p>
    </div>

    <h2>1. Qué guardamos en tu navegador</h2>
    <div class="legal__tabla">
      <table>
        <thead><tr><th scope="col">Nombre</th><th scope="col">Tipo</th><th scope="col">Para qué</th><th scope="col">Duración</th></tr></thead>
        <tbody>
          <tr><td><code>sesion</code></td><td>Cookie propia, necesaria</td><td>Mantener tu sesión iniciada. No es accesible para JavaScript (HttpOnly).</td><td>7 días, o hasta que cierres sesión</td></tr>
          <tr><td><code>google_estado</code></td><td>Cookie propia, necesaria</td><td>Solo si usas “Continuar con Google”: protege ese inicio de sesión para que otro sitio no pueda completarlo a tu nombre.</td><td>Máximo 10 minutos; se borra al terminar</td></tr>
          <tr><td><code>carrito_ecocordi</code></td><td>Almacenamiento local del navegador</td><td>Recordar los productos de tu carrito aunque cierres la página. Queda solo en tu equipo.</td><td>Hasta que vacíes el carrito o borres los datos del navegador</td></tr>
          <tr><td><code>luz_ecocordi</code></td><td>Almacenamiento local del navegador</td><td>Recordar si elegiste ver la página con luz de mañana, tarde o noche.</td><td>Hasta que borres los datos del navegador</td></tr>
        </tbody>
      </table>
    </div>

    <h2>2. Lo que no usamos</h2>
    <p>No usamos Google Analytics, píxeles de redes sociales, publicidad, mapas incrustados ni
    contenido de otros sitios. Si eliges “Continuar con Google”, pasarás por la página de Google,
    que usa sus propias cookies. Los enlaces a Instagram, Facebook, Google Maps y Unsplash solo te
    llevan a esos sitios; una vez allí, rigen sus propias políticas.</p>

    <h2>3. ¿Necesitamos tu consentimiento?</h2>
    <p>Lo que guardamos es necesario para el servicio que tú pides (iniciar sesión, conservar tu
    carrito) o recuerda una preferencia que tú eliges. No sirve para identificarte ante terceros ni
    para seguir tu navegación. Por eso no mostramos un aviso para aceptar cookies.</p>
    <p>Si en el futuro agregamos herramientas de analítica o publicidad, te pediremos
    <strong>antes</strong> tu consentimiento expreso, con la opción de rechazarlas tan fácil como aceptarlas,
    como exige la normativa de protección de datos personales.</p>

    <h2>4. Cómo borrarlas</h2>
    <p>La cookie de sesión se borra al usar “Salir”. Todo lo demás se puede borrar desde la configuración
    de tu navegador (“Borrar datos de navegación” o “Cookies y datos de sitios”). Si lo haces, se vaciará
    tu carrito y la página volverá a elegir la luz según la hora.</p>
'''

DEVOLUCIONES = f'''
    <div class="legal__resumen">
      <p><strong>En resumen:</strong> tienes <strong>10 días</strong> desde que recibes tu compra para
      arrepentirte (derecho a retracto), salvo en pinturas preparadas a pedido y productos ya aplicados o usados.
      Y si un producto sale malo, tienes <strong>6 meses</strong> de garantía legal para elegir cambio,
      reparación o devolución del dinero.</p>
    </div>

    <h2>1. Derecho a retracto (compras por internet)</h2>
    <p>Según el artículo 3 bis de la Ley 19.496, en las compras a distancia puedes dejar sin efecto la
    compra, sin dar explicaciones, dentro de <strong>10 días desde que recibes el producto</strong>.</p>
    <h3>Cómo ejercerlo</h3>
    <ul>
      <li>Escríbenos a <a href="mailto:{CORREO}">{CORREO}</a> dentro del plazo, indicando tu número de pedido.</li>
      <li>Devuelve el producto sin usar y con sus elementos originales: envase, etiquetas, sellos, manuales o cajas.</li>
      <li>Te devolveremos <strong>todo lo que pagaste, sin descuentos por gastos</strong>, lo antes posible y siempre antes de 45 días desde que nos avisas.</li>
    </ul>
    <h3>Cuándo no aplica</h3>
    <p>De acuerdo con el reglamento de exclusiones al derecho de retracto (vigente desde el 28 de febrero de 2025),
    no se puede ejercer en:</p>
    <ul>
      <li><strong>Pinturas preparadas a pedido</strong>, por ejemplo, entonadas en el color que pediste.</li>
      <li><strong>Productos que ya no se pueden volver a vender</strong> en las condiciones en que se ofrecieron, porque fueron aplicados o usados.</li>
    </ul>
    <p>Estas excepciones no se aplican si el producto llegó con fallas o no corresponde a lo que pediste:
    en ese caso rige la garantía legal.</p>
{pendiente("definir con asesoría legal cómo y dónde se devuelven los productos (sucursal o retiro), quién asume el costo del envío de vuelta y cómo informar las exclusiones del retracto en la forma que exige su reglamento.")}

    <h2>2. Garantía legal de 6 meses</h2>
    <p>Según los artículos 19 a 21 de la Ley 19.496 (plazo ampliado a 6 meses por la Ley 21.398), si un
    producto tiene fallas o defectos de fabricación, no sirve para el uso al que está destinado, o no
    corresponde a lo que compraste, dentro de <strong>6 meses desde que lo recibes</strong> puedes elegir:</p>
    <ul>
      <li>el <strong>cambio</strong> del producto,</li>
      <li>su <strong>reparación</strong> gratuita, o</li>
      <li>la <strong>devolución del dinero</strong> que pagaste.</li>
    </ul>
    <p>La garantía no cubre daños causados por un mal uso o una aplicación que no siga las instrucciones
    del envase. Para usarla, escríbenos a <a href="mailto:{CORREO}">{CORREO}</a> con tu número de pedido
    y el comprobante de compra.</p>

    <h2>3. Pedidos que aún no has pagado</h2>
    <p>Como hoy el sitio no cobra en línea, puedes anular sin costo un pedido que todavía no pagaste
    escribiendo a <a href="mailto:{CORREO}">{CORREO}</a>.</p>

    <h2>4. Cambios por otros motivos</h2>
    <p>Si quieres cambiar un producto que no tiene fallas y fuera del derecho a retracto, escríbenos y
    revisaremos tu caso.</p>
{pendiente("si la empresa ofrece una política de cambios voluntaria (por ejemplo, “30 días para cambios con boleta”), escribirla aquí. No se debe prometer algo que la empresa no haya decidido.")}

    <h2>5. Contacto</h2>
{datos_empresa()}
'''

CUERPOS = {"terminos.html": TERMINOS, "privacidad.html": PRIVACIDAD, "cookies.html": COOKIES, "devoluciones.html": DEVOLUCIONES}

if __name__ == "__main__":
    for archivo, titulo, titulo_html in PAGINAS:
        ruta = os.path.join(BASE, archivo)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(pagina(archivo, titulo, titulo_html, CUERPOS[archivo]))
        print("generada:", archivo)
