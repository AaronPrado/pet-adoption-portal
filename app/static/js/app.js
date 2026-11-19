// Pide confirmación antes de enviar los formularios marcados con data-confirmar.
// El texto se lee de un atributo (escapado por Jinja) en lugar de interpolarlo
// en un manejador onclick, donde el escapado HTML no protege contra XSS.
document.addEventListener('submit', function (event) {
    var mensaje = event.target.dataset.confirmar;
    if (event.defaultPrevented) {
        return;  // ya enviándose (ver más abajo): no se vuelve a preguntar
    }
    if (mensaje && !window.confirm(mensaje)) {
        event.preventDefault();
    }
});

// Protección contra el doble envío (P-20). Un formulario POST que sale de
// verdad se marca con aria-busy="true" y se ignoran sus envíos siguientes.
// No se deshabilita ningún botón: un botón deshabilitado deja de enviar su
// name/value. La marca se pone al final de la propagación (en window), así
// que no la recibe un envío cancelado al no confirmar; uno que no supera la
// validación HTML5 (campo obligatorio, foto demasiado grande) ni siquiera
// lanza el evento submit.
var TEXTO_ENVIANDO = 'Enviando…';
// Si la respuesta no llega (red caída, envío detenido, una descarga que no
// cambia de página), el formulario se libera pasado este tiempo.
var LIBERAR_TRAS_MS = 10000;
var liberaciones = new WeakMap();

// aria-busy no se anuncia: el estado se lee en una región role="status",
// que tiene que existir antes de cambiar su texto para que se anuncie.
var estadoEnvio = document.createElement('div');
estadoEnvio.setAttribute('role', 'status');
estadoEnvio.className = 'visually-hidden';
document.body.appendChild(estadoEnvio);

function anunciarEnvio() {
    // Vaciar y volver a escribir hace que se repita el anuncio
    estadoEnvio.textContent = '';
    window.setTimeout(function () {
        estadoEnvio.textContent = TEXTO_ENVIANDO;
    }, 50);
}

function liberar(formulario) {
    window.clearTimeout(liberaciones.get(formulario));
    liberaciones.delete(formulario);
    formulario.removeAttribute('aria-busy');
    if (!document.querySelector('form[aria-busy="true"]')) {
        estadoEnvio.textContent = '';
    }
}

function enviaPorPost(event) {
    var boton = event.submitter;
    var metodo = boton && boton.hasAttribute('formmethod') ? boton.formMethod : event.target.method;
    var destino = (boton && boton.getAttribute('formtarget')) || event.target.target;
    return metodo === 'post' && (!destino || destino === '_self');
}

document.addEventListener('submit', function (event) {
    if (event.target.getAttribute('aria-busy') === 'true') {
        event.preventDefault();
        anunciarEnvio();
    }
}, true);

window.addEventListener('submit', function (event) {
    var formulario = event.target;
    if (!event.defaultPrevented && enviaPorPost(event)) {
        formulario.setAttribute('aria-busy', 'true');
        anunciarEnvio();
        liberaciones.set(formulario, window.setTimeout(function () {
            liberar(formulario);
        }, LIBERAR_TRAS_MS));
    }
});

// Al volver con «Atrás», la bfcache restaura la página tal como se dejó:
// los formularios vuelven a estar disponibles.
window.addEventListener('pageshow', function () {
    Array.prototype.forEach.call(document.querySelectorAll('form[aria-busy="true"]'), liberar);
});

// Tras un envío con errores, el foco va al resumen (macro resumen_errores)
// para que el lector de pantalla lo lea y el teclado empiece por él.
var resumenErrores = document.querySelector('[data-resumen-errores]');
if (resumenErrores) {
    resumenErrores.focus();
}

// Añade o quita un id de la lista de aria-describedby de un campo.
function describirCon(campo, id, activar) {
    var ids = (campo.getAttribute('aria-describedby') || '').split(/\s+/).filter(function (actual) {
        return actual && actual !== id;
    });
    if (activar) {
        ids.unshift(id);
    }
    if (ids.length) {
        campo.setAttribute('aria-describedby', ids.join(' '));
    } else {
        campo.removeAttribute('aria-describedby');
    }
}

// Muestra el error junto al campo (en <id>-error, que se crea si no existe) o,
// sin mensaje, lo quita junto con las marcas de campo no válido.
function mostrarErrorDeCampo(campo, mensaje) {
    var id = campo.id + '-error';
    var nodo = document.getElementById(id);
    if (mensaje) {
        if (!nodo) {
            nodo = document.createElement('div');
            nodo.id = id;
            nodo.className = 'invalid-feedback';
            campo.insertAdjacentElement('afterend', nodo);
        }
        nodo.textContent = mensaje;
    } else if (nodo) {
        nodo.remove();
    }
    campo.classList.toggle('is-invalid', Boolean(mensaje));
    if (mensaje) {
        campo.setAttribute('aria-invalid', 'true');
    } else {
        campo.removeAttribute('aria-invalid');
    }
    describirCon(campo, id, Boolean(mensaje));
}

// Rechaza en el navegador los archivos que superan data-max-bytes. El servidor
// descarta entera una petición demasiado grande (413) y no puede conservar lo
// escrito en el formulario; así ni siquiera se envía. Elegir otro archivo (o
// quitarlo) borra también el error que dio el servidor con el anterior.
document.addEventListener('change', function (event) {
    var campo = event.target;
    var maximo = Number(campo.dataset && campo.dataset.maxBytes);
    if (campo.type !== 'file' || !maximo) {
        return;
    }
    var demasiado = Array.prototype.some.call(campo.files, function (archivo) {
        return archivo.size > maximo;
    });
    var mensaje = demasiado ? campo.dataset.mensajeTamano : '';
    campo.setCustomValidity(mensaje);
    mostrarErrorDeCampo(campo, mensaje);
    if (demasiado) {
        campo.reportValidity();
    }
});

// Navegación de base.html: menú móvil y menú de usuario con el patrón
// disclosure (un botón con aria-expanded y aria-controls). El HTML llega
// cerrado y con-js.js ya ha marcado <html> con .con-js, que activa el CSS
// que oculta el panel que sigue a un botón cerrado.
function panelDe(boton) {
    return document.getElementById(boton.getAttribute('aria-controls') || '');
}

// Un botón sin panel (aria-controls roto) se ignora
var desplegables = Array.prototype.filter.call(document.querySelectorAll('[data-desplegable]'), panelDe);

function estaAbierto(boton) {
    return boton.getAttribute('aria-expanded') === 'true';
}

function contiene(boton, nodo) {
    var panel = panelDe(boton);
    return Boolean(nodo) && (boton.contains(nodo) || Boolean(panel && panel.contains(nodo)));
}

function abrir(boton, abierto) {
    boton.setAttribute('aria-expanded', String(abierto));
}

desplegables.forEach(function (boton) {
    boton.addEventListener('click', function () {
        abrir(boton, !estaAbierto(boton));
    });
    // Se cierra cuando el foco sale del botón y de su panel (relatedTarget
    // es null si la ventana pierde el foco: entonces se deja como está)
    [boton, panelDe(boton)].forEach(function (zona) {
        zona.addEventListener('focusout', function (event) {
            if (event.relatedTarget && !contiene(boton, event.relatedTarget)) {
                abrir(boton, false);
            }
        });
    });
});

// Clic fuera: cierra los desplegables abiertos que no contienen el clic
document.addEventListener('click', function (event) {
    desplegables.forEach(function (boton) {
        if (estaAbierto(boton) && !contiene(boton, event.target)) {
            abrir(boton, false);
        }
    });
});

// Escape cierra el desplegable abierto más interno que tiene el foco (el de
// usuario va dentro del menú móvil) y devuelve el foco a su botón
document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') {
        return;
    }
    var boton = desplegables.slice().reverse().filter(function (candidato) {
        return estaAbierto(candidato) && contiene(candidato, document.activeElement);
    })[0];
    if (boton) {
        abrir(boton, false);
        boton.focus();
    }
});
