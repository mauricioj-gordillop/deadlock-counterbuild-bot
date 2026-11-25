# Tutorial Paso 3: Despliegue 24/7 Gratuito (Sin Tarjeta)

Toda la ingesta y el procesamiento Medallion ya corren en la nube (**GitHub Actions + Databricks**). El único servicio que debe mantenerse activo 24/7 es el **proceso único del Bot de Discord (`bot/`)**.

---

## 1. Elegir dónde alojar el Bot (100% gratuito, sin tarjeta)

> **Por qué se descartan AWS / GCP / Oracle Always Free / Fly.io:** aunque ofrecen capas gratuitas, exigen registrar tarjeta de crédito/débito para verificar identidad.

| Opción | Costo / Tarjeta | 24/7 nativo | Ideal si... |
|---|---|---|---|
| **Azure for Students** *(tutorial completo abajo)* | \$0 — **\$100 USD/año sin tarjeta** verificando correo universitario o GitHub Student Pack | Sí (VM Linux real) | Eres estudiante y quieres una VM Linux 24/7 sin depender de pings HTTP. Renovable cada año mientras sigas estudiando. |
| **Render (Free Web Service) + monitor HTTP** | \$0 — **sin tarjeta** (`512 MB` RAM, `750 h/mes`) | Con ping cada 10 min a `/health` | No tienes cuenta estudiantil o buscas despliegue indefinido conectado directo a GitHub (`bot/Dockerfile`). |
| **Servidor Linux propio / Raspberry Pi / WSL2** | \$0 | Sí | Ya cuentas con un equipo encendido en casa. |

> **Nota sobre migración:** como el bot es *stateless* (todos los datos viven en Databricks), si algún día termina tu periodo de estudiante en Azure o prefieres cambiar a Render, mover el bot a otro host toma ~5 minutos sin migrar bases de datos.

---

## 2. Crear una VM Linux 24/7 en Azure for Students (Paso a Paso)

### 2.1 Activar la suscripción
1. Si tienes **GitHub Student Developer Pack**, entra a [education.github.com/pack](https://education.github.com/pack) y abre **Microsoft Azure** (o entra directo a [azure.microsoft.com/free/students](https://azure.microsoft.com/free/students/)).
2. Verifica tu estatus estudiantil y SMS (**sin tarjeta**). Confirma en `https://portal.azure.com` → **Subscriptions** que tienes **Azure for Students** activa con **\$100 USD**.

### 2.2 Descubrir tus regiones permitidas *(evita `RequestDisallowedByAzure`)*
Azure for Students restringe cada suscripción a ~5 regiones concretas; si intentas crear la VM fuera de ellas fallará la validación con `RequestDisallowedByAzure`. Consulta tu lista exacta antes de crear la VM:
* **Desde el portal:** busca **`Policy`** → **Authoring → Assignments** → abre **`Allowed resource deployment regions`** → **View assignment** → pestaña **Parameters** → revisa **`Allowed locations`**.
* **O en Azure Cloud Shell** *(icono `>_` arriba a la derecha en el portal)*:
  ```bash
  az policy assignment list --query "[].parameters.listOfAllowedLocations.value" -o json
  ```

**Qué región elegir:** prioriza regiones de **Norteamérica** (como `canadacentral`, `northcentralus`, `eastus2`, `westus2` o `westus`) sobre Sudamérica (`brazilsouth`, `chilecentral`), ya que suelen ser **25–40% más baratas** en Azure, tienen mayor stock de tamaños pequeños serie `B` y menor latencia hacia Discord y Databricks.

### 2.3 Consultar tamaños baratos disponibles en tu región
En el mismo Cloud Shell, lista qué tamaños de la serie `B` tienen stock real en tu región elegida (cambia `canadacentral` por la tuya):
```bash
az vm list-skus --location canadacentral --resource-type virtualMachines --query "[?starts_with(name, 'Standard_B') && length(restrictions)==\`0\`].name" -o table
```

Tamaños recomendados (los del primer grupo incluyen **750 h/mes gratis los primeros 12 meses**):
* **Gratis 12 meses (750 h/mes):** `Standard_B2pts_v2` *(Arm64, 2 vCPU / 1 GB)*, `Standard_B2ats_v2` *(x64 AMD, 2 vCPU / 1 GB)*, `Standard_B1s` *(x64, 1 vCPU / 1 GB)*.
* **Muy baratos (caben en el crédito anual de \$100):** `Standard_B1ls` *(~\$3.80/mes, 0.5 GB RAM — usar `systemd`, no Docker)*, `Standard_B2ts_v2` *(~\$7.60/mes, 1 GB RAM)*.
* **Evita** tamaños > \$15–20/mes (`B2s`, `D2*`), ya que agotarán el crédito en pocos meses.

### 2.4 Crear la VM en el Portal sin trampas de costo
Ve a **Virtual machines** → **Create** → **Azure virtual machine**:
1. **`Basics`:**
   * **Resource group:** *Create new* → `rg-deadlock-bot`
   * **Virtual machine name:** `vm-deadlock-bot`
   * **Region:** una de las regiones permitidas obtenidas en 2.2.
   * **Security type:** selecciona **`Standard`** *(el valor por defecto `Trusted launch` oculta tamaños pequeños como `B1s` y `B1ls`)*.
   * **Image:** `Ubuntu Server 24.04 LTS - x64 Gen2` *(si vas a elegir `Standard_B2pts_v2`, selecciona **`Ubuntu Server 24.04 LTS - Arm64 Gen2`**)*.
   * **Size:** haz clic en **`See all sizes`**, ordena por **`Cost/month`** y elige tu tamaño de 2.3 (prioriza cualquiera marcado como **`Free services eligible`** o el serie `B` más barato).
   * **Authentication type:** `SSH public key` → **Username:** `ubuntu` → **Generate new key pair** (`deadlock-bot-key`).
   * **Inbound ports:** marca **solo `SSH (22)`** *(el bot solo hace conexiones salientes y `/health` escucha únicamente en `127.0.0.1:8080`)*.
2. **`Disks` *(crucial para no gastar crédito)*:**
   * **OS disk type:** cambia `Premium SSD` por **`Standard SSD (locally-redundant storage)`**.
   * **OS disk size:** **`30 GiB`** (o máximo `64 GiB`, dentro del cupo gratuito).
   * Marca **`Delete with VM`**.
3. **`Networking`:** marca **`Delete public IP and NIC when VM is deleted`**.
4. **`Management`:** **desmarca `Enable auto-shutdown`** y deja **Boot diagnostics** en `Disable`.
5. Pulsa **Review + create** → **Create** → **Download private key and create resource** (`deadlock-bot-key.pem`).

### 2.5 Conectarte por SSH desde Windows (PowerShell)
Mueve la clave a `C:\Users\Mauricio\.ssh\deadlock-bot-key.pem` (ajusta tu usuario de Windows), copia la **Public IP address** (`<IP_PUBLICA>`) desde la página de tu VM en Azure y ejecuta:
```powershell
icacls "$env:USERPROFILE\.ssh\deadlock-bot-key.pem" /inheritance:r /grant:r "$($env:USERNAME):(R)"
ssh -i "$env:USERPROFILE\.ssh\deadlock-bot-key.pem" ubuntu@<IP_PUBLICA>
```

---

## 3. Instalar y Configurar el Bot en el Servidor Ubuntu

Ya dentro de tu servidor Linux (`ubuntu@vm-deadlock-bot:~$`), prepara el repositorio y las variables de entorno:

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/mauricioj-gordillop/deadlock-counterbuild-bot.git
cd deadlock-counterbuild-bot
cp .env.example .env
nano .env
```

Completa en `.env` (usando el token **`deadlock-bot-sql`**, nunca el de GitHub Actions):
```env
DISCORD_TOKEN=tu_token_de_discord
DISCORD_GUILD_ID=id_de_tu_servidor_o_vacio_para_global

DATABRICKS_SERVER_HOSTNAME=dbc-xxxxxxxx-xxxx.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/0123456789abcdef
DATABRICKS_TOKEN=dapi_tu_token_deadlock_bot_sql
DATABRICKS_CATALOG=workspace
DATABRICKS_SCHEMA=deadlock

REFRESH_INTERVAL_HOURS=12
HEALTH_PORT=8080
LOG_LEVEL=INFO
```
Guarda en `nano` (`Ctrl+O`, `Enter`, `Ctrl+X`) y protege el archivo:
```bash
chmod 600 .env
```

---

## 4. Arrancar el Bot 24/7 en Segundo Plano

### Opción A: Python + `systemd` *(Recomendada en VMs de 0.5–1 GB RAM)*
Consume solo ~60–90 MB de RAM y no requiere instalar Docker.

1. Crea el entorno virtual e instala dependencias:
   ```bash
   python3 -m venv ~/.venvs/deadlock-bot
   ~/.venvs/deadlock-bot/bin/pip install --upgrade pip
   ~/.venvs/deadlock-bot/bin/pip install -r bot/requirements.txt
   ```
2. *(Opcional)* Prueba rápida en primer plano (`Ctrl+C` cuando confirmes que carga el snapshot y se conecta a Discord):
   ```bash
   set -a && source .env && set +a
   cd ~/deadlock-counterbuild-bot/bot && ~/.venvs/deadlock-bot/bin/python -m bot.main
   ```
3. Crea el archivo del servicio `systemd` (si tu usuario Linux no es `ubuntu`, reemplaza `ubuntu` por tu usuario):
   ```bash
   sudo tee /etc/systemd/system/deadlock-bot.service > /dev/null <<'EOF'
   [Unit]
   Description=Deadlock Counterbuild Discord Bot
   After=network-online.target
   Wants=network-online.target

   [Service]
   Type=simple
   User=ubuntu
   WorkingDirectory=/home/ubuntu/deadlock-counterbuild-bot/bot
   EnvironmentFile=/home/ubuntu/deadlock-counterbuild-bot/.env
   ExecStart=/home/ubuntu/.venvs/deadlock-bot/bin/python -m bot.main
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   EOF
   ```
4. Activa e inicia el servicio:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now deadlock-bot
   sudo systemctl status deadlock-bot
   ```

### Opción B: Docker Compose *(Alternativa en servidores con >= 1 GB RAM)*
```bash
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# Cierra y vuelve a entrar por SSH para aplicar el grupo docker
cd ~/deadlock-counterbuild-bot
docker compose up -d --build
docker compose logs -f bot
```

### Alternativa sin VM: Render Free Web Service
Si prefieres desplegar sin VM en **Render** (sin tarjeta, 750 h/mes):
1. Crea un **New Web Service** conectado a tu repo de GitHub apuntando al Dockerfile `bot/Dockerfile` (Root Directory: `bot`).
2. Carga las mismas variables de `.env` en *Environment* y configura `HEALTH_PORT=10000` (el puerto `PORT` por defecto de Render).
3. Crea un monitor gratuito en **UptimeRobot** o **cron-job.org** que haga `GET https://<tu-app>.onrender.com/health` cada **10 minutos** para evitar el *spin-down* de 15 minutos.

---

## 5. Verificación y Mantenimiento

### Verificar que todo funciona
1. En la VM ejecuta:
   ```bash
   curl http://127.0.0.1:8080/health
   ```
   Debe devolver HTTP `200 OK` con `"status": "ok"`, cantidad de `heroes`, `rules` y `loaded_at` (fecha del último refresco desde Databricks).
2. En Discord escribe `/counter`: debe aparecer el autocompletado instantáneo y responder en `< 1 s`.
3. Ya puedes cerrar la ventana SSH (`exit`); el bot seguirá corriendo 24/7.
4. En Azure Portal, revisa **Cost Management + Billing → Cost analysis** tras 2–3 días para confirmar que el gasto mensual proyectado es mínimo.

### Comandos útiles del día a día
* **Ver logs en vivo (`Ctrl+C` para salir sin detener el bot):** `sudo journalctl -u deadlock-bot -f`
* **Actualizar tras cambios en GitHub:**
  ```bash
  cd ~/deadlock-counterbuild-bot && git pull && sudo systemctl restart deadlock-bot
  ```
* **Rotar el token `deadlock-bot-sql` antes de los 90 días:** genera el nuevo token (*Scope: `BI Tools`*) en Databricks, reemplaza `DATABRICKS_TOKEN` en `.env`, ejecuta `sudo systemctl restart deadlock-bot` (o `docker compose restart bot`) y revoca el token anterior.
* **Renovar Azure for Students (cada 12 meses):** vuelve a validar tu correo universitario desde el aviso de Microsoft ~30 días antes del aniversario para recibir otros \$100 USD sin interrumpir la suscripción.
