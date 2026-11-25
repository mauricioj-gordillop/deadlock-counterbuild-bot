# Guía Detallada: Discord Developer Portal

Esta guía explica paso a paso cómo registrar el bot, obtener su token e invitarlo con los permisos mínimos necesarios para el slash command `/counter`.

## Paso 1: Crear la aplicación y obtener el `DISCORD_TOKEN`
1. Ingresa a [Discord Developer Portal](https://discord.com/developers/applications) con tu cuenta de Discord.
2. Haz clic en **New Application**, escribe un nombre (por ejemplo `Deadlock Counterbuild`), acepta los términos y pulsa **Create**.
3. En el menú lateral izquierdo selecciona **Bot**.
4. Haz clic en **Reset Token** (y confirma con tu contraseña/2FA si te lo solicita) → **Copy**.
5. Guarda ese valor para pegarlo en `DISCORD_TOKEN` dentro del archivo `.env` en tu servidor ([deployment.md](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/docs/deployment.md)).
6. **Privileged Gateway Intents:** deja los tres interruptores (*Presence Intent*, *Server Members Intent* y *Message Content Intent*) en **`Off`**. Este bot opera exclusivamente con slash commands (`/counter`) y no necesita permisos privilegiados.

## Paso 2: Invitar el bot a tu servidor con permisos mínimos
1. En el menú lateral izquierdo abre **OAuth2** → **URL Generator**.
2. En la sección **Scopes**, marca exactamente estas dos casillas:
   - `bot`
   - `applications.commands`
3. Aparecerá la sección **Bot Permissions**. Marca únicamente:
   - `Send Messages`
   - `Embed Links`
   - `Use Slash Commands`
4. Baja hasta **Generated URL**, haz clic en **Copy** y ábrela en una pestaña nueva del navegador.
5. Selecciona el servidor de Discord donde quieres instalar el bot y haz clic en **Continue** → **Authorize**.

## Paso 3: Sincronización instantánea de `/counter` (recomendado en pruebas)
Discord puede tardar hasta 1 hora en propagar comandos registrados globalmente. Para probar `/counter` de inmediato en tu servidor:
1. En la app de Discord ve a **Ajustes de usuario** (engranaje) → **Avanzado** → activa **Modo Desarrollador**.
2. Haz clic derecho sobre el icono de tu servidor → **Copiar ID del servidor**.
3. Colócalo en tu `.env`:
   ```env
   DISCORD_GUILD_ID=123456789012345678
   ```
4. Cuando quieras que `/counter` funcione en todos los servidores donde se invite el bot, deja `DISCORD_GUILD_ID=` vacío y reinicia el bot.
