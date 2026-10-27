"""Shared file-size units and bounded IO for registration."""
import hashlib
MIB = 1024 ** 2
DEFAULT_FILE_MIB = 1024
CHUNK = MIB

def human(size_bytes):
    """1 GB = 1 GiB (1024 MiB), the convention used on every PRM screen."""
    if size_bytes >= 1024 * MIB:
        value = size_bytes / (1024 * MIB)
        return (f"{value:.0f}" if value == int(value) else f"{value:.2f}").replace(".", ",") + " GB"
    return f"{size_bytes / MIB:.1f}".replace(".", ",") + " MB"


def check_size(size, limit_mib=DEFAULT_FILE_MIB):
    """Per-file limit: exactly limit_mib MiB is accepted, one byte more is refused."""
    if size > limit_mib * MIB:
        raise ValueError(f'Arquivo acima do limite permitido de {human(limit_mib * MIB)}.')


def check_package(size, limit_mib):
    """Whole ZIP/folder: several files of up to 1 GB each may travel together, up to PRM_UPLOAD_MAX_MIB."""
    if size > limit_mib * MIB:
        raise ValueError(f'Pacote (ZIP ou pasta) acima do limite permitido de {human(limit_mib * MIB)}. '
                         'Cada arquivo pode ter até 1 GB; divida o lote em pacotes menores.')

def file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b''): digest.update(chunk)
    return digest.hexdigest()

def copy_bounded(reader, writer, limit):
    total=0
    while chunk:=reader.read(CHUNK):
        total+=len(chunk)
        if total>limit: raise ValueError('Arquivo excede limite descompactado.')
        writer.write(chunk)
    return total
