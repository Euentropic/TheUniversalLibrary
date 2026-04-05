import os
import zipfile
import rarfile
import logging

logger = logging.getLogger(__name__)

class DependencyError(Exception):
    """Excepción específica cuando falta un ejecutable del sistema."""
    pass

class ComicEngine:
    def __init__(self, file_path):
        self.file_path = file_path
        self.archive = None
        self.image_files = []
        self._load_archive()

    def _load_archive(self):
        ext = os.path.splitext(self.file_path)[1].lower()
        try:
            if ext == '.cbz':
                self.archive = zipfile.ZipFile(self.file_path, 'r')
                file_list = self.archive.namelist()
            elif ext == '.cbr':
                self.archive = rarfile.RarFile(self.file_path, 'r')
                file_list = self.archive.namelist()
            else:
                raise ValueError("Formato no soportado, se esperaba .cbz o .cbr")
        except rarfile.Error as e:
            if "Cannot find working tool" in str(e) or "UnRAR not installed" in str(e):
                logger.error(f"Error cargando CBR por falta de dependencias: {e}")
                raise DependencyError("Falta la herramienta del sistema (unrar/WinRAR) requerida para leer archivos .cbr.")
            else:
                logger.error(f"Error abriendo el archivo {self.file_path}: {e}")
                raise
        except Exception as e:
            logger.error(f"Error abriendo el archivo {self.file_path}: {e}")
            raise

        # Filtrar por extensiones de imagen válidas (ignorando directorios ocultos como __MACOSX)
        valid_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
        images = []
        for f in file_list:
            # zipfile/rarfile usan '/' incluso en Windows, así que buscamos carpetas ignoradas
            if not f.startswith('__MACOSX') and os.path.splitext(f)[1].lower() in valid_extensions:
                images.append(f)
                
        # Ordenar alfabéticamente para asegurar el orden correcto de lectura de páginas
        self.image_files = sorted(images)
        
    def get_page_bytes(self, index: int) -> bytes:
        if 0 <= index < len(self.image_files):
            filename = self.image_files[index]
            with self.archive.open(filename) as f:
                return f.read()
        raise IndexError("Índice de página de cómic fuera de rango.")
        
    def __len__(self):
        return len(self.image_files)

    def close(self):
        if self.archive:
            self.archive.close()
