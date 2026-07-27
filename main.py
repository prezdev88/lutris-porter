import argparse
import sys
import os
from rich.console import Console

from core import get_installed_games, export_games, import_games
import questionary

console = Console()

def detect_usb_drives():
    """Busca unidades extraíbles montadas en las rutas comunes de Linux/SteamOS."""
    drives = []
    base_media_path = "/run/media/"
    if os.path.exists(base_media_path):
        try:
            for user_dir in os.listdir(base_media_path):
                user_path = os.path.join(base_media_path, user_dir)
                if os.path.isdir(user_path):
                    try:
                        for drive in os.listdir(user_path):
                            drive_path = os.path.join(user_path, drive)
                            if os.path.isdir(drive_path):
                                drives.append(drive_path)
                    except PermissionError:
                        # Ignorar si no hay permisos (ej: /run/media/root)
                        continue
        except PermissionError:
            pass
    return drives

def run_export(output_file):
    console.print("\n[bold blue]Buscando juegos en Lutris...[/bold blue]")
    games = get_installed_games()
    
    if not games:
        console.print("[red]No se encontraron juegos instalados o hubo un error al leer la base de datos.[/red]")
        return
        
    choices = [{"name": g["name"], "value": g} for g in games]
    
    selected = questionary.checkbox(
        "Selecciona los juegos que deseas exportar (Usa Espacio para marcar, Enter para confirmar):",
        choices=choices
    ).ask()
    
    if selected:
        export_games(selected, output_file)
    else:
        console.print("[yellow]Operación cancelada. No se seleccionaron juegos.[/yellow]")
    
def run_import(archive_file):
    console.print(f"\n[bold green]Iniciando proceso de importación desde {archive_file}...[/bold green]")
    import_games(archive_file)

def run_wizard():
    console.print("[bold cyan]=== Asistente de Migración de Lutris ===[/bold cyan]\n")
    
    action = questionary.select(
        "¿Qué deseas hacer?",
        choices=[
            "Exportar (Respaldar juegos de este PC a un archivo)",
            "Importar (Restaurar juegos desde un archivo a este PC)",
            "Salir"
        ]
    ).ask()
    
    if not action or action == "Salir":
        console.print("[yellow]Saliendo...[/yellow]")
        sys.exit(0)
        
    if action.startswith("Exportar"):
        base_path = ""
        usbs = detect_usb_drives()
        
        if usbs:
            choices = [{"name": "Almacenamiento Local (Carpeta actual)", "value": ""}]
            for u in usbs:
                choices.append({"name": f"Pendrive / Disco Externo ({os.path.basename(u)})", "value": f"{u}/"})
                
            base_path = questionary.select(
                "¡He detectado discos externos! ¿Dónde quieres guardar el respaldo?",
                choices=choices
            ).ask()
            
            if base_path is None:  # Canceló con Ctrl+C
                return

        output = questionary.text(
            "¿Cómo deseas llamar al archivo de respaldo?",
            default="lutris_backup.tar"
        ).ask()
        
        if output:
            final_path = os.path.join(base_path, output) if base_path else output
            run_export(final_path)
            
    elif action.startswith("Importar"):
        archive = questionary.path(
            "Ingresa la ruta del archivo de respaldo a importar:",
            default="lutris_backup.tar"
        ).ask()
        
        if archive:
            run_import(archive)

def main():
    parser = argparse.ArgumentParser(description="Lutris Migrator - Respalda y migra tus juegos de Lutris fácilmente.")
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponibles")

    # Comando 'export'
    parser_export = subparsers.add_parser("export", help="Exporta uno o más juegos a un archivo compreso")
    parser_export.add_argument("-o", "--output", default="lutris_backup.tar", help="Nombre del archivo de salida (ej: backup.tar)")

    # Comando 'import'
    parser_import = subparsers.add_parser("import", help="Importa juegos desde un archivo compreso")
    parser_import.add_argument("archive", help="Ruta al archivo compreso (.tar)")

    args = parser.parse_args()

    # Si no se pasan argumentos (como cuando el usuario solo hace 'python main.py'), lanzamos el wizard
    if args.command is None:
        run_wizard()
    elif args.command == "export":
        run_export(args.output)
    elif args.command == "import":
        run_import(args.archive)

if __name__ == "__main__":
    main()
