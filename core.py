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

# Detección automática
if os.path.exists(FLATPAK_LUTRIS_DB):
    LUTRIS_DB_PATH = FLATPAK_LUTRIS_DB
    LUTRIS_CONFIG_DIR = FLATPAK_LUTRIS_CONFIG
else:
    # Usamos estándar por defecto o si existe
    LUTRIS_DB_PATH = STD_LUTRIS_DB
    LUTRIS_CONFIG_DIR = STD_LUTRIS_CONFIG

def get_db_connection(path=LUTRIS_DB_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró la base de datos de Lutris en: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def get_installed_games(db_path=LUTRIS_DB_PATH):
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
        
    console.print(f"Preparando archivo de exportación: [bold cyan]{output_path}[/bold cyan]")
    
    # 1. Guardar la metadata temporalmente
    metadata_file = "games_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(selected_games, f, indent=4)
        
    # Crear el tar con la metadata primero
    subprocess.run(["tar", "-cf", output_path, metadata_file], check=True)
    os.remove(metadata_file)
    
    # 2. Agregar cada juego usando GNU tar nativo (infinitamente más rápido para archivos pequeños)
    console.print("[bold yellow]Empaquetando juegos con motor nativo de Linux (GNU Tar)...[/bold yellow]")
    console.print("Esto procesará miles de archivos pequeños a velocidad nativa.")
    
    for game in selected_games:
        name = game.get('name', 'Desconocido')
        directory = game.get('directory')
        slug = game.get('slug')
        
        console.print(f" -> Añadiendo: [bold cyan]{name}[/bold cyan]")
        
        if directory and os.path.exists(directory):
            basename = os.path.basename(directory)
            # GNU tar -r (append). Transformamos la ruta interna '.' a 'games/basename'
            # Descartamos errores menores como "socket ignored" que lanza tar
            transform_arg = f"s,^\\.,games/{basename},"
            subprocess.run(
                ["tar", "--transform", transform_arg, "-rf", output_path, "-C", directory, "."],
                stderr=subprocess.DEVNULL
            )
        else:
            console.print(f"[yellow]Advertencia:[/yellow] El directorio para {name} no existe ({directory})")

        # Buscar archivo de configuración
        config_file = game.get('configpath') or slug
        if config_file:
            if not config_file.endswith('.yml'):
                config_file += '.yml'
            config_path = os.path.join(LUTRIS_CONFIG_DIR, config_file)
            if os.path.exists(config_path):
                transform_arg = f"s,^.*/,configs/,"
                subprocess.run(
                    ["tar", "--transform", transform_arg, "-rf", output_path, config_path],
                    stderr=subprocess.DEVNULL
                )

    console.print("\n[bold green]¡Exportación completada exitosamente a velocidad nativa![/bold green]")

def import_games(archive_path):
    if not os.path.exists(archive_path):
        console.print(f"[bold red]Error:[/bold red] El archivo {archive_path} no existe.")
        return
        
    if not os.path.exists(LUTRIS_DB_PATH):
        console.print("[bold red]Lutris no parece estar instalado en este sistema. (pga.db no encontrado)[/bold red]")
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
    os.makedirs(LUTRIS_CONFIG_DIR, exist_ok=True)

    with tarfile.open(archive_path, "r") as tar:
        # Extraer y leer metadata
        try:
            metadata_member = tar.getmember("games_metadata.json")
            f = tar.extractfile(metadata_member)
            metadata = json.load(f)
        except KeyError:
            console.print("[bold red]Archivo inválido: No se encontró games_metadata.json[/bold red]")
            return

        conn = get_db_connection()
        cursor = conn.cursor()

        for game in tqdm(metadata, desc="Importando juegos"):
            name = game.get('name', 'Desconocido')
            original_dir = game.get('directory')
            slug = game.get('slug')
            config_file = game.get('configpath') or slug
            
            if not config_file.endswith('.yml'):
                config_file += '.yml'
                
            basename = os.path.basename(original_dir) if original_dir else slug
            new_dir = os.path.join(base_dest_dir, basename)
            
            # Extraer archivos del juego
            game_folder_prefix = f"games/{basename}"
            members = [m for m in tar.getmembers() if m.name.startswith(game_folder_prefix)]
            
            if members:
                # Ajustamos las rutas para extraer en el nuevo directorio
                for m in members:
                    # m.name es algo como "games/basename/algo"
                    # queremos que se extraiga en "new_dir/algo"
                    # tar.extract preserva m.name si no lo modificamos, es mejor extraer a una temp o cambiar name
                    pass
                
                # Para simplificar la extracción de una subcarpeta, extraemos al directorio base_dest_dir 
                # (ya que el prefijo es games/basename, quedará en base_dest_dir/games/basename... no,
                # para evitar eso extraemos manualmente).
                for m in members:
                    rel_path = os.path.relpath(m.name, "games") # ej: basename/algo
                    dest_path = os.path.join(base_dest_dir, rel_path)
                    
                    if m.isdir():
                        os.makedirs(dest_path, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        with open(dest_path, "wb") as out_f:
                            with tar.extractfile(m) as in_f:
                                shutil.copyfileobj(in_f, out_f)
            
            # Extraer y ajustar configuración
            config_member_name = f"configs/{config_file}"
            try:
                conf_m = tar.getmember(config_member_name)
                conf_dest = os.path.join(LUTRIS_CONFIG_DIR, config_file)
                
                with open(conf_dest, "w", encoding="utf-8") as out_f:
                    with tar.extractfile(conf_m) as in_f:
                        content = in_f.read().decode("utf-8")
                        # Reemplazo de cadena básico pero efectivo
                        if original_dir:
                            content = content.replace(original_dir, new_dir)
                        out_f.write(content)
            except KeyError:
                console.print(f"[yellow]No se encontró configuración para {name}[/yellow]")

            # Actualizar base de datos
            game['directory'] = new_dir
            # Remover id si queremos que sea autoincremental o forzar reemplazo
            game_id = game.pop('id', None) 
            
            columns = ', '.join(game.keys())
            placeholders = ', '.join(['?'] * len(game))
            
            try:
                # Si el juego ya existe por slug, lo actualizamos, si no lo insertamos
                cursor.execute(f"SELECT id FROM games WHERE slug = ?", (slug,))
                row = cursor.fetchone()
                
                if row:
                    # Update
                    set_clause = ', '.join([f"{k} = ?" for k in game.keys()])
                    values = list(game.values()) + [row['id']]
                    cursor.execute(f"UPDATE games SET {set_clause} WHERE id = ?", values)
                else:
                    # Insert
                    cursor.execute(f"INSERT INTO games ({columns}) VALUES ({placeholders})", tuple(game.values()))
            except sqlite3.Error as e:
                console.print(f"[bold red]Error guardando {name} en BD:[/bold red] {e}")

        conn.commit()
        conn.close()
        
    console.print("[bold green]¡Migración completada exitosamente! Abre Lutris para ver tus juegos.[/bold green]")
    
