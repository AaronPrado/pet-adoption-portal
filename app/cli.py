"""
Comandos de línea de comandos de la aplicación (flask <comando>).
"""

import click

from app import db
from app.models import Usuario
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
