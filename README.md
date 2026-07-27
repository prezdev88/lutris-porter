# Lutris Porter

Una herramienta por línea de comandos diseñada para respaldar y migrar tus juegos de [Lutris](https://lutris.net/) de un computador a otro (por ejemplo, desde una Steam Deck hacia tu PC principal).

## Requisitos
- Python 3
- Lutris instalado (necesita `~/.local/share/lutris/pga.db`)

## Instalación y Configuración

```bash
# Clonar o entrar al repositorio
cd lutris-backup

# Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate
pip install questionary rich tqdm
```

## Uso

### Exportar (Respaldar)
El comando `export` escanea tu base de datos de Lutris y te presenta una lista interactiva de todos tus juegos instalados. Puedes elegir cuáles empaquetar.

```bash
python main.py export -o respaldo_juegos.tar.gz
```
- Usa **Espacio** para seleccionar/deseleccionar un juego.
- Usa **Enter** para confirmar y generar el paquete.

El archivo resultante contendrá:
- La carpeta completa del juego.
- El archivo de configuración de Lutris (`.yml`).
- La metadata extraída directamente de tu base de datos.

### Importar (Migrar)
Transfiere el archivo compreso generado (`respaldo_juegos.tar.gz`) al nuevo PC y ejecuta el siguiente comando:

```bash
python main.py import respaldo_juegos.tar.gz
```
La aplicación te preguntará en qué carpeta deseas instalar los juegos (por defecto `~/Games`). Automáticamente:
1. Extraerá los archivos a la nueva ubicación.
2. Colocará la configuración en `~/.config/lutris/games/` actualizando las rutas antiguas a las nuevas de manera automática.
3. Actualizará o registrará los juegos de vuelta en tu base de datos local de Lutris para que aparezcan apenas abras la aplicación.

¡Y listo! Al iniciar Lutris verás todos los juegos importados funcionando a la perfección.
