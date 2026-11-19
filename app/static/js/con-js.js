// Se carga en <head> de base.html, sin defer: marca <html> antes del primer
// pintado para que el CSS pliegue los menús sin que se vean abiertos un
// instante. Sin JS no hay .con-js y la navegación se ve entera.
document.documentElement.classList.add('con-js');
