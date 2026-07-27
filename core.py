import sqlite3
import os
import shutil
import tarfile
import json
from pathlib import Path
from rich.console import Console
from tqdm import tqdm
import questionary

console = Console()

# Rutas estándar (Nativas)
STD_LUTRIS_DB = os.path.expanduser("~/.local/share/lutris/pga.db")
STD_LUTRIS_CONFIG = os.path.expanduser("~/.config/lutris/games")

# Rutas Flatpak (Steam Deck)
FLATPAK_LUTRIS_DB = os.path.expanduser("~/.var/app/net.lutris.Lutris/data/lutris/pga.db")
FLATPAK_LUTRIS_CONFIG = os.path.expanduser("~/.var/app/net.lutris.Lutris/config/lutris/games")

def detect_lutris_db():
    if os.path.exists(FLATPAK_LUTRIS_DB):
        return FLATPAK_LUTRIS_DB
    if os.path.exists(STD_LUTRIS_DB):
        return STD_LUTRIS_DB
    return None

def get_lutris_config_dir():
    if os.path.exists(FLATPAK_LUTRIS_DB):
        return FLATPAK_LUTRIS_CONFIG
    return STD_LUTRIS_CONFIG

def get_db_connection(path=None):
    if path is None:
        path = detect_lutris_db()
    if not path or not os.path.exists(path):
        # Fallback al estandar si vamos a crearla o no existe
        path = STD_LUTRIS_DB
        if not os.path.exists(path):
            raise FileNotFoundError(f"No se encontró la base de datos de Lutris en: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def get_installed_games(db_path=None):
    try:
        conn = get_db_connection(db_path)
    except FileNotFoundError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return []
        
    cursor = conn.cursor()
    # Asumiendo esquema estándar de Lutris
    try:
        # En versiones recientes de Lutris, 'is_installed' ya no existe. 
        # Es más seguro verificar que 'directory' tenga un valor asignado.
        cursor.execute("SELECT * FROM games WHERE directory IS NOT NULL AND directory != ''")
        games = [dict(row) for row in cursor.fetchall()]
        return games
    except sqlite3.OperationalError as e:
        console.print(f"[bold red]Error leyendo BD:[/bold red] {e}")
        return []
    finally:
        conn.close()

import subprocess

def export_games(selected_games, output_path):
    if not selected_games:
        console.print("[yellow]No se seleccionaron juegos para exportar.[/yellow]")
        return
        
    console.print(f"Calculando tamaño total a exportar...")
    total_size = 0
    
    # Pre-calcular el tamaño para la barra de progreso
    for game in selected_games:
        directory = game.get('directory')
        if directory and os.path.exists(directory):
            for dirpath, dirnames, filenames in os.walk(directory):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)

    console.print(f"Preparando archivo de exportación: [bold cyan]{output_path}[/bold cyan]")
    
    # Escribimos metadata temporalmente
    tmp_metadata = "/tmp/lutris_games_metadata.json"
    with open(tmp_metadata, "w") as f:
        json.dump(selected_games, f, indent=4)
        
    total_size += os.path.getsize(tmp_metadata)

    # Construimos el comando GNU Tar
    cmd = ["tar", "-c"]
    
    # GNU Tar remueve el slash inicial (/) por defecto, así que nuestras reglas
    # de transformación deben coincidir con la ruta sin el slash inicial.
    meta_path_clean = tmp_metadata.lstrip("/")
    cmd.extend(["--transform", f"s|^{meta_path_clean}|games_metadata.json|"])
    cmd.append(tmp_metadata)
    
    for game in selected_games:
        directory = game.get('directory')
        slug = game.get('slug')
        
        if directory and os.path.exists(directory):
            basename = os.path.basename(directory)
            clean_dir = os.path.abspath(directory).lstrip("/")
            cmd.extend(["--transform", f"s|^{clean_dir}|games/{basename}|"])
            cmd.append(os.path.abspath(directory))
        else:
            console.print(f"[yellow]Advertencia:[/yellow] El directorio para {game.get('name')} no existe ({directory})")

        config_file = game.get('configpath') or slug
        if config_file:
            if not config_file.endswith('.yml'):
                config_file += '.yml'
            config_path = os.path.join(get_lutris_config_dir(), config_file)
            if os.path.exists(config_path):
                clean_cfg = os.path.abspath(config_path).lstrip("/")
                cmd.extend(["--transform", f"s|^{clean_cfg}|configs/{config_file}|"])
                cmd.append(os.path.abspath(config_path))

    # Ejecutamos Tar y capturamos su salida en streaming
    # Esto combina la velocidad de bajo nivel de Tar (ideal para prefijos Proton)
    # con la capacidad de Python para mostrar una barra de progreso fluida (tqdm).
    console.print("[bold yellow]Iniciando motor híbrido (Velocidad C + UI Python)...[/bold yellow]")
    
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    try:
        with open(output_path, "wb") as f_out:
            with tqdm(total=total_size, unit="B", unit_scale=True, desc="Empaquetando") as pbar:
                while True:
                    # Leemos en bloques gigantes (4MB) para no ahogar la tarjeta SD
                    chunk = process.stdout.read(1024 * 1024 * 4)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    pbar.update(len(chunk))
    except Exception as e:
        console.print(f"[bold red]Error durante la escritura:[/bold red] {e}")
    finally:
        process.wait()
        if os.path.exists(tmp_metadata):
            os.remove(tmp_metadata)

    console.print("\n[bold green]¡Exportación completada exitosamente a máxima velocidad![/bold green]")

def install_lutris():
    """Asistente para instalar Lutris si no está presente en el sistema."""
    console.print("\n[bold yellow]Iniciando asistente de instalación de Lutris...[/bold yellow]")
    
    choices = []
    if shutil.which("pacman"):
        choices.append("Pacman (Arch Linux / Manjaro)")
    if shutil.which("flatpak"):
        choices.append("Flatpak (Universal / Steam Deck)")
    if shutil.which("apt"):
        choices.append("APT (Ubuntu / Debian / Mint)")
    if shutil.which("dnf"):
        choices.append("DNF (Fedora)")
        
    choices.append("Cancelar")
    
    if len(choices) == 1:
        console.print("[red]No se detectó un gestor de paquetes compatible. Debes instalar Lutris manualmente.[/red]")
        return False
        
    method = questionary.select(
        "¿Qué gestor de paquetes deseas usar para instalar Lutris en este PC?",
        choices=choices
    ).ask()
    
    if method == "Cancelar" or not method:
        return False
        
    try:
        if "Pacman" in method:
            console.print("[bold cyan]Se requerirá tu contraseña (sudo) para usar pacman...[/bold cyan]")
            subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "lutris"], check=True)
            console.print("[yellow]Inicializando base de datos de Lutris...[/yellow]")
            # Usamos el python del sistema para evitar que falle por estar dentro de un venv
            subprocess.run(["/usr/bin/python3", "/usr/bin/lutris", "-l"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        elif "Flatpak" in method:
            console.print("[bold cyan]Configurando repositorio de Flathub (si no existe)...[/bold cyan]")
            subprocess.run(["flatpak", "remote-add", "--if-not-exists", "flathub", "https://flathub.org/repo/flathub.flatpakrepo"], check=False)
            console.print("[bold cyan]Instalando Lutris vía Flatpak...[/bold cyan]")
            subprocess.run(["flatpak", "install", "-y", "flathub", "net.lutris.Lutris"], check=True)
            console.print("[yellow]Inicializando base de datos de Lutris...[/yellow]")
            subprocess.run(["flatpak", "run", "net.lutris.Lutris", "-l"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        elif "APT" in method:
            console.print("[bold cyan]Se requerirá tu contraseña (sudo) para usar apt...[/bold cyan]")
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y", "lutris"], check=True)
            console.print("[yellow]Inicializando base de datos de Lutris...[/yellow]")
            subprocess.run(["/usr/bin/python3", "/usr/bin/lutris", "-l"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        elif "DNF" in method:
            console.print("[bold cyan]Se requerirá tu contraseña (sudo) para usar dnf...[/bold cyan]")
            subprocess.run(["sudo", "dnf", "install", "-y", "lutris"], check=True)
            console.print("[yellow]Inicializando base de datos de Lutris...[/yellow]")
            subprocess.run(["/usr/bin/python3", "/usr/bin/lutris", "-l"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        console.print("[bold green]¡Lutris se instaló y configuró exitosamente![/bold green]")
        return True
    except subprocess.CalledProcessError:
        console.print("[bold red]Hubo un error durante la instalación. Por favor, instálalo manualmente.[/bold red]")
        return False

def import_games(archive_path):
    if not os.path.exists(archive_path):
        console.print(f"[red]El archivo de respaldo {archive_path} no existe.[/red]")
        return

    db_path = detect_lutris_db()
    if not db_path:
        console.print("[yellow]No se encontró una instalación de Lutris en este sistema.[/yellow]")
        if questionary.confirm("¿Deseas que la herramienta intente instalar y configurar Lutris por ti ahora mismo?").ask():
            if install_lutris():
                db_path = detect_lutris_db()
                
        if not db_path:
            console.print("[red]No se puede continuar sin Lutris. Abortando importación.[/red]")
            return

    # 1. Preguntar por la ruta base
    default_base_dir = os.path.expanduser("~/Games")
    base_dest_dir = questionary.path(
        "¿En qué carpeta base deseas instalar los juegos?",
        default=default_base_dir,
        only_directories=True
    ).ask()
    
    if not base_dest_dir:
        console.print("[yellow]Importación cancelada.[/yellow]")
        return
        
    os.makedirs(base_dest_dir, exist_ok=True)
    os.makedirs(get_lutris_config_dir(), exist_ok=True)

    console.print(f"[blue]Preparando motor de extracción secuencial...[/blue]")
    total_size = os.path.getsize(archive_path)
    metadata = None

    with tarfile.open(archive_path, "r") as tar:
        with tqdm(total=total_size, unit="B", unit_scale=True, desc="Extrayendo juegos") as pbar:
            for m in tar:
                # La barra de progreso avanza según el tamaño del archivo
                pbar.update(m.size + 512) # Aproximación del tamaño real en el tar
                
                if m.name == "games_metadata.json":
                    extracted = tar.extractfile(m)
                    if extracted:
                        metadata = json.load(extracted)
                    continue
                    
                if m.name.startswith("games/"):
                    rel_path = os.path.relpath(m.name, "games")
                    dest_path = os.path.join(base_dest_dir, rel_path)
                elif m.name.startswith("configs/"):
                    rel_path = os.path.relpath(m.name, "configs")
                    dest_path = os.path.join(get_lutris_config_dir(), rel_path)
                else:
                    continue
                    
                if m.isdir():
                    os.makedirs(dest_path, exist_ok=True)
                elif m.issym():
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    if os.path.exists(dest_path) or os.path.islink(dest_path):
                        try:
                            os.remove(dest_path)
                        except OSError:
                            pass
                    try:
                        os.symlink(m.linkname, dest_path)
                    except OSError:
                        pass
                elif m.isreg():
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    extracted = tar.extractfile(m)
                    if extracted:
                        with open(dest_path, "wb") as out_f:
                            shutil.copyfileobj(extracted, out_f)
                        # Restaurar los permisos originales (ej: ejecución para los .exe y .dll)
                        try:
                            os.chmod(dest_path, m.mode)
                        except OSError:
                            pass

    if not metadata:
        console.print("[bold red]Archivo inválido: No se encontró games_metadata.json[/bold red]")
        return

    console.print("[blue]Inyectando información en la base de datos de Lutris...[/blue]")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Obtener las columnas válidas de la base de datos actual para evitar errores por versiones distintas de Lutris
    cursor.execute("PRAGMA table_info(games)")
    valid_columns = [row['name'] for row in cursor.fetchall()]

    for game in metadata:
        name = game.get('name', 'Desconocido')
        original_dir = game.get('directory')
        slug = game.get('slug')
        basename = os.path.basename(original_dir) if original_dir else slug
        new_dir = os.path.join(base_dest_dir, basename)
        
        # Ajustar configuraciones si es necesario
        config_file = game.get('configpath') or slug
        if not config_file.endswith('.yml'):
            config_file += '.yml'
            
        conf_dest = os.path.join(get_lutris_config_dir(), config_file)
        if os.path.exists(conf_dest) and original_dir:
            try:
                with open(conf_dest, "r", encoding="utf-8") as f:
                    content = f.read()
                content = content.replace(original_dir, new_dir)
                with open(conf_dest, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                console.print(f"[yellow]Advertencia: No se pudo modificar el archivo de configuración para {name}: {e}[/yellow]")

        # Actualizar base de datos
        game['directory'] = new_dir
        game.pop('id', None)
        
        # Filtrar solo las columnas que existan en la base de datos del PC de destino
        filtered_game = {k: v for k, v in game.items() if k in valid_columns}
        
        columns = ', '.join(filtered_game.keys())
        placeholders = ', '.join(['?'] * len(filtered_game))
        
        try:
            cursor.execute(f"SELECT id FROM games WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            
            if row:
                set_clause = ', '.join([f"{k} = ?" for k in filtered_game.keys()])
                values = list(filtered_game.values()) + [row['id']]
                cursor.execute(f"UPDATE games SET {set_clause} WHERE id = ?", values)
            else:
                cursor.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", tuple(filtered_game.values()))
        except sqlite3.Error as e:
            console.print(f"[bold red]Error guardando {name} en BD:[/bold red] {e}")

    conn.commit()
    conn.close()
        
    console.print("[bold green]¡Migración completada exitosamente! Abre Lutris para ver tus juegos.[/bold green]")
