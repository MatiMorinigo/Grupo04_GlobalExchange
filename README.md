# Grupo04_GlobalExchange
Plataforma web para la gestión digital de operaciones cambiarias de Global Exchange, desarrollada con Django, Keycloak, PostgreSQL y tecnologías web, aplicando Scrum como metodología de desarrollo.

# Global Exchange Web

Global Exchange Web es una plataforma desarrollada para digitalizar y gestionar los procesos principales de una casa de cambio.

El sistema permite realizar operaciones de compra y venta de divisas, consultar tasas de cambio, gestionar clientes, generar reportes, emitir facturas electrónicas y administrar operaciones de cajas físicas y sucursales.

Este proyecto es desarrollado en el marco de la asignatura Ingeniería de Software II utilizando Scrum como metodología de trabajo.

## Objetivo

Desarrollar una plataforma web que permita realizar operaciones cambiarias de manera rápida, segura y conveniente, además de proporcionar herramientas para la administración, monitoreo y control de las operaciones de Global Exchange.

## Funcionalidades principales

- Registro y autenticación de usuarios.
- Autenticación y autorización mediante Keycloak.
- Gestión de roles y permisos.
- Asociación de usuarios con clientes.
- Gestión de clientes físicos y jurídicos.
- Clasificación de clientes en Minorista, Corporativo y VIP.
- Consulta de tasas de cambio.
- Simulación de conversión entre monedas.
- Compra y venta de divisas.
- Gestión de estados de transacciones.
- Integración con medios de pago.
- Facturación electrónica.
- Historial de transacciones.
- Exportación de reportes en PDF y Excel.
- Monitoreo de ganancias.
- Gestión de monedas y tasas de cambio.
- Notificaciones por correo electrónico.
- Gestión de sucursales y cajas físicas.
- Apertura y cierre de cajas.
- Gestión de remesas y movimientos de efectivo.
- Arqueo automático de caja.
- Control de diferencias entre saldo físico y teórico.

## Tecnologías

### Backend

- Python 3.11
- Django
- Django REST Framework
- Gunicorn
- Celery

### Autenticación y autorización

- Keycloak
- OpenID Connect (OIDC)
- OAuth 2.0
- JSON Web Token (JWT)

### Base de datos y servicios

- PostgreSQL
- Redis

### Frontend

- HTML5
- CSS3
- JavaScript
- Nginx

### Integraciones externas

- Servicio de correo electrónico
- Plataforma de pagos
- API de facturación electrónica

## Arquitectura

La aplicación se encuentra organizada en diferentes componentes:

- Cliente / Navegador Web
- Servidor Web
- Servidor Backend
- Servidor de Base de Datos
- Keycloak
- Redis
- Servicio de correo electrónico
- Plataforma de pagos
- Servicio de facturación electrónica

El sistema contará con configuraciones independientes para los ambientes de:

- Desarrollo
- Pruebas
- Producción

## Roles principales

El sistema contempla los siguientes actores:

- Visitante
- Usuario
- Cliente
- Administrador
- Analista cambiario
- Cajero
- Tesorero

También interactúa con servicios externos como Keycloak, servicios bancarios, billeteras electrónicas, correo electrónico y servicios de facturación.

## Metodología de desarrollo

El proyecto utiliza Scrum.

El trabajo se organiza mediante:

- Product Backlog
- Sprints
- Sprint Backlog
- Epics
- Historias de Usuario
- Tareas

Jira es utilizado para la gestión y seguimiento del proyecto.

## Control de versiones

El código fuente del proyecto se administra mediante Git y GitHub.

El equipo utilizará ramas para organizar el desarrollo y facilitar la integración de los cambios realizados por los distintos integrantes.

## Estado del proyecto

🚧 Proyecto actualmente en desarrollo.
