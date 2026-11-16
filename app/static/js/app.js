// Pide confirmación antes de enviar los formularios marcados con data-confirmar.
// El texto se lee de un atributo (escapado por Jinja) en lugar de interpolarlo
// en un manejador onclick, donde el escapado HTML no protege contra XSS.
document.addEventListener('submit', function (event) {
    var mensaje = event.target.dataset.confirmar;
    if (mensaje && !window.confirm(mensaje)) {
        event.preventDefault();
    }
});

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
