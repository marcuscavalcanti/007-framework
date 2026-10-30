"""Read exact historical proof inputs without a Git checkout or extraction."""
import hashlib
import io
import tarfile
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures/historical-sources.tar.gz"
SHA256 = "75405b32cf52569c299e7e5b5c53954289a7e31a6aa9110c551c4d319e65a906"


def historical_source(revision, relative):
    payload = FIXTURE.read_bytes()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("historical source fixture hash mismatch")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        member = archive.getmember(f"{revision}/{relative}")
        if not member.isfile():
            raise ValueError("historical source is not a regular file")
        return archive.extractfile(member).read()
