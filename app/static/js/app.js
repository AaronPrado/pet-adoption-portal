// Pide confirmación antes de enviar los formularios marcados con data-confirmar.
// El texto se lee de un atributo (escapado por Jinja) en lugar de interpolarlo
// en un manejador onclick, donde el escapado HTML no protege contra XSS.
document.addEventListener('submit', function (event) {
    var mensaje = event.target.dataset.confirmar;
    if (mensaje && !window.confirm(mensaje)) {
        event.preventDefault();
    }
});
