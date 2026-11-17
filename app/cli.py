"""
Comandos de línea de comandos de la aplicación (flask <comando>).
"""

import click
from sqlalchemy import select

from app import db, fotos
from app.models import Mascota, Usuario
from app.routes.auth import PASSWORD_MIN_LENGTH


def register_commands(app):
    """Registra los comandos CLI en la app."""

    @app.cli.command('crear-admin')
    @click.option('--email', prompt=True, help='Email del administrador')
    @click.option('--nombre', prompt=True, help='Nombre del administrador')
    @click.password_option(help='Contraseña (se pide sin mostrarla)')
    def crear_admin(email, nombre, password):
        """Crea un administrador o asciende a admin un usuario existente."""
        if len(password) < PASSWORD_MIN_LENGTH:
            raise click.BadParameter(
                f'Debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.', param_hint='password'
            )

        email = email.strip().lower()
        usuario = Usuario.query.filter_by(email=email).first()
        if usuario:
            usuario.rol = 'admin'
            usuario.set_password(password)
            mensaje = f'Usuario {email} actualizado como administrador.'
        else:
            usuario = Usuario(email=email, nombre=nombre.strip(), password=password, rol='admin')
            db.session.add(usuario)
            mensaje = f'Administrador {email} creado.'

        db.session.commit()
        click.echo(mensaje)

    @app.cli.command('exportar-fotos')
    @click.argument('destino', type=click.Path(file_okay=False))
    def exportar_fotos(destino):
        """
        Copia en DESTINO las fotos propias de las mascotas, con sus variantes.

        Lee del backend configurado (local o s3). Sale con código 1 si falta
        algún archivo, para que una copia programada no falle en silencio.
        """
        if not fotos.subida_disponible():
            raise click.ClickException('No hay backend de fotos configurado (FOTOS_BACKEND).')
        urls = db.session.scalars(select(Mascota.foto_url).where(Mascota.foto_url.is_not(None)).distinct()).all()
        try:
            resultado = fotos.exportar_fotos(urls, destino)
        except fotos.ErrorExportacion as error:
            raise click.ClickException(str(error)) from None

        for clave in resultado.no_encontradas:
            click.echo(f'No se ha encontrado {clave} en el almacenamiento (o no se ha podido leer).', err=True)
        click.echo(f'{resultado.fotos} fotos ({resultado.archivos} archivos) exportadas a {destino}.')
        if resultado.no_encontradas:
            click.echo(f'{len(resultado.no_encontradas)} archivos no encontrados.', err=True)
            raise SystemExit(1)
